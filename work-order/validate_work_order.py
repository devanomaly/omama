#!/usr/bin/env python3
"""Deterministic validator for slim work-order cards (CARD-01, 2026-08-19).

Usage:
    py -3 validate_work_order.py <path-to-card.yaml>

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
              command that cannot fail proves nothing. The validator checks
              the FIELD, not the truth of what the command tests; a
              technically-real but irrelevant command is a human review item.
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
            first_token = verify.strip().split()[0].lower()
            if first_token in VACUOUS_FIRST_TOKENS:
                violations.append(
                    f"verify={verify.strip()!r} is vacuous (deny-list: "
                    "true, :, echo ...): a command that cannot fail "
                    "proves nothing"
                )

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
