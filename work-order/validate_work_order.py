#!/usr/bin/env python3
"""Deterministic validator for slim work-order cards (CARD-01, 2026-08-19).

Usage:
    python3 validate_work_order.py <path-to-card.yaml>

Exit code 0  -> valid.
Exit code 1  -> invalid; violations printed to stderr, one per line,
                each prefixed with "VIOLATION:" so callers can grep them.
                Internal errors also exit 1 (fail closed): a card the
                validator could not fully evaluate is not a valid card.
Exit code 2  -> the validator itself cannot run (pyyaml missing, usage error).

THE SLIM SCHEMA (closed -- unknown keys are violations, duplicate YAML keys
are rejected; both inherited from the legacy schema's 5th external review):

  goal        non-empty string. What this card changes.
  non_goals   non-empty list of non-empty strings. What it must NOT touch.
  tier        S1 | S2 | S3. Proposed by the agent, RATIFIED BY THE HUMAN --
              the validator checks the value, not the ratification.
  task_type   one of {bugfix, implementation, refactor, config, do-nothing,
              ask-first} (legacy enum preserved).
  done_when   non-empty list of non-empty strings: observable conditions.
  verify      ONE shell command, non-empty, NOT VACUOUS. Deny-list (at
              minimum): empty/whitespace, `true`, `:`, `echo ...` -- a
              command that cannot fail proves nothing. The deny-list is
              applied to the FIRST WORD OF EVERY SEGMENT of the command
              line -- after `||`, `;`, `&&`, `|`, `|&` and a newline, and
              inside quotes (`|| 'tr'"ue"`), behind a group, a redirection,
              an assignment or a `then`/`else`/`do`/`time` -- because
              `pytest -q || true` proves exactly as little as `true`. A
              BACKGROUNDED command (a bare `&` at a command boundary) is
              rejected too: its exit status is discarded. The rule reads
              `verify` as a POSIX/bash command line; the receipt gate runs
              it with `Popen(shell=True)` -- /bin/sh on POSIX, cmd.exe on
              Windows -- so cmd.exe no-ops are outside its reach. Both the
              remaining bypasses and the real commands this
              over-approximation rejects (each with a rewrite) are named in
              work-order/README.md. The validator checks the FIELD, not the
              truth of what the command tests; a technically-real but
              irrelevant command is a human review item.
  repro       required IFF task_type == bugfix (you don't fix what you have
              not reproduced); optional otherwise. When present: the
              ATTACHED reproduction itself as a non-empty string or list of
              non-empty strings (failing test + output, recorded command,
              incident artifact). `repro: true` is a checkbox, not a
              reproduction, and is rejected.

ROUTING INVARIANT (documented here, ENFORCED by the receipt gate reading
`tier`): tier S3 => plan-mode approval before implementation AND a review
pass before close. This validator is preflight; it proves the card is
well-formed before dispatch and never observes execution. Post-execution
binding of the verify command to the actual tree is the receipt gate's job
(the Stop-hook verifier), not this file's.

Legacy schema (observed_failure/hypothesis/allowed/budget/...) was retired
by CARD-01; its fixtures live in fixture/archive/ and its validator in git
history (this file, before 2026-08-19).
"""
import re
import sys

try:
    import yaml
except ImportError:
    print("VIOLATION: pyyaml not installed (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REQUIRED_KEYS = [
    "goal",
    "non_goals",
    "tier",
    "task_type",
    "done_when",
    "verify",
]

# repro is the one conditionally-required key: mandatory iff bugfix.
KNOWN_KEYS = set(REQUIRED_KEYS) | {"repro"}

TIER_ENUM = {"S1", "S2", "S3"}

TASK_TYPE_ENUM = {
    "bugfix",
    "implementation",
    "refactor",
    "config",
    "do-nothing",
    "ask-first",
}

# Vacuous first tokens: commands that exit 0 without testing anything.
# `true` and `:` are shell no-ops; `echo ...` prints success it never earned.
VACUOUS_FIRST_TOKENS = {"true", ":", "echo"}

# WHERE the deny-list is applied: to the first word of EVERY
# operator-separated segment of `verify`, not only to the first word of the
# command line -- `pytest -q || true` proves exactly as little as `true`.
# This is deliberately NOT a shell parser (no new dependency, no quote /
# comment / heredoc / `$( )` parsing); the shapes it over-rejects and the
# rewrite for each are named in work-order/README.md.
#
# Longest operators first so `|&`, `&&` and `||` win over `|`.
SEGMENT_OPERATORS = re.compile(r"\|&|&&|\|\||;|\||\n")

# A backslash-newline pair is a line continuation: the shell joins the lines
# into one word, so `tr\` + newline + `ue` IS `true`.
LINE_CONTINUATION = re.compile(r"\\\n")

# A bare `&` at a command boundary backgrounds the command and discards its
# exit status. Excluded: the operators that merely contain `&` (`&&`, `|&`,
# `>&`, `<&`, `&>`) and a `&` inside a word (`"a&b"`, `?a=1&b=2`, `&#39;`).
# `wait $!` would collect the status; the rule does not read that far, so
# every bare `&` is rejected (rewrite documented in the piece README).
BACKGROUND_AMP = re.compile(r"(?<![&|<>])&(?![&>])(?=[\s)]|$)")

# Reserved words that only introduce the real command behind them.
# `if`, `elif`, `while`, `until` and `!` are NOT here, on purpose: a no-op
# CONDITION is a named residual, and skipping `!` could not expose a
# cannot-fail no-op (`! true`, `! :`, `! echo x` all exit 1).
LEADING_RESERVED_WORDS = {"then", "else", "do", "time"}

# Redirection operators written as their own word: each takes the word after.
BARE_REDIRECTIONS = {">", ">>", "<", "2>", ">&", "<&", "&>"}

# A redirection with its target glued on (`>x`, `2>&1`, `&>x`, `<x`).
REDIRECTION_WORD = re.compile(r"(?:&>|[0-9]*(?:>>|>&|>|<&|<))\S")

# A leading `NAME=value` / `NAME+=value` assignment prefix.
ASSIGNMENT_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")

# Stripped from a segment's edges: a group's `(`, `)` and `{` never belong to
# the command (`{ true; }`, `( true )`, `(pytest -q || true)` all expose
# `true`). `}` is NOT stripped -- in valid bash it never glues to a token, so
# a lone `}` segment is an ordinary non-denied word like `fi`, `done`, `esac`.
SEGMENT_EDGE_CHARS = " \t\r\n\f\v(){"


def _segment_first_word(segment):
    """Return the segment's first real word, lowercased and normalized.

    Returns "" when the segment carries no command at all: empty (a trailing
    `;`, an operator followed by a newline, the trailing newline of a block
    scalar) or only reserved words, redirections and assignments. An empty
    segment is skipped, never a violation.
    """
    words = segment.split()
    while words:
        word = words[0]
        if word.lower() in LEADING_RESERVED_WORDS:
            words.pop(0)
        elif word in BARE_REDIRECTIONS:
            words.pop(0)            # the operator ...
            if words:
                words.pop(0)        # ... and the target word it takes
        elif REDIRECTION_WORD.match(word):
            words.pop(0)
        elif ASSIGNMENT_WORD.match(word):
            words.pop(0)
        else:
            break
    if not words:
        return ""
    token = words[0].lower()
    for quote in ('"', "'", "\\"):   # `'tr'"ue"` and `\true` are both `true`
        token = token.replace(quote, "")
    for cut in ("<", ">"):           # `true>/dev/null` exposes `true`
        at = token.find(cut)
        if at != -1:
            token = token[:at]
    return token


def vacuity_violations(verify):
    """Return the vacuity violations of one `verify` command line.

    Empty list == not vacuous. Every string operation here is total: a
    malformed or hostile value yields a VIOLATION or nothing, never a raise.
    """
    text = verify.strip()
    line = LINE_CONTINUATION.sub("", text)
    found = []

    # Reported ALONE, not alongside a segment violation: that is what makes a
    # slip in this regex visible. `>& 2`, `<& 0` and `&> /dev/null` have no
    # clean case of their own, so if one of the exclusions above were dropped,
    # this line would replace the segment line the bare-redirection fixture
    # locks -- and its runner reports it as red for the WRONG reason instead
    # of quietly passing.
    if BACKGROUND_AMP.search(line):
        found.append(
            f"verify={text!r} is vacuous (backgrounded command): a bare `&` "
            "at a command boundary discards the exit status of what it "
            "starts -- the card would close on a result nobody collected"
        )
        return found

    for raw_segment in SEGMENT_OPERATORS.split(line):
        segment = raw_segment.strip(SEGMENT_EDGE_CHARS)
        token = _segment_first_word(segment)
        if token in VACUOUS_FIRST_TOKENS:
            found.append(
                f"verify={text!r} is vacuous (deny-list: true, :, echo ...): "
                f"segment {segment!r} begins with {token!r} -- a command "
                "that cannot fail proves nothing"
            )
            break

    return found


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently
    keeping the last occurrence (a second, laxer `verify:` at the end of
    the file would override the first without a trace)."""


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError:
            raise yaml.constructor.ConstructorError(
                None, None,
                "unhashable mapping key %r" % (key,), key_node.start_mark)
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None,
                "duplicate key %r (yaml would silently keep the last "
                "occurrence)" % (key,), key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates)


def _is_nonempty_str(v):
    return isinstance(v, str) and bool(v.strip())


def _is_str_list(v):
    return (isinstance(v, list) and len(v) > 0
            and all(_is_nonempty_str(x) for x in v))


def _empty(v):
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, (list, dict)) and len(v) == 0:
        return True
    return False


def validate(doc):
    """Return a list of violation strings. Empty list == valid."""
    violations = []

    if not isinstance(doc, dict):
        violations.append("document root is not a mapping (YAML object)")
        return violations

    # 1. closed schema: required keys present, unknown rejected
    unknown = sorted(k for k in doc if k not in KNOWN_KEYS)
    if unknown:
        violations.append(
            f"unknown top-level keys {unknown}: the schema is closed -- "
            "a key the validator does not know is a key it cannot enforce"
        )
    for key in REQUIRED_KEYS:
        if key not in doc:
            violations.append(f"missing required key: {key}")

    # 2. a present-but-empty required value contains nothing (containment
    # theater); named as such, and its type check is skipped.
    empty_keys = {k for k in REQUIRED_KEYS if k in doc and _empty(doc.get(k))}
    for key in REQUIRED_KEYS:
        if key in empty_keys:
            violations.append(
                f"empty value for required key: {key} "
                "(a present key with a null value contains nothing)"
            )

    def present(key):
        return key in doc and key not in empty_keys

    # 3. goal: non-empty string
    if present("goal") and not _is_nonempty_str(doc["goal"]):
        violations.append(f"goal={doc['goal']!r} is not a string")

    # 4. non_goals / done_when: non-empty lists of non-empty strings
    for key in ("non_goals", "done_when"):
        if present(key) and not _is_str_list(doc[key]):
            violations.append(
                f"{key}={doc[key]!r} is not a non-empty list of non-empty "
                "strings"
            )

    # 5. tier: closed enum, human-ratified (the value is checkable; the
    # ratification is not -- it is a human act by design)
    if present("tier"):
        tier = doc["tier"]
        if not isinstance(tier, str) or tier not in TIER_ENUM:
            violations.append(
                f"tier={tier!r} is not one of {sorted(TIER_ENUM)} "
                "(proposed by the agent, ratified by the human)"
            )

    # 6. task_type: string from the enum (a mistyped value is a violation,
    # never a traceback -- fail closed with a named reason)
    task_type = None
    if present("task_type"):
        task_type = doc["task_type"]
        if not isinstance(task_type, str):
            violations.append(
                f"task_type={task_type!r} is not a string (must be one of "
                f"{sorted(TASK_TYPE_ENUM)})"
            )
            task_type = None
        elif task_type not in TASK_TYPE_ENUM:
            violations.append(
                f"task_type={task_type!r} is not one of "
                f"{sorted(TASK_TYPE_ENUM)}"
            )

    # 7. verify: one non-empty, non-vacuous shell command
    if present("verify"):
        verify = doc["verify"]
        if not _is_nonempty_str(verify):
            violations.append(
                f"verify={verify!r} is not a non-empty string "
                "(one real shell command is the contract)"
            )
        else:
            violations.extend(vacuity_violations(verify))

    # 8. repro: required iff bugfix; when present, the attached reproduction
    # itself -- a non-empty string or list of non-empty strings. A boolean
    # is a checkbox, not a reproduction.
    if task_type == "bugfix" and "repro" not in doc:
        violations.append(
            "task_type=bugfix requires repro: attach the failing test / "
            "recorded command / incident artifact before any agent edits "
            "code (you don't fix what you have not reproduced)"
        )
    if "repro" in doc:
        repro = doc["repro"]
        if not (_is_nonempty_str(repro) or _is_str_list(repro)):
            violations.append(
                f"repro={repro!r} is not a non-empty string or list of "
                "non-empty strings: a checkbox is not a reproduction -- "
                "attach the artifact itself"
            )

    return violations


def main(argv):
    if len(argv) != 2:
        print("usage: validate_work_order.py <path-to-card.yaml>", file=sys.stderr)
        return 2

    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.load(f, Loader=StrictLoader)
    except FileNotFoundError:
        print(f"VIOLATION: file not found: {path}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"VIOLATION: not valid YAML: {e}", file=sys.stderr)
        return 1

    # Fail closed: an internal error means the document was NOT fully
    # validated, and an unvalidated card is not a valid one. A named
    # VIOLATION line, never a bare traceback.
    try:
        violations = validate(doc)
    except Exception as e:  # noqa: BLE001 -- fail-closed safety net
        print(
            "VIOLATION: validator internal error (fail-closed): "
            f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}", file=sys.stderr)
        return 1

    print(f"OK: {path} is a valid card")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
