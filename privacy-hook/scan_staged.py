#!/usr/bin/env python3
"""privacy-hook / scan_staged.py

A pre-commit privacy scanner with a DELIBERATELY NARROW claim. It blocks
staged content on four layers:

  1. deny_filenames -- a regex matched against every component of the
     staged path (config: <REPO_ROOT>/privacy-deny.json).
  2. the literal token list -- one literal per line in the file that
     config points at (`tokens_file`): client codenames, internal
     hostnames, project aliases. Strings no off-the-shelf scanner can
     know about.
  3. deny_regexes -- team-owned content regexes, same config.
  4. a SHORT list of built-in credential shapes that are structurally
     unmistakable: AWS key id, GitHub token formats, PEM / PuTTY
     private-key headers, credentials embedded in a URL, plus two vendor
     key prefixes (Anthropic, Slack).

Layers 1 and 2 are the reason this hook exists NEXT TO gitleaks /
trufflehog instead of pretending to replace them: no maintained ruleset
knows your client's codename or your jump host's internal name.

WHAT THIS HOOK DELIBERATELY DOES NOT DO ANY MORE
------------------------------------------------
Generic "<secret-ish key> = <high-entropy value>" detection. It was here,
it was hardened twice, and the measurement that killed it is this: a
fresh attacker produced 16 working bypasses AND 16 false positives on the
SAME rule, and each patch traded one class for the other at roughly 1:1.

  * every bypass was a secret whose punctuation the value class did not
    model (a leading `{` or `(`, an embedded `<`, `%`, `'`, `,` or a
    backtick, a URL-valued secret);
  * every false positive was ordinary repo content: docker-compose
    local-dev URLs, README quickstart blocks, `.env.example`
    placeholders, `password: form.passwordConfirmation` in JS, Bitnami
    chart defaults, Terraform `random_password` references.

Entropy-based generic secret detection is a solved problem OUTSIDE this
file (gitleaks, trufflehog: maintained, tuned, benchmarked rulesets) and
an unsolved one inside a hand-rolled regex. And a hook that blocks
`docker-compose.yml` gets uninstalled -- which is total loss of
protection, not partial.

So: no generic assignment rule, no per-segment entropy heuristic, no
placeholder vocabulary, no warn-but-allow mode. In this hook a block is a
block. Run gitleaks in CI for the generic half.

Quiet by design: findings report a rule id + the staged path only, never
the matched text and never surrounding context, so the hook's own output
is safe to paste into a Slack thread or a CI log.

No client-specific, project-specific or personal-path literals live in
this file. Everything an adopting team customizes lives in
privacy-deny.json (and the tokens file it points at).

Usage: invoked with no arguments by the `pre-commit` wrapper in
.git/hooks/ of the adopting repo. This script itself is committed at the
REPO ROOT (see README: Como adotar, step 1) -- a different directory from
the wrapper -- and locates itself and its config via `git rev-parse
--show-toplevel` (repo_root(), below), not via its own path. Exits 0
(allow commit) or 1 (block commit).
"""
import json
import os
import re
import subprocess
import sys

# --- built-in credential shapes ----------------------------------------
# Every pattern here is a STRUCTURAL, vendor-documented format: a fixed
# prefix plus a fixed length, or a fixed header line. That is why they
# have a near-zero false-positive rate and why they survived the scope
# cut. They are NOT examples of real secrets and none of them can match
# its own source line.
#
# The bar for adding a pattern here: a documented, fixed shape whose
# match is a credential by construction. "A long random-looking string
# next to a suggestive key name" does NOT meet that bar -- that is the
# rule this file used to have and no longer does.
BUILTIN_PATTERNS = [
    # AWS long-term (AKIA), STS/temporary (ASIA), and the other documented
    # AWS key-id prefixes. ASIA is what every assumed-role credential
    # looks like, so restricting this to AKIA covered the rarer half.
    ("aws-access-key", re.compile(rb"(?:AKIA|ASIA|ABIA|ACCA|A3T[A-Z0-9])[0-9A-Z]{16}")),
    # Classic (ghp_/gho_/ghu_/ghs_/ghr_) and fine-grained (github_pat_)
    # GitHub tokens. github_pat_ is the format GitHub issues by default
    # since 2022.
    ("github-token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36}")),
    ("github-pat", re.compile(rb"github_pat_[A-Za-z0-9_]{40,}")),
    ("anthropic-key", re.compile(rb"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("slack-token", re.compile(rb"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private-key-block", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("putty-private-key", re.compile(rb"PuTTY-User-Key-File-\d")),
    # Credentials in a URL. `(?i)` because an uppercased scheme is common
    # in docs and .env samples; the password class allows `/` because real
    # passwords contain it. Groups 1 and 2 are user and password, and they
    # exist for one reason: the local-dev allowlist below.
    ("url-credentials",
     re.compile(rb"(?i)[a-z][a-z0-9+.\-]*://([^/\s:@]+):([^@\s]+)@")),
]

# --- the allowlist: canonical non-secrets ------------------------------
#
# An allowlist is a DELIBERATE, REVIEWABLE BYPASS. It is short, it is
# literal (no regex, no fuzzy prefix matching), every entry says why it is
# safe on the line above it, and a team that disagrees with an entry
# deletes the line. It exists because the alternative -- a "smart" test
# for what looks like a documentation example or a local-dev credential --
# is exactly the kind of heuristic this piece just finished removing.
#
# Scope: the allowlist only ever suppresses a BUILT-IN pattern match. It
# never touches deny_filenames, deny_regexes or the literal token list:
# what the team declares, blocks. No exceptions, no inline suppression
# comment anywhere in this piece.

# Matched text that is a published documentation example, not a
# credential. Compared byte-exactly against the whole match.
ALLOWLIST_LITERALS = frozenset([
    # AWS's own documentation example access key id. Appears hard-coded in
    # moto / localstack / boto3 test suites worldwide; is not a live key.
    b"AKIAIOSFODNN7EXAMPLE",
    # AWS's own documentation example secret access key. Listed for
    # completeness and reviewability. HONEST NOTE, so nobody mistakes this
    # line for protection: no built-in pattern above matches this string
    # today (there is no AWS secret-key shape in the list, because a
    # 40-char base64-ish run is not a structurally unmistakable format),
    # so this entry currently suppresses nothing. It is here so the pair
    # reads as a pair in review.
    b"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
])

# `user:password` pairs that are published defaults of a local-dev
# service, compared byte-exactly (lowercased) against the credential pair
# extracted from a URL match. These five lines are why `url-credentials`
# stopped blocking `docker-compose.yml`, the README quickstart and the
# setup docs -- five of the sixteen measured false positives.
LOCAL_DEV_URL_CREDENTIALS = frozenset([
    # the postgres image's conventional local pair; the single most-copied
    # DATABASE_URL line in the polyglot ecosystem
    b"postgres:postgres",
    # RabbitMQ's published default account, verbatim from its own docs
    b"guest:guest",
    # verbatim from the mongo image's Docker Hub README
    b"root:example",
    # the canonical throwaway basic-auth pair in curl/healthcheck examples
    b"admin:admin",
    # the other canonical throwaway pair, common in tutorial connection
    # strings
    b"user:password",
])
# STATED COST of the pair allowlist, so it is not a silent hole: the pair
# is matched WITHOUT looking at the host, so one of these pairs against a
# PRODUCTION hostname also commits clean. That is accepted: a production
# database whose password is `postgres` is already lost, and a host
# heuristic (localhost / compose-service-name / private range) is
# precisely the kind of guessing this file no longer does. Change one
# character of either half of the pair and it blocks again -- see the
# `allowlist-url-pair-one-side-changed` fixture case.
#
# (Deliberately no example URL literal in this comment: a full
# credential-bearing URL written out here would make this file's own
# committability depend on its own allowlist. Verified: the only
# built-in match anywhere in this file is the allowlisted AWS
# documentation key id.)

DEFAULT_CONFIG_NAME = "privacy-deny.json"


def builtin_hit(view):
    """Rule id of the first built-in pattern match the allowlist does not
    explain away, or None.

    Iterates EVERY match of every pattern (not just the first) so that one
    allowlisted occurrence in a file cannot shield a real credential
    elsewhere in the same file."""
    for rule, rx in BUILTIN_PATTERNS:
        for m in rx.finditer(view):
            if rule == "url-credentials":
                pair = (m.group(1) + b":" + m.group(2)).lower()
                if pair in LOCAL_DEV_URL_CREDENTIALS:
                    continue
            elif m.group(0) in ALLOWLIST_LITERALS:
                continue
            return rule
    return None


# --- encoding normalization --------------------------------------------
# Every layer below operates on bytes. A file saved as UTF-16 (the default
# of PowerShell's `Out-File -Encoding unicode` and of several Windows
# exporters) contains the same secret in plain sight for any editor, but
# NUL-interleaved for a byte matcher -- which used to defeat all four
# layers at once with a single save. So each blob is scanned as its raw
# bytes AND, when it decodes as a wide Unicode encoding, as the UTF-8
# re-encoding of that text.
#
# This layer is KEPT by the scope cut: it serves the built-in patterns,
# the deny_regexes and the literal token list, not only the rule that was
# removed. Its two known gaps (blobs over WIDE_MAX_BLOB, and wide text
# with no NUL byte in the probe window) are recorded in the README failure
# map, not fixed here.
WIDE_BOMS = [
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]
WIDE_CODECS = ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"]
# Trying every codec on a large binary blob would be wasted work; NUL bytes
# are the signal that a wide encoding is even plausible.
WIDE_PROBE_BYTES = 4096
WIDE_MAX_BLOB = 8 * 1024 * 1024


def _decoded_view(data, codec):
    try:
        text = data.decode(codec)
    except (UnicodeDecodeError, LookupError, ValueError):
        return None
    if not text:
        return None
    # Reject decodes that produced mostly junk -- a real text file is
    # overwhelmingly printable.
    bad = sum(1 for c in text[:WIDE_PROBE_BYTES]
              if c not in "\t\r\n" and ord(c) < 32)
    if bad > max(4, len(text[:WIDE_PROBE_BYTES]) // 20):
        return None
    return text.encode("utf-8", "replace")


def text_views(data):
    """Byte views of `data` that must all be scanned: the raw bytes, plus
    a UTF-8 re-encoding for each wide-Unicode reading that succeeds."""
    views = [data]
    if not data or len(data) > WIDE_MAX_BLOB:
        return views
    probe = data[:WIDE_PROBE_BYTES]
    if b"\x00" not in probe:
        return views
    seen = {data}
    codecs = []
    for bom, codec in WIDE_BOMS:
        if data.startswith(bom):
            codecs.append(codec)
            break
    for codec in WIDE_CODECS:
        if codec not in codecs:
            codecs.append(codec)
    for codec in codecs:
        view = _decoded_view(data, codec)
        if view and view not in seen:
            seen.add(view)
            views.append(view)
    return views


def repo_root():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                        capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("BLOCKED hook-error not-a-git-repo\n")
        sys.exit(1)
    return r.stdout.strip()


def load_config(root):
    """Loads <root>/privacy-deny.json. Missing OR malformed config is a
    hard failure (fail closed, not silently permissive) -- the point of
    this hook is that the deny-list is always in force.

    Every failure path prints the same shape as a content finding
    (`BLOCKED <rule> <relative path>`) and nothing else: no absolute path
    (it carries the dev's home directory and username) and no Python
    traceback (it carries interpreter install paths)."""
    path = os.path.join(root, DEFAULT_CONFIG_NAME)
    if not os.path.isfile(path):
        sys.stderr.write(
            "BLOCKED hook-error missing-config %s (expected at the repo "
            "root; see README: Como adotar)\n" % DEFAULT_CONFIG_NAME)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("top level must be an object")

        deny_regexes = []
        for entry in cfg.get("deny_regexes") or []:
            deny_regexes.append(
                (entry["id"], re.compile(entry["pattern"].encode("utf-8"))))

        deny_filenames = [re.compile(p, re.IGNORECASE)
                          for p in cfg.get("deny_filenames") or []]
    except Exception:
        sys.stderr.write(
            "BLOCKED hook-error bad-config %s (unreadable, not valid JSON, "
            "or a bad deny_regexes/deny_filenames entry)\n"
            % DEFAULT_CONFIG_NAME)
        sys.exit(1)

    tokens = []
    tokens_file = cfg.get("tokens_file")
    if tokens_file:
        tpath = os.path.join(root, tokens_file)
        if os.path.isfile(tpath):
            try:
                with open(tpath, "rb") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith(b"#"):
                            tokens.append(line)
            except OSError:
                sys.stderr.write(
                    "BLOCKED hook-error bad-tokens-file %s\n" % tokens_file)
                sys.exit(1)
        else:
            # A configured-but-missing tokens file is a config error, not a
            # silent no-op -- fail closed so the deny-list can't quietly go
            # dark because a file was renamed or forgotten during checkout.
            sys.stderr.write(
                "BLOCKED hook-error missing-tokens-file %s\n" % tokens_file)
            sys.exit(1)

    return deny_regexes, deny_filenames, tokens, tokens_file


# Which staged change kinds must be scanned. The rule is "every path that
# will EXIST in the resulting commit with content this hook has not yet
# vetted", so the filter is derived from that, not from habit:
#   A (added)       -- new path, new content.                     scan
#   C (copied)      -- new path, content cloned from elsewhere.   scan
#   M (modified)    -- existing path, new content.                scan
#   R (renamed)     -- `git mv innocent.txt .env` reports as R. The
#                      destination path is new and its basename has never
#                      been checked.                              scan
#   T (typechange)  -- e.g. regular file -> symlink. Same path, but a
#                      different blob (a symlink's blob is its target
#                      path), so the content check must re-run.   scan
# Deliberately excluded:
#   D (deleted)     -- the path will NOT exist in the commit, so there is
#                      nothing sensitive to leak; worse, `git show :path`
#                      has no stage-0 entry for it and would raise a
#                      bogus `unreadable-staged-blob` block on every
#                      delete.
#   U (unmerged)    -- git itself refuses to commit with unresolved
#                      conflicts, so this filter can never be the thing
#                      that lets an unmerged path through; including it
#                      would only produce bogus `unreadable-staged-blob`
#                      blocks (no stage-0 entry mid-conflict).
STAGED_CHANGE_FILTER = "ACMRT"

# Index entries that have NO blob to read. `--diff-filter=ACMRT` reports a
# submodule pointer (gitlink, mode 160000) like any other path, but
# `git show :<path>` has nothing to hand back -- which made every commit
# that moved a submodule pointer fail with `unreadable-staged-blob`, in
# every repo that uses submodules, with no workaround but `--no-verify`.
# A gitlink is a 20-byte commit id: there is no content in it to leak, so
# it is skipped rather than blocked. `unreadable-staged-blob` stays a hard
# block for everything else -- that path is the fail-closed branch for a
# blob the hook genuinely could not read.
GITLINK_MODE = "160000"


def staged_entries():
    """[(path, dst_mode)] for every staged change the filter selects.

    Uses `--raw -z` (not `--name-only`) precisely to get the destination
    mode, which is the only way to tell a gitlink from a file."""
    r = subprocess.run(
        ["git", "diff", "--cached", "--raw", "-z",
         "--diff-filter=" + STAGED_CHANGE_FILTER],
        capture_output=True)
    if r.returncode != 0:
        sys.stderr.write("BLOCKED hook-error git-diff-failed\n")
        sys.exit(1)

    fields = r.stdout.decode("utf-8", "replace").split("\0")
    entries = []
    i = 0
    while i < len(fields):
        field = fields[i]
        if not field.startswith(":"):
            i += 1
            continue
        # ":<srcmode> <dstmode> <srcsha> <dstsha> <status>"
        parts = field[1:].split(" ")
        if len(parts) < 5:
            i += 1
            continue
        dst_mode, status = parts[1], parts[4]
        if status[:1] in ("R", "C"):
            # source path, then destination path; only the destination
            # exists in the resulting commit.
            path = fields[i + 2] if i + 2 < len(fields) else ""
            i += 3
        else:
            path = fields[i + 1] if i + 1 < len(fields) else ""
            i += 2
        if path:
            entries.append((path, dst_mode))
    return entries


def staged_blob(path):
    r = subprocess.run(["git", "show", ":" + path], capture_output=True)
    if r.returncode != 0:
        return None
    return r.stdout


def scan_bytes(data, deny_regexes, tokens, builtins_only=False):
    for view in text_views(data):
        hit = builtin_hit(view)
        if hit:
            return hit
        if builtins_only:
            continue
        for rule_id, rx in deny_regexes:
            if rx.search(view):
                return "deny-list:" + rule_id
        for tok in tokens:
            if tok in view:
                return "deny-token"
    return None


def config_relpaths(tokens_file):
    """Repo-relative paths whose SELF-REFERENTIAL layers are suppressed:
    the deny-list config and the tokens file it points at.

    Only the layers that would match the file's OWN declarations are
    suppressed (deny_regexes and the literal tokens); the built-in
    credential patterns still apply, so an AWS key or a private-key block
    pasted into a `_comment` still blocks.

    Comparison is exact on the git-reported relative path, which is the
    identity git itself uses. On a case-insensitive filesystem the cost of
    the strictness is that a config staged under an unexpected case gets
    scanned -- i.e. it fails CLOSED."""
    paths = {DEFAULT_CONFIG_NAME}
    if tokens_file:
        paths.add(tokens_file.replace("\\", "/").lstrip("./"))
    return paths


def main():
    root = repo_root()
    deny_regexes, deny_filenames, tokens, tokens_file = load_config(root)
    self_referential = config_relpaths(tokens_file)

    bad = 0
    for path, dst_mode in staged_entries():
        # deny_filenames is matched against EVERY component of the staged
        # path, not only the basename. A directory literally named `.env`
        # (`.env/local`) is not expressible in any basename regex, so
        # basename-only matching left a shape no config change could
        # reach. Matching components keeps the config vocabulary the same
        # (`^\.env$` still means "a path element named exactly .env").
        # This check runs BEFORE the gitlink skip: a gitlink has no blob to
        # scan, but it does have a path, and the filename policy is about
        # the path (a submodule named `.env` used to sail through -- 5th
        # external review, 2026-08-18).
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if any(rx.search(part) for part in parts for rx in deny_filenames):
            print("BLOCKED deny-filename %s" % path)
            bad += 1
            continue
        if dst_mode == GITLINK_MODE:
            continue

        data = staged_blob(path)
        if data is None:
            print("BLOCKED unreadable-staged-blob %s" % path)
            bad += 1
            continue

        hit = scan_bytes(data, deny_regexes, tokens,
                         builtins_only=path in self_referential)
        if hit:
            print("BLOCKED %s %s" % (hit, path))
            bad += 1

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
