"""Fixture runner for the deterministic-validator pattern.

Proves the gate actually gates, red and green, for every violation code
the skeleton knows about, plus the NOT-RUN path (an artifact it could not
evaluate at all — a checker that could not look must never report a pass):

  - clean.csv              -> 0 violations, exit 0, VERIFIED
  - violating.csv          -> enum + missing violations, exit 1, FAILED
  - extra_cell.csv         -> undeclared extra cell, exit 1, FAILED
  - missing_cell.csv       -> a data row SHORTER than the header, truncating
                              a non-required column (so nothing else would
                              flag it), exit 1, FAILED with missing-cell
                              named by the real header column name
  - duplicate_column.csv   -> duplicate-column + enum violations, exit 1, FAILED
  - typo_header.csv        -> ONE typo'd column ("prio") still overlaps the
                              schema, so it takes the normal FAILED path with
                              missing-column + unknown-column naming the real
                              disputed columns, exit 1 -- never NOT-RUN
  - (in-process)           -> "type": "int" via validate_rows() with a one-off
                              schema ("12_3" parses in CPython's int() but is
                              rejected by the strict ASCII regex), FAILED
  - empty.csv              -> no header row to evaluate, exit 2, NOT-RUN
  - unterminated_quote.csv -> quoted field never closes before EOF (the rest
                              of the file would otherwise vanish silently
                              into one field), exit 2, NOT-RUN
  - headerless.csv         -> no header row at all, so the first data row
                              got read as the header (zero overlap with the
                              declared schema) -- exit 2, NOT-RUN, and never
                              echoes that data row's raw values back
  - nul_byte.csv           -> a data cell carries an embedded NUL byte (valid
                              UTF-8, so decoding alone never catches it) --
                              binary garbage / wrong encoding / truncated
                              write, exit 2, NOT-RUN, never VERIFIED
  - standalone skeleton with its shipped placeholder empty SCHEMA -- exit 2,
    NOT-RUN (checked separately below, not against example_instantiation.py)

Run:
    py -3 fixture/run_fixture.py
Exits 0 if every case behaves as expected, non-zero otherwise (so this
file itself can sit in CI as the piece's own regression test).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXAMPLE = os.path.join(ROOT, "example_instantiation.py")
SKELETON = os.path.join(ROOT, "validator_skeleton.py")


def run(csv_path):
    result = subprocess.run(
        [sys.executable, EXAMPLE, "--csv", csv_path],
        capture_output=True, text=True,
    )
    json_line = next(l for l in result.stdout.splitlines() if l.strip().startswith("{"))
    summary = json.loads(json_line)
    return result.returncode, summary, result.stdout


def run_skeleton_standalone(csv_path):
    """Runs validator_skeleton.py directly (not via example_instantiation.py)
    so the shipped placeholder empty SCHEMA is exercised for real."""
    result = subprocess.run(
        [sys.executable, SKELETON, "--csv", csv_path],
        capture_output=True, text=True,
    )
    json_line = next(l for l in result.stdout.splitlines() if l.strip().startswith("{"))
    summary = json.loads(json_line)
    return result.returncode, summary, result.stdout


def expect(failures, label, condition, message):
    if not condition:
        failures.append("%s: %s" % (label, message))


def main():
    failures = []

    code, summary, out = run(os.path.join(HERE, "clean.csv"))
    print("clean.csv -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "clean.csv", code == 0, "expected exit 0, got %d" % code)
    expect(failures, "clean.csv", summary["invalid"] == 0,
           "expected invalid=0, got %d" % summary["invalid"])
    expect(failures, "clean.csv", "VERIFIED" in out, "expected a VERIFIED summary line")

    code, summary, out = run(os.path.join(HERE, "violating.csv"))
    print("violating.csv -> exit=%d %s" % (code, json.dumps(summary)))
    checks = {v["check"] for v in summary["invalid_rows"]}
    expect(failures, "violating.csv", code == 1, "expected exit 1, got %d" % code)
    expect(failures, "violating.csv", "enum" in checks,
           "expected an 'enum' violation, got checks=%s" % checks)
    expect(failures, "violating.csv", "missing" in checks,
           "expected a 'missing' violation, got checks=%s" % checks)
    expect(failures, "violating.csv", "FAILED" in out, "expected a FAILED summary line")

    code, summary, out = run(os.path.join(HERE, "extra_cell.csv"))
    print("extra_cell.csv -> exit=%d %s" % (code, json.dumps(summary)))
    checks = {v["check"] for v in summary["invalid_rows"]}
    expect(failures, "extra_cell.csv", code == 1, "expected exit 1, got %d" % code)
    expect(failures, "extra_cell.csv", "extra-cell" in checks,
           "expected an 'extra-cell' violation, got checks=%s" % checks)
    expect(failures, "extra_cell.csv", "FAILED" in out, "expected a FAILED summary line")

    code, summary, out = run(os.path.join(HERE, "missing_cell.csv"))
    print("missing_cell.csv -> exit=%d %s" % (code, json.dumps(summary)))
    checks = {v["check"] for v in summary["invalid_rows"]}
    fields = {v["field"] for v in summary["invalid_rows"]}
    expect(failures, "missing_cell.csv", code == 1, "expected exit 1, got %d" % code)
    expect(failures, "missing_cell.csv", "missing-cell" in checks,
           "expected a 'missing-cell' violation (the truncated column is NOT "
           "required, so nothing else would flag it), got checks=%s" % checks)
    expect(failures, "missing_cell.csv", "notes" in fields,
           "expected the shortfall named by the real header column name "
           "('notes'), got fields=%s" % fields)
    expect(failures, "missing_cell.csv", "FAILED" in out, "expected a FAILED summary line")

    code, summary, out = run(os.path.join(HERE, "duplicate_column.csv"))
    print("duplicate_column.csv -> exit=%d %s" % (code, json.dumps(summary)))
    checks = {v["check"] for v in summary["invalid_rows"]}
    expect(failures, "duplicate_column.csv", code == 1, "expected exit 1, got %d" % code)
    expect(failures, "duplicate_column.csv", "duplicate-column" in checks,
           "expected a 'duplicate-column' violation, got checks=%s" % checks)
    expect(failures, "duplicate_column.csv", "enum" in checks,
           "expected the duplicate's bad enum value to still be caught regardless of "
           "column order, got checks=%s" % checks)
    expect(failures, "duplicate_column.csv", "missing-column" not in checks,
           "a duplicate column must never be misreported as a missing-column, "
           "got checks=%s" % checks)

    code, summary, out = run(os.path.join(HERE, "typo_header.csv"))
    print("typo_header.csv -> exit=%d %s" % (code, json.dumps(summary)))
    checks = {v["check"] for v in summary["invalid_rows"]}
    fields = {v["field"] for v in summary["invalid_rows"]}
    expect(failures, "typo_header.csv", code == 1,
           "a header with ONE typo'd column still overlaps the schema and "
           "must take the normal FAILED path, never NOT-RUN; got exit %d" % code)
    expect(failures, "typo_header.csv", "missing-column" in checks and "unknown-column" in checks,
           "expected missing-column + unknown-column naming the disputed "
           "columns, got checks=%s" % checks)
    expect(failures, "typo_header.csv", "priority" in fields and "prio" in fields,
           "expected the real disputed column names ('priority' missing, "
           "'prio' unknown), got fields=%s" % fields)

    # In-process case: "type": "int" has no column in the example schema, so
    # it is exercised directly against validate_rows() with a one-off schema.
    sys.path.insert(0, ROOT)
    from validator_skeleton import validate_rows  # noqa: E402
    type_summary = validate_rows(
        ["item_id", "count"],
        [(2, ["ITEM-901", "12_3"])],
        {"item_id": {"required": True},
         "count": {"required": True, "type": "int"}},
    )
    print("in-process type:int -> %s" % json.dumps(type_summary))
    type_checks = {v["check"] for v in type_summary["invalid_rows"]}
    expect(failures, "type:int", type_summary["status"] == "FAILED",
           "expected FAILED, got %s" % type_summary["status"])
    expect(failures, "type:int", "type" in type_checks,
           "expected a 'type' violation ('12_3' is int()-parseable in "
           "CPython but not a portable integer -- the strict ASCII regex "
           "must reject it), got checks=%s" % type_checks)

    # In-process case: a TYPO'D SCHEMA ("integer" instead of "int") used to
    # fall through to the no-op default, so invalid data could be VERIFIED
    # by a checker that silently was not checking (5th external review,
    # 2026-08-18). A malformed schema is a misconfigured validator: NotRun.
    from validator_skeleton import NotRun  # noqa: E402
    try:
        validate_rows(
            ["item_id", "count"],
            [(2, ["ITEM-901", "not-a-number"])],
            {"item_id": {"required": True},
             "count": {"required": True, "type": "integer"}},
        )
        print("in-process schema-typo -> NO EXCEPTION (bug)")
        expect(failures, "schema-typo", False,
               "expected NotRun for unknown schema type 'integer', got a "
               "normal verdict (the typo'd rule silently checked nothing)")
    except NotRun as exc:
        print("in-process schema-typo -> NotRun: %s" % exc.reason)
        expect(failures, "schema-typo", "integer" in exc.reason,
               "NotRun reason should name the offending type, got: %s"
               % exc.reason)

    code, summary, out = run(os.path.join(HERE, "empty.csv"))
    print("empty.csv -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "empty.csv", code == 2, "expected exit 2, got %d" % code)
    expect(failures, "empty.csv", summary["status"] == "NOT-RUN",
           "expected status NOT-RUN, got %s" % summary.get("status"))
    expect(failures, "empty.csv", "NOT-RUN" in out, "expected a NOT-RUN summary line")

    code, summary, out = run(os.path.join(HERE, "unterminated_quote.csv"))
    print("unterminated_quote.csv -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "unterminated_quote.csv", code == 2,
           "expected exit 2 (a quote that never closes before EOF must never "
           "let the rest of the file silently vanish and report VERIFIED), "
           "got %d" % code)
    expect(failures, "unterminated_quote.csv", summary["status"] == "NOT-RUN",
           "expected status NOT-RUN, got %s" % summary.get("status"))
    expect(failures, "unterminated_quote.csv", summary["rows"] == 0,
           "expected 0 rows counted as evaluated, got %d" % summary["rows"])
    expect(failures, "unterminated_quote.csv", "NOT-RUN" in out,
           "expected a NOT-RUN summary line")

    code, summary, out = run(os.path.join(HERE, "headerless.csv"))
    print("headerless.csv -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "headerless.csv", code == 2,
           "expected exit 2 (a data row mistaken for the header must never "
           "be validated as if it were real column names), got %d" % code)
    expect(failures, "headerless.csv", summary["status"] == "NOT-RUN",
           "expected status NOT-RUN, got %s" % summary.get("status"))
    dumped = json.dumps(summary)
    expect(failures, "headerless.csv", "jane.doe" not in dumped and "123-45-6789" not in dumped,
           "the raw data value from the mistaken header row must never appear "
           "in the summary -- got %s" % dumped)
    expect(failures, "headerless.csv", "NOT-RUN" in out,
           "expected a NOT-RUN summary line")

    code, summary, out = run(os.path.join(HERE, "nul_byte.csv"))
    print("nul_byte.csv -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "nul_byte.csv", code == 2,
           "expected exit 2 (an embedded NUL byte means the artifact is not "
           "trustworthy text -- binary garbage, wrong encoding, or a "
           "truncated write -- and must be NOT-RUN, never VERIFIED), "
           "got %d" % code)
    expect(failures, "nul_byte.csv", summary["status"] == "NOT-RUN",
           "expected status NOT-RUN, got %s" % summary.get("status"))
    expect(failures, "nul_byte.csv", "NOT-RUN" in out,
           "expected a NOT-RUN summary line")

    code, summary, out = run_skeleton_standalone(os.path.join(HERE, "clean.csv"))
    print("standalone skeleton (empty SCHEMA) -> exit=%d %s" % (code, json.dumps(summary)))
    expect(failures, "standalone skeleton", code == 2,
           "an unconfigured validator (no SCHEMA) evaluated zero columns -- "
           "that is NOT-RUN, not FAILED (exit 1) and not a silent pass; "
           "got exit %d" % code)
    expect(failures, "standalone skeleton", summary["status"] == "NOT-RUN",
           "expected status NOT-RUN, got %s" % summary.get("status"))
    expect(failures, "standalone skeleton", "NOT-RUN" in out,
           "expected a NOT-RUN summary line")

    if failures:
        print("FIXTURE FAILED:")
        for f in failures:
            print("  - " + f)
        return 1

    print("FIXTURE OK: clean case green; enum/missing, extra-cell, "
          "missing-cell, duplicate-column, typo'd-header "
          "(missing/unknown-column), and type:int cases red for the right "
          "reasons; empty-file, unterminated-quote, headerless-CSV, "
          "NUL-byte, and unconfigured-skeleton cases all correctly "
          "reported as NOT-RUN instead of a false pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
