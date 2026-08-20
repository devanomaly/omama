"""Deterministic validator skeleton: drop-in gate for any structured artifact
(CSV of labels, a config export, a generated report) that a script — never
an LLM, never a human eyeballing a diff — checks against a closed schema.

THREE-STATE EXIT CONTRACT
--------------------------
Every run ends in exactly one of three states, and the last line printed
always names it literally:

  0  VERIFIED  - ran end-to-end, evaluated every declared column and every
                 row, zero violations.
  1  FAILED    - ran end-to-end, found one or more named violations.
  2  NOT-RUN   - could NOT evaluate: unreadable path, undecodable bytes,
                 an embedded NUL byte (valid UTF-8, but the signature of
                 binary garbage / wrong encoding / truncated writes),
                 empty file (no header), malformed CSV (including an
                 unterminated quoted field that runs off the end of the
                 file), a header that shares no column name with the
                 declared schema (a data row mistaken for the header), or
                 the validator itself not configured with a SCHEMA. Partial
                 coverage is NOT-RUN, never a pass — a checker that could
                 not look must never report a pass. The final line names
                 what could not be evaluated.

HOW TO ADOPT
------------
1. Copy this file into your project (keep the name or rename it, doesn't
   matter — it has no import dependency on this toolkit).
2. Edit the SCHEMA dict below: one entry per CSV column you want gated.
3. Run: python3 validator_skeleton.py --csv path/to/artifact.csv
4. Wire the exit code into your pipeline/CI/pre-commit gate: 0 = clean,
   1 = violations found, 2 = could not evaluate at all (treat exactly
   like a failure — never proceed past a 2).

The row-level validate_rows() function and the CLI plumbing around it are
schema-agnostic — you never need to touch them. Only SCHEMA changes.

SCHEMA FORMAT
-------------
SCHEMA = {
    "column_name": {
        "required": True,              # empty value -> "missing" violation
        "enum": {"a", "b", "c"},       # closed vocabulary; omit for free text
        "type": "int",                 # optional: "int" or "str" (default)
    },
    ...
}

Every violation is reported as {line, field, check}. ROW-level checks never
put a raw cell value in `field` (schema names, header names, or column-N
positions only). HEADER-level checks (unknown-column, duplicate-column) echo
header CELL TEXT — safe exactly when the header row is a genuine header. If
a headerless CSV's first data row happens to share >= 1 cell with a schema
column name, the zero-overlap NOT-RUN guard does not fire and the OTHER
cells of that data row (raw data, possibly PII) are echoed as
unknown-column field names. Treat the output as log-safe only when header
provenance is trusted (e.g. the writer always emits the header row).

Checks: "missing", "enum", "type" (row-level); "unknown-column" (an
undeclared column header), "missing-column" (a SCHEMA field absent from
the CSV header), "duplicate-column" (the same column name appears more
than once in the header — every occurrence is validated independently, so
an invalid value can no longer hide behind column order); "extra-cell"
(a data row has more cells than the header declares — an undeclared value
that would otherwise pass silently, named per extra position); "missing-cell"
(a data row has FEWER cells than the header declares — the symmetric
shortfall, named by the real header column name at that position, so a
truncated row is flagged even when the missing column isn't `required`).
"""
import argparse
import csv
import json
import re
import sys


class NotRun(Exception):
    """Raised whenever the validator could not evaluate the input at all.
    Carries the human-readable reason that becomes the NOT-RUN line."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ASCII-only: `[0-9]` as an explicit character class matches only U+0030-39,
# never fullwidth/Arabic-Indic/other Unicode decimal digits, and never the
# `_` digit-group separator Python's own int() accepts. A "type": "int"
# schema promise means "parses the same way downstream JSON/int() readers
# in Go, JS, Postgres would" -- not "whatever CPython's int() happens to
# tolerate this version".
_STRICT_INT_RE = re.compile(r"^[+-]?[0-9]+$")


def _reject_nul(f, path):
    """Yields the file's lines, raising NotRun on the first embedded NUL
    byte. NUL is valid UTF-8, so decoding alone never catches it -- but in a
    text CSV it is the signature of binary garbage, a wrong encoding (e.g.
    UTF-16 read as UTF-8), or a truncated/interleaved write. That is the
    could-not-trust-the-bytes class, i.e. NOT-RUN -- never a VERIFIED."""
    for line in f:
        if "\x00" in line:
            raise NotRun("NUL byte in %s -- not trustworthy text "
                         "(binary garbage, wrong encoding, or a truncated "
                         "write)" % path)
        yield line


def load_csv(path):
    """Returns (header, rows) where header is the raw list of column names
    (duplicates preserved, in header order) and rows is a list of
    (line_num, raw_row) with raw_row the unprocessed list of cell strings —
    its length may differ from len(header); that mismatch is exactly what
    the row-level extra-cell/missing-cell checks are for. Raises NotRun if
    the file can't be opened, decoded, or parsed as CSV, has no header
    row at all, or contains an embedded NUL byte (see _reject_nul).

    Uses csv.reader(..., strict=True): the stdlib csv module does NOT raise
    for an unterminated quoted field at EOF by default -- it silently
    swallows every remaining physical line into one giant final field, so a
    truncated file reports back as one short, clean-looking row instead of
    a parse failure. strict=True turns that into csv.Error ("unexpected end
    of data"), which the NotRun handler below turns into NOT-RUN. Verified
    this does not misfire on ordinary multi-line quoted fields, doubled
    ("escaped") quotes, or a stray unquoted `"` inside a data value -- all
    still parse the same as before; only the "quote never closes before
    EOF" shape newly raises.

    `rows` are addressed by `reader.line_num` (physical line the record
    ENDED on), not a logical record counter -- a quoted field spanning
    several physical lines must not be mis-addressed as an early line
    number when it actually closes several lines later.
    """
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(_reject_nul(f, path), strict=True)
            try:
                header = next(reader)
            except StopIteration:
                raise NotRun("empty file (no header row): %s" % path)
            except csv.Error as exc:
                raise NotRun("malformed CSV while reading header of %s: %s" % (path, exc))
            rows = []
            try:
                for raw_row in reader:
                    rows.append((reader.line_num, raw_row))
            except csv.Error as exc:
                raise NotRun("malformed CSV while reading %s: %s" % (path, exc))
    except OSError as exc:
        raise NotRun("unreadable file: %s" % exc)
    except UnicodeDecodeError as exc:
        raise NotRun("undecodable file (not valid utf-8): %s" % exc)
    return header, rows


def check_header(header, schema):
    """Header-level violations: duplicate column names, columns the schema
    expects but the CSV lacks, and columns the CSV has that the schema
    doesn't know about. Duplicate columns get their own explicit check —
    never left to surface only as a misleading missing-column report."""
    violations = []
    schema_fields = set(schema)
    csv_fields = set(header)

    seen_counts = {}
    for name in header:
        seen_counts[name] = seen_counts.get(name, 0) + 1
    for name in sorted(n for n, c in seen_counts.items() if c > 1):
        violations.append({"line": None, "field": name, "check": "duplicate-column"})

    for missing in sorted(schema_fields - csv_fields):
        violations.append({"line": None, "field": missing, "check": "missing-column"})
    for extra in sorted(csv_fields - schema_fields):
        violations.append({"line": None, "field": extra, "check": "unknown-column"})
    return violations


def _field_positions(header):
    """Maps each column name to the list of indexes it occupies in the
    header. A list longer than 1 means that column name is duplicated."""
    positions = {}
    for idx, name in enumerate(header):
        positions.setdefault(name, []).append(idx)
    return positions


def validate_row(line, raw_row, header, positions, schema):
    """Validates one raw row against SCHEMA. Returns a list of violations
    ({line, field, check}) for that row — empty list if the row is clean.
    Every occurrence of a duplicated column is checked independently (so an
    invalid value can't hide behind column order), and every cell beyond
    the header's length is reported as an undeclared extra-cell."""
    violations = []

    for field, rules in schema.items():
        idxs = positions.get(field, [])
        values = [raw_row[i].strip() if i < len(raw_row) and raw_row[i] is not None else ""
                  for i in idxs]
        required = rules.get("required", False)

        if not values or all(v == "" for v in values):
            if required:
                violations.append({"line": line, "field": field, "check": "missing"})
            continue

        field_type = rules.get("type", "str")
        enum = rules.get("enum")
        for value in values:
            if value == "":
                continue
            if field_type == "int" and not _STRICT_INT_RE.match(value):
                violations.append({"line": line, "field": field, "check": "type"})
                continue
            if enum is not None and value not in enum:
                violations.append({"line": line, "field": field, "check": "enum"})

    if len(raw_row) > len(header):
        for extra_idx in range(len(header), len(raw_row)):
            violations.append({"line": line, "field": "column-%d" % (extra_idx + 1),
                               "check": "extra-cell"})
    elif len(raw_row) < len(header):
        # Symmetric to extra-cell: a row with FEWER cells than the header
        # declares is an undeclared structural shortfall too, not silently
        # "the trailing columns happened to be empty". Named by the real
        # header column name at that position (never a raw value -- these
        # are column names, not data) so it survives even when the missing
        # column isn't `required` and so would otherwise generate no
        # violation of any kind.
        for missing_idx in range(len(raw_row), len(header)):
            violations.append({"line": line, "field": header[missing_idx],
                               "check": "missing-cell"})

    return violations


_SCHEMA_RULE_KEYS = {"required", "enum", "type"}
_SCHEMA_TYPES = {"int", "str"}


def check_schema(schema):
    """Raises NotRun if SCHEMA itself is malformed. A schema typo
    (`"type": "integer"`) used to fall through to the default no-op path,
    so invalid data could be VERIFIED by a checker that silently was not
    checking (5th external review, 2026-08-18). A misconfigured validator
    has not evaluated anything: NOT-RUN, never a verdict."""
    if not isinstance(schema, dict):
        raise NotRun("SCHEMA is not a mapping: %r" % (type(schema).__name__,))
    for field, rules in schema.items():
        if not isinstance(field, str) or not field.strip():
            raise NotRun("SCHEMA has a non-string/empty column name: %r" % (field,))
        if not isinstance(rules, dict):
            raise NotRun("SCHEMA[%r] is not a mapping of rules: %r" % (field, rules))
        unknown = sorted(set(rules) - _SCHEMA_RULE_KEYS)
        if unknown:
            raise NotRun("SCHEMA[%r] has unknown rule key(s) %s -- known: %s"
                         % (field, unknown, sorted(_SCHEMA_RULE_KEYS)))
        if "required" in rules and not isinstance(rules["required"], bool):
            raise NotRun("SCHEMA[%r]['required'] is not a boolean: %r"
                         % (field, rules["required"]))
        if "type" in rules and rules["type"] not in _SCHEMA_TYPES:
            raise NotRun("SCHEMA[%r]['type'] is %r -- known types: %s "
                         "(a typo here would silently validate nothing)"
                         % (field, rules["type"], sorted(_SCHEMA_TYPES)))
        if "enum" in rules:
            enum = rules["enum"]
            if not isinstance(enum, (set, frozenset, list, tuple)) or not enum \
                    or not all(isinstance(x, str) for x in enum):
                raise NotRun("SCHEMA[%r]['enum'] is not a non-empty "
                             "collection of strings: %r" % (field, enum))


def validate_rows(header, rows, schema):
    """Runs header-level and row-level checks. Returns the summary dict
    that is this pattern's whole point: one machine-readable verdict,
    never 'the agent said it looked fine'.

    Raises NotRun if `header` shares not one single column name with the
    declared `schema` (and schema is non-empty). Zero overlap is the
    strongest structural signal that this "header" is not a header at all
    -- typically a headerless CSV whose first data row got treated as the
    header. Reporting it as an ordinary header mismatch would mean every
    unknown-column/duplicate-column violation echoes a raw data value
    (whatever that data row happened to contain) into a field this pattern
    promises never carries raw values -- so it is treated as could-not-
    evaluate instead of a normal, partial header mismatch (a header with
    one typo'd or renamed column still overlaps the rest and is handled by
    check_header below as usual). Also raises NotRun if SCHEMA itself is
    malformed (see check_schema)."""
    check_schema(schema)
    if schema and not (set(schema) & set(header)):
        raise NotRun(
            "header row shares no column name with the %d declared schema "
            "field(s) (%s) -- this looks like a data row was mistaken for "
            "the header (missing header row), so header cells are not "
            "trustworthy enough to report as column names"
            % (len(schema), ", ".join(sorted(schema)))
        )
    invalid_rows = check_header(header, schema)
    positions = _field_positions(header)
    for line, raw_row in rows:
        invalid_rows.extend(validate_row(line, raw_row, header, positions, schema))

    status = "VERIFIED" if not invalid_rows else "FAILED"
    return {
        "status": status,
        "rows": len(rows),
        "invalid": len(invalid_rows),
        "invalid_rows": invalid_rows,
    }


def run_cli(schema, argv=None):
    """Reusable CLI entrypoint. Call this from your own instantiation
    script (see example_instantiation.py) or from this file's __main__.
    Always prints the machine-readable JSON summary line first, then the
    literal final state line the three-state exit contract requires
    (VERIFIED / FAILED / NOT-RUN). Returns the matching exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="path to the CSV artifact to validate")
    a = ap.parse_args(argv)

    try:
        header, rows = load_csv(a.csv)
        summary = validate_rows(header, rows, schema)
    except NotRun as exc:
        print(json.dumps({"status": "NOT-RUN", "rows": 0, "invalid": 0,
                          "invalid_rows": [], "reason": exc.reason}))
        print("NOT-RUN: could not evaluate - %s" % exc.reason)
        return 2

    print(json.dumps(summary))
    if summary["status"] == "VERIFIED":
        print("VERIFIED: %d row(s), 0 violations" % summary["rows"])
        return 0
    print("FAILED: %d violation(s) across %d row(s)" % (summary["invalid"], summary["rows"]))
    return 1


# --- Edit below this line for a standalone drop-in validator ---------------

SCHEMA = {
    # "column_name": {"required": True, "enum": {"a", "b", "c"}},
}

if __name__ == "__main__":
    if not SCHEMA:
        # An empty SCHEMA means zero columns were ever evaluated -- the
        # definition of NOT-RUN, not FAILED. This is the file that DEFINES
        # the three-state contract; its own misconfiguration path must obey
        # it too, exit 2 with a literal NOT-RUN line, never exit 1.
        reason = (
            "SCHEMA is empty. Edit validator_skeleton.py and define your "
            "columns, or import validate_rows()/run_cli() from another "
            "script that supplies its own SCHEMA (see example_instantiation.py)."
        )
        sys.stderr.write(reason + "\n")
        print(json.dumps({"status": "NOT-RUN", "rows": 0, "invalid": 0,
                          "invalid_rows": [], "reason": reason}))
        print("NOT-RUN: could not evaluate - %s" % reason)
        sys.exit(2)
    sys.exit(run_cli(SCHEMA))
