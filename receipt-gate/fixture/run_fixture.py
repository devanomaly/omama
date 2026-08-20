#!/usr/bin/env python3
"""Fixture runner for receipt_gate.py (CARD-02, 2026-08-19).

Builds throwaway git repos, invokes the gate as a subprocess with synthetic
Stop-hook stdin JSON, and asserts exit codes + named-reason regression locks
for every case in the hardened plan: the allow set, the block set, and the
pinned KNOWN-LIMITATION.

Exit 0  -> every case behaved as expected, each red for its NAMED reason.
Exit 1  -> at least one case misbehaved (gate broken or weakened), OR a
           case's environment could not be established (env-heavy fixtures
           FAIL LOUDLY, never skip -- a silently-skipped fail-closed fixture
           recreates the silent-absence class inside the test suite).

Usage:  py -3 run_fixture.py [case-name-substring]
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "receipt_gate.py"
ROOT = HERE.parent.parent
VALIDATOR = ROOT / "work-order" / "validate_work_order.py"
CHECKER = ROOT / "output-discipline" / "scripts" / "check_artifact.py"
PY = sys.executable

GREEN = f'"{PY}" -c "import sys; sys.exit(0)"'
RED = f'"{PY}" -c "import sys; print(\'BOOM_MARKER\'); sys.exit(3)"'


class CaseFail(Exception):
    pass


def check(cond, msg, result=None):
    if not cond:
        detail = msg
        if result is not None:
            tail = (result.stdout + result.stderr).strip().splitlines()[-8:]
            detail += "\n      | " + "\n      | ".join(tail) if tail else ""
        raise CaseFail(detail)


def _rmtree(path):
    def onerr(fn, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            fn(p)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda fn, p, e: onerr(fn, p, e))
    else:
        shutil.rmtree(path, onerror=onerr)


def git(repo, *args, check_rc=True):
    r = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if check_rc and r.returncode != 0:
        raise CaseFail(f"fixture setup git {args} failed: {r.stderr.strip()}")
    return r


def make_repo(base, name="repo", commit=True):
    repo = Path(base) / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@test")
    git(repo, "config", "user.name", "fixture")
    if commit:
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-qm", "base")
    return repo


def yaml_sq(s):
    return "'" + s.replace("'", "''") + "'"


def card_text(verify=GREEN, tier="S1", with_verify=True):
    lines = [
        "goal: 'fixture goal'",
        "non_goals: ['nothing']",
        f"tier: {tier}",
        "task_type: implementation",
        "done_when: ['observable thing']",
    ]
    if with_verify:
        lines.append(f"verify: {yaml_sq(verify)}")
    return "\n".join(lines) + "\n"


def write_card(repo, verify=GREEN, tier="S1", **kw):
    (repo / "CARD.yaml").write_text(card_text(verify=verify, tier=tier, **kw),
                                    encoding="utf-8")


def gate_env(extra=None, strip_path=False):
    env = dict(os.environ)
    env.pop("OMAMA_CARD", None)
    env["OMAMA_VALIDATOR"] = str(VALIDATOR)
    env["OMAMA_CHECK_ARTIFACT"] = str(CHECKER)
    if strip_path:
        env["PATH"] = os.path.dirname(PY)
    if extra:
        env.update(extra)
    return env


def run_gate(cwd, env=None, stdin=None, argv_prefix=None, timeout=180):
    argv = list(argv_prefix or [PY]) + [str(GATE)]
    payload = stdin if stdin is not None else json.dumps(
        {"cwd": str(cwd), "stop_hook_active": False, "hook_event_name": "Stop"})
    return subprocess.run(argv, input=payload, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env=env or gate_env(), cwd=str(cwd), timeout=timeout)


def receipt(repo, sub=""):
    p = Path(repo) / sub / "CARD.receipt.json" if sub else Path(repo) / "CARD.receipt.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


REVIEW_PASS = ("<!-- review v1 · tier: S -->\n"
               "Verdict: PASS\n\n## Findings\n- none\n\n"
               "Non-findings: schema, hashing checked clean.\n")
REVIEW_BLOCK = REVIEW_PASS.replace("Verdict: PASS", "Verdict: BLOCK")
REVIEW_BLOCK_THEN_PASS = REVIEW_BLOCK + "\nVerdict: PASS\n"
REVIEW_NOTRUN = "just some prose with no declaration at all\n"
REVIEW_PLAN_TYPED = ("<!-- plan v1 · tier: XS -->\n"
                     "Done when: it works.\nVerify: something\n")

# ---------------------------------------------------------------- allow set

def a_verified_green(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    check("VERIFIED" in r.stdout, "no VERIFIED on stdout", r)
    rc = receipt(repo)
    check(rc is not None, "no receipt written", r)
    check(rc["verdict"] == "VERIFIED" and rc["exit"] == 0, f"bad receipt {rc}", r)
    for k in ("rev", "patch_id", "diff_sha", "diff_hash"):
        check(rc.get(k), f"receipt {k} null on VERIFIED (invalid on its face)", r)
    check(set(rc) == {"command", "exit", "verdict", "rev", "patch_id",
                      "diff_sha", "diff_hash", "timestamp"},
          f"receipt keys not exact: {sorted(rc)}", r)
    check(not (repo / "CARD.close").exists(), "CARD.close not consumed", r)


def a_honest_failed_red(tmp):
    repo = make_repo(tmp)
    write_card(repo, verify=RED)
    (repo / "CARD.close").write_text("FAILED: could not fix the flake",
                                     encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    check("FAILED (honest)" in r.stdout, "no honest-FAILED line", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "FAILED" and rc["exit"] == 3,
          f"bad receipt {rc}", r)
    check("could not fix" in (rc.get("reason") or ""), "reason not echoed", r)
    check(not (repo / "CARD.close").exists(), "CARD.close not consumed", r)


def a_honest_failed_green(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("FAILED: bailing anyway", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "FAILED" and rc["exit"] == 0,
          f"green-verify FAILED close must record verdict FAILED: {rc}", r)


def a_honest_schema_broken(tmp):
    repo = make_repo(tmp)
    write_card(repo, tier="S9")
    (repo / "CARD.close").write_text("FAILED: schema was wrong", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "FAILED", f"bad receipt {rc}", r)
    check("schema" in (rc.get("reason") or "").lower(),
          "schema state not recorded in reason", r)


def a_honest_unparseable(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_text("goal: [unclosed\n", encoding="utf-8")
    (repo / "CARD.close").write_text("FAILED: card is broken", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["command"] is None and rc["exit"] is None,
          f"unparseable card must yield command/exit null: {rc}", r)


def a_honest_empty_card(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_text("", encoding="utf-8")
    (repo / "CARD.close").write_text("FAILED: editor crash left empty card",
                                     encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["command"] is None, f"None-root card: {rc}", r)


def a_honest_list_root(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_text("- a\n- b\n", encoding="utf-8")
    (repo / "CARD.close").write_text("FAILED: card is a list", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["command"] is None, f"list-root card: {rc}", r)


def a_honest_verify_absent(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_text(card_text(with_verify=False), encoding="utf-8")
    (repo / "CARD.close").write_text("FAILED: no verify yet", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["command"] is None, f"verify-absent card: {rc}", r)


def a_honest_dirty_tree(tmp):
    repo = make_repo(tmp)
    mut = f'"{PY}" -c "open(\'tracked.txt\',\'a\').write(\'more\')"'
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("FAILED: gave up mid-change", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0,
          f"honest close must not block on UNEXPECTED-CHANGE, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "FAILED", f"bad receipt {rc}", r)


def a_honest_nongit(tmp):
    d = Path(tmp) / "plain"
    d.mkdir()
    (d / "CARD.yaml").write_text(card_text(), encoding="utf-8")
    (d / "CARD.close").write_text("FAILED: not even a repo", encoding="utf-8")
    env = gate_env({"OMAMA_CARD": str(d / "CARD.yaml")})
    r = run_gate(d, env=env)
    check(r.returncode == 0, f"expected degraded exit 0, got {r.returncode}", r)
    rc = receipt(d)
    check(rc and rc["verdict"] == "FAILED" and rc["rev"] is None,
          f"degraded receipt must have null hashes: {rc}", r)
    check("git" in (rc.get("reason") or "").lower(), "degradation not named", r)


def a_honest_gitless_path(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("FAILED: no git here", encoding="utf-8")
    r = run_gate(repo, env=gate_env(strip_path=True))
    check(r.returncode == 0, f"expected degraded exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["rev"] is None, f"expected null hashes: {rc}", r)


def a_wip_turn(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    fake = {"command": "x", "exit": 0, "verdict": "VERIFIED", "rev": "deadbeef",
            "patch_id": "p", "diff_sha": "d", "diff_hash": "h",
            "timestamp": "2026-08-19T00:00:00Z"}
    (repo / "CARD.receipt.json").write_text(json.dumps(fake), encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"WIP turn must allow, got {r.returncode}", r)
    check("WIP" in r.stdout, "no WIP warning line", r)
    check("VERIFIED" in r.stdout, "standing receipt not echoed on WIP turn", r)
    check(receipt(repo) == fake, "WIP turn must not touch the receipt", r)


def a_no_card(tmp):
    repo = make_repo(tmp)
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    check("NO-CARD" in r.stdout, "no NO-CARD line", r)


def a_no_card_nongit(tmp):
    d = Path(tmp) / "plain"
    d.mkdir()
    r = run_gate(d)
    check(r.returncode == 0,
          f"non-git cwd without card must warn not block, got {r.returncode}", r)
    check("NO-CARD" in r.stdout, "no NO-CARD line", r)
    check("GIT-ERROR" not in r.stderr, "GIT-ERROR fired with no card engaged", r)


def a_no_card_orphan_close(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.close").write_text("FAILED: from a deleted card", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    check("CARD.close" in r.stdout, "orphaned CARD.close not named", r)


def a_s3_pass_review(tmp):
    repo = make_repo(tmp)
    write_card(repo, tier="S3")
    (repo / "CARD.review.md").write_text(REVIEW_PASS, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "card+review")
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "VERIFIED", f"bad receipt {rc}", r)


def a_s3_overbudget_review(tmp):
    """CARD-03: output-discipline's line budgets are advisory. A
    structurally-valid S3 review (verdict in first 3 lines, Findings +
    Non-findings present) that blows past tier S's 15-line budget must
    still ALLOW the close -- the gate must invoke the output-discipline
    checker with --budgets-advisory so over-budget-only warns instead of
    blocking."""
    filler = "\n".join(f"- padding line {i} to blow the tier S budget"
                       for i in range(20))
    review = ("<!-- review v1 · tier: S -->\n"
              "Verdict: PASS\n\n## Findings\n" + filler + "\n\n"
              "Non-findings: schema, hashing checked clean.\n")
    repo = _s3_repo(tmp, review)
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "VERIFIED", f"bad receipt {rc}", r)
    check("over-budget" in (r.stdout + r.stderr),
          "advisory over-budget warning swallowed -- operator never sees it",
          r)


def a_omama_card_custom(tmp):
    repo = make_repo(tmp)
    sub = repo / "cards"
    sub.mkdir()
    (sub / "my.yaml").write_text(card_text(), encoding="utf-8")
    (sub / "CARD.close").write_text("CLOSE", encoding="utf-8")
    env = gate_env({"OMAMA_CARD": str(sub / "my.yaml")})
    r = run_gate(repo, env=env)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo, sub="cards")
    check(rc and rc["verdict"] == "VERIFIED",
          f"receipt not at card dir or bad: {rc}", r)


def a_honest_undecodable(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_bytes(card_text().encode("utf-16"))
    (repo / "CARD.close").write_text("FAILED: mojibake card", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["command"] is None, f"undecodable card: {rc}", r)


# ---------------------------------------------------------------- block set

def b_planted_red(tmp):
    repo = make_repo(tmp)
    write_card(repo, verify=RED)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("VERIFY-RED" in r.stderr, "red not named VERIFY-RED", r)
    check("BOOM_MARKER" in r.stderr, "verify output tail not fed back", r)
    check("FAILED" in r.stderr and "CARD.close" in r.stderr,
          "escape-hatch text missing from block message", r)


def b_unexpected_tracked(tmp):
    repo = make_repo(tmp)
    mut = f'"{PY}" -c "open(\'tracked.txt\',\'a\').write(\'x\')"'
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def b_unexpected_untracked_dir(tmp):
    repo = make_repo(tmp)
    (repo / "udir").mkdir()
    (repo / "udir" / "a.txt").write_text("a", encoding="utf-8")
    mut = f'"{PY}" -c "open(\'udir/b.txt\',\'w\').write(\'b\')"'
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"-uall lock: new file inside untracked dir must trip, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def b_unexpected_review_rewrite(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.review.md").write_text(REVIEW_PASS, encoding="utf-8")
    mut = f'"{PY}" -c "open(\'CARD.review.md\',\'w\').write(\'swapped PASS\')"'
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"CARD-family content lock must trip, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def b_unexpected_stash(tmp):
    repo = make_repo(tmp)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    write_card(repo, verify="git stash -q && git stash pop -q")
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"stash round-trip must trip the reflog tripwire, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def b_schema_fail_close(tmp):
    repo = make_repo(tmp)
    write_card(repo, verify="true")
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("SCHEMA" in r.stderr, "not named SCHEMA", r)
    check("VIOLATION" in r.stderr, "validator output not echoed", r)


def b_garbage_close(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("MAYBE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("CLOSE-TOKEN" in r.stderr, "not named CLOSE-TOKEN", r)


def b_bare_failed(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("FAILED", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"bare FAILED (no reason) must block, got {r.returncode}", r)
    check("CLOSE-TOKEN" in r.stderr and "reason" in r.stderr.lower(),
          "reason requirement not named", r)


def _s3_repo(tmp, review_text):
    repo = make_repo(tmp)
    write_card(repo, tier="S3")
    if review_text is not None:
        (repo / "CARD.review.md").write_text(review_text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "s3")
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    return repo


def b_s3_no_review(tmp):
    r = run_gate(_s3_repo(tmp, None))
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_s3_block_verdict(tmp):
    r = run_gate(_s3_repo(tmp, REVIEW_BLOCK))
    check(r.returncode == 2,
          f"Verdict: BLOCK passes the checker exit 0 -- gate must still block, got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_s3_block_then_pass(tmp):
    r = run_gate(_s3_repo(tmp, REVIEW_BLOCK_THEN_PASS))
    check(r.returncode == 2,
          f"BLOCK-in-first-3 + PASS-later must block, got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_s3_notrun(tmp):
    r = run_gate(_s3_repo(tmp, REVIEW_NOTRUN))
    check(r.returncode == 2, f"checker NOT-RUN must block, got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_s3_plan_typed(tmp):
    r = run_gate(_s3_repo(tmp, REVIEW_PLAN_TYPED))
    check(r.returncode == 2,
          f"plan-typed review (checker exit 0, zero verdicts) must block, got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_s3_structure_invalid_advisory(tmp):
    """CARD-03: --budgets-advisory only demotes the over-budget violation --
    a within-budget review with a PASS verdict in its first 3 lines but no
    Non-findings section is a tier S STRUCTURE violation, which still fails
    the checker (exit 1) and must still block, flag on or not."""
    review = ("<!-- review v1 · tier: S -->\n"
              "Verdict: PASS\n\n## Findings\n- none\n")
    r = run_gate(_s3_repo(tmp, review))
    check(r.returncode == 2,
          f"structure-invalid review must block even under --budgets-advisory, "
          f"got {r.returncode}", r)
    check("S3-REVIEW" in r.stderr, "not named S3-REVIEW", r)


def b_timeout(tmp):
    repo = make_repo(tmp)
    (repo / "spawner.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, 'child.py'])\n"
        "time.sleep(30)\n", encoding="utf-8")
    (repo / "child.py").write_text(
        "import time, pathlib\ntime.sleep(3)\n"
        "pathlib.Path('marker.txt').write_text('x')\n", encoding="utf-8")
    write_card(repo, verify=f'"{PY}" spawner.py')
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo, env=gate_env({"OMAMA_VERIFY_TIMEOUT": "2"}))
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("TIMEOUT" in r.stderr, "not named TIMEOUT", r)
    time.sleep(4.5)
    check(not (repo / "marker.txt").exists(),
          "grandchild survived the timeout kill (process tree not killed)", r)


def b_pyyaml_less(tmp):
    probe = subprocess.run([PY, "-S", "-c", "import yaml"], capture_output=True)
    check(probe.returncode != 0,
          "FIXTURE ENV NOT ESTABLISHED: py -S can still import yaml -- "
          "this fail-closed fixture must fail loudly, not fake a pass")
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo, argv_prefix=[PY, "-S"])
    check(r.returncode == 2,
          f"pyyaml-less interpreter must fail closed (exit 2), got {r.returncode}", r)
    check("GATE-ERROR" in r.stderr, "not named GATE-ERROR", r)


def b_gitless_close(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo, env=gate_env(strip_path=True))
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("GIT-ERROR" in r.stderr, "not named GIT-ERROR", r)


def b_unborn_head(tmp):
    repo = make_repo(tmp, commit=False)
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"unborn HEAD must block, never hash empty output, got {r.returncode}", r)
    check("GIT-ERROR" in r.stderr, "not named GIT-ERROR", r)


def b_empty_stdin(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    r = run_gate(repo, stdin="")
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("BAD-INPUT" in r.stderr, "not named BAD-INPUT", r)


def b_json_no_cwd_fallback(tmp):
    repo = make_repo(tmp)
    write_card(repo)
    r = run_gate(repo, stdin=json.dumps({"stop_hook_active": False}))
    check(r.returncode == 0,
          f"cwd-less JSON must fall back to getcwd (spike-confirmed), got {r.returncode}", r)
    check("WIP" in r.stdout, "getcwd fallback did not find the card (no WIP line)", r)


def b_omama_card_dangling(tmp):
    repo = make_repo(tmp)
    env = gate_env({"OMAMA_CARD": str(Path(tmp) / "nope" / "CARD.yaml")})
    r = run_gate(repo, env=env)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("CARD-CONFIGURED-BUT-MISSING" in r.stderr,
          "not named CARD-CONFIGURED-BUT-MISSING", r)


def b_undecodable_close_intent(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.yaml").write_bytes(card_text().encode("utf-16"))
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"undecodable card on CLOSE-intent must block, got {r.returncode}", r)
    check("SCHEMA" in r.stderr or "GATE-ERROR" in r.stderr,
          "block not named", r)


def b_forged_receipt_blocked(tmp):
    repo = make_repo(tmp)
    write_card(repo, verify=RED)
    (repo / "CARD.receipt.json").write_text('{"verdict": "VERIFIED"}',
                                            encoding="utf-8")
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check(receipt(repo) is None,
          "pre-existing receipt survived a blocked close (start-deletion missing)", r)


def b_plant_mid_attempt(tmp):
    repo = make_repo(tmp)
    plant = (f'"{PY}" -c "import json; json.dump({{\'verdict\': \'VERIFIED\'}}, '
             f'open(\'CARD.receipt.json\',\'w\')); import sys; sys.exit(3)"')
    write_card(repo, verify=plant)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check(receipt(repo) is None,
          "verify-planted receipt survived the block (block-exit deletion missing)", r)


def b_plant_guard_route(tmp):
    repo = make_repo(tmp)
    (repo / "CARD.review.md").write_text(REVIEW_PASS, encoding="utf-8")
    plant = (f'"{PY}" -c "import json, os, shutil; '
             f'json.dump({{\'verdict\': \'VERIFIED\'}}, open(\'CARD.receipt.json\',\'w\')); '
             f'os.remove(\'CARD.review.md\'); os.mkdir(\'CARD.review.md\')"')
    write_card(repo, verify=plant)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"exception mid-H2 must fail closed, got {r.returncode}", r)
    check(receipt(repo) is None,
          "planted receipt survived the guard-route block (guard deletion missing)", r)


def b_assume_unchanged_mid(tmp):
    repo = make_repo(tmp)
    mut = (f'"{PY}" -c "open(\'tracked.txt\',\'a\').write(\'x\')" '
           f'&& git update-index --assume-unchanged tracked.txt')
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"mutate+assume-unchanged must trip the index-flag tripwire, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def b_assume_preseed(tmp):
    repo = make_repo(tmp)
    git(repo, "update-index", "--assume-unchanged", "tracked.txt")
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2,
          f"pre-seeded assume-unchanged flag must block CLOSE-intent, got {r.returncode}", r)
    check("INDEX-FLAGS" in r.stderr, "not named INDEX-FLAGS", r)
    check("--no-assume-unchanged" in r.stderr, "remediation not named", r)


def b_omama_card_rewrite(tmp):
    repo = make_repo(tmp)
    sub = repo / "cards"
    sub.mkdir()
    mut = f'"{PY}" -c "open(\'cards/my.yaml\',\'a\').write(\'# tampered\')"'
    (sub / "my.yaml").write_text(card_text(verify=mut), encoding="utf-8")
    (sub / "CARD.close").write_text("CLOSE", encoding="utf-8")
    env = gate_env({"OMAMA_CARD": str(sub / "my.yaml")})
    r = run_gate(repo, env=env)
    check(r.returncode == 2,
          f"resolved-card rewrite mid-verify must trip, got {r.returncode}", r)
    check("UNEXPECTED-CHANGE" in r.stderr, "not named UNEXPECTED-CHANGE", r)


def a_honest_review_dir(tmp):
    """code-review F4: honest close must ALWAYS complete -- a CARD.review.md
    that is a directory (or AV-locked) must degrade, never crash to exit 2."""
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.review.md").mkdir()
    (repo / "CARD.close").write_text("FAILED: weird review state",
                                     encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0,
          f"honest close crashed on unreadable family file, got {r.returncode}", r)
    check(receipt(repo) is not None, "no receipt on honest close", r)


def a_honest_bad_timeout(tmp):
    """code-review F5: malformed OMAMA_VERIFY_TIMEOUT must not block the
    honest hatch."""
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("FAILED: bad env anyway", encoding="utf-8")
    r = run_gate(repo, env=gate_env({"OMAMA_VERIFY_TIMEOUT": "10m"}))
    check(r.returncode == 0,
          f"honest close blocked by timeout typo, got {r.returncode}", r)
    rc = receipt(repo)
    check("OMAMA_VERIFY_TIMEOUT" in (rc.get("reason") or ""),
          "timeout typo not named in reason", r)


def b_bad_timeout_close(tmp):
    """code-review F5: on VERIFIED-intent the broken knob blocks, NAMED."""
    repo = make_repo(tmp)
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo, env=gate_env({"OMAMA_VERIFY_TIMEOUT": "10m"}))
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("OMAMA_VERIFY_TIMEOUT" in r.stderr, "broken knob not named", r)


def a_tracked_receipt_recomputable(tmp):
    """code-review F3: even with CARD.receipt.json git-TRACKED, diff_sha must
    be recomputable post-close via the exact pinned command (receipt path
    pathspec-excluded)."""
    repo = make_repo(tmp)
    (repo / "CARD.receipt.json").write_text("{}", encoding="utf-8")
    git(repo, "add", "CARD.receipt.json")
    git(repo, "commit", "-qm", "track receipt")
    (repo / "tracked.txt").write_text("dirty for a non-empty diff\n",
                                      encoding="utf-8")
    write_card(repo)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"expected exit 0, got {r.returncode}", r)
    rc = receipt(repo)
    check(rc and rc["verdict"] == "VERIFIED", f"bad receipt {rc}", r)
    d = git(repo, "-c", "core.quotepath=false", "-c", "diff.noprefix=false",
            "-c", "diff.mnemonicPrefix=false", "-c", "diff.interHunkContext=0",
            "diff", "--no-ext-diff", "--no-color", "--no-textconv", "-U3",
            "HEAD", "--", ".", ":(exclude)CARD.receipt.json")
    import hashlib
    recomputed = hashlib.sha256(d.stdout.encode("utf-8")).hexdigest()
    check(recomputed == rc["diff_sha"],
          f"diff_sha not recomputable: recorded {rc['diff_sha'][:12]} vs "
          f"recomputed {recomputed[:12]}", r)


def b_unexpected_untracked_removed(tmp):
    """code-review F9: a REMOVED untracked file must be named as removed in
    the UNEXPECTED-CHANGE detail (was dead code behind a precedence bug)."""
    repo = make_repo(tmp)
    (repo / "u.txt").write_text("u", encoding="utf-8")
    mut = f'"{PY}" -c "import os; os.remove(\'u.txt\')"'
    write_card(repo, verify=mut)
    (repo / "CARD.close").write_text("CLOSE", encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 2, f"expected exit 2, got {r.returncode}", r)
    check("removed untracked names" in r.stderr and "u.txt" in r.stderr,
          "removed untracked file not named in the block detail", r)


# --------------------------------------------------- pinned KNOWN-LIMITATION

def k_forged_wip_receipt_persists(tmp):
    """KNOWN-LIMITATION (pinned so the 'forged receipt deleted' fixtures
    cannot manufacture false confidence): a receipt forged on a WIP turn
    persists -- detection is the WIP echo line / ratification / recompute,
    never file presence."""
    repo = make_repo(tmp)
    write_card(repo)
    forged = {"command": "x", "exit": 0, "verdict": "VERIFIED", "rev": "f" * 8,
              "patch_id": "p", "diff_sha": "d", "diff_hash": "h",
              "timestamp": "2026-08-19T00:00:00Z"}
    (repo / "CARD.receipt.json").write_text(json.dumps(forged), encoding="utf-8")
    r = run_gate(repo)
    check(r.returncode == 0, f"WIP turn allows, got {r.returncode}", r)
    check(receipt(repo) == forged,
          "KNOWN-LIMITATION drifted: WIP turn touched the forged receipt", r)
    check("VERIFIED" in r.stdout, "forged receipt not surfaced by WIP echo", r)


CASES = [
    ("allow: green VERIFIED close, receipt v2 key-exact", a_verified_green),
    ("allow: honest FAILED w/ red verify", a_honest_failed_red),
    ("allow: honest FAILED w/ GREEN verify records verdict FAILED", a_honest_failed_green),
    ("allow: honest close on schema-broken card", a_honest_schema_broken),
    ("allow: honest close on YAML-unparseable card", a_honest_unparseable),
    ("allow: honest close on empty-file card (root None)", a_honest_empty_card),
    ("allow: honest close on list-rooted card", a_honest_list_root),
    ("allow: honest close on verify-absent card", a_honest_verify_absent),
    ("allow: honest close w/ dirty tree (no freshness block)", a_honest_dirty_tree),
    ("allow: honest close in non-git card dir (degraded)", a_honest_nongit),
    ("allow: honest close w/ git-less PATH (degraded)", a_honest_gitless_path),
    ("allow: WIP turn echoes standing receipt, touches nothing", a_wip_turn),
    ("allow: NO-CARD", a_no_card),
    ("allow: non-git cwd without card is NO-CARD not GIT-ERROR", a_no_card_nongit),
    ("allow: NO-CARD names orphaned CARD.close", a_no_card_orphan_close),
    ("allow: S3 + PASS review", a_s3_pass_review),
    ("allow: S3 + over-budget PASS review", a_s3_overbudget_review),
    ("allow: OMAMA_CARD at non-default path", a_omama_card_custom),
    ("allow: honest close on undecodable card", a_honest_undecodable),
    ("block: planted-red, output tail + hatch text", b_planted_red),
    ("block: UNEXPECTED-CHANGE tracked mutation", b_unexpected_tracked),
    ("block: UNEXPECTED-CHANGE new file inside untracked dir (-uall)", b_unexpected_untracked_dir),
    ("block: UNEXPECTED-CHANGE CARD.review.md rewrite mid-verify", b_unexpected_review_rewrite),
    ("block: UNEXPECTED-CHANGE stash round-trip (reflog tripwire)", b_unexpected_stash),
    ("block: schema-fail on CLOSE-intent (vacuous verify)", b_schema_fail_close),
    ("block: garbage CARD.close token", b_garbage_close),
    ("block: bare FAILED without reason", b_bare_failed),
    ("block: S3 review absent", b_s3_no_review),
    ("block: S3 verdict BLOCK with checker exit 0", b_s3_block_verdict),
    ("block: S3 BLOCK-first-3 + PASS-later", b_s3_block_then_pass),
    ("block: S3 checker NOT-RUN", b_s3_notrun),
    ("block: S3 plan-typed review (zero verdicts)", b_s3_plan_typed),
    ("block: S3 structure-invalid review under advisory budgets",
     b_s3_structure_invalid_advisory),
    ("block: TIMEOUT kills the whole process tree", b_timeout),
    ("block: pyyaml-less interpreter fails closed", b_pyyaml_less),
    ("block: git-less PATH on CLOSE-intent", b_gitless_close),
    ("block: unborn HEAD", b_unborn_head),
    ("block: empty stdin is BAD-INPUT", b_empty_stdin),
    ("allow: JSON without cwd falls back to getcwd", b_json_no_cwd_fallback),
    ("block: OMAMA_CARD dangling", b_omama_card_dangling),
    ("block: undecodable card on CLOSE-intent", b_undecodable_close_intent),
    ("block: pre-existing forged receipt deleted on blocked close", b_forged_receipt_blocked),
    ("block: verify-planted receipt deleted on block exit", b_plant_mid_attempt),
    ("block: verify-planted receipt deleted when family file turns unreadable", b_plant_guard_route),
    ("allow: honest close with CARD.review.md as a directory", a_honest_review_dir),
    ("allow: honest close survives OMAMA_VERIFY_TIMEOUT typo", a_honest_bad_timeout),
    ("block: OMAMA_VERIFY_TIMEOUT typo blocks CLOSE-intent, named", b_bad_timeout_close),
    ("allow: tracked receipt stays diff_sha-recomputable", a_tracked_receipt_recomputable),
    ("block: removed untracked file named in UNEXPECTED-CHANGE", b_unexpected_untracked_removed),
    ("block: mutate + --assume-unchanged mid-verify", b_assume_unchanged_mid),
    ("block: pre-seeded assume-unchanged at H1", b_assume_preseed),
    ("block: OMAMA_CARD card rewritten mid-verify", b_omama_card_rewrite),
    ("KNOWN-LIMITATION: forged WIP-turn receipt persists", k_forged_wip_receipt_persists),
]


def main(argv):
    only = argv[1] if len(argv) > 1 else None
    base = tempfile.mkdtemp(prefix="rgate-fixture-")
    all_ok = True
    ran = 0
    try:
        for label, fn in CASES:
            if only and only not in label and only not in fn.__name__:
                continue
            ran += 1
            case_dir = tempfile.mkdtemp(prefix=fn.__name__ + "-", dir=base)
            try:
                fn(case_dir)
                print(f"[PASS] {label}")
            except CaseFail as e:
                all_ok = False
                print(f"[FAIL] {label}")
                print(f"       {e}")
            except Exception as e:  # noqa: BLE001 -- a crash is a failure
                all_ok = False
                print(f"[FAIL] {label} [runner crash: {type(e).__name__}: {e}]")
    finally:
        _rmtree(base)
    print()
    if ran == 0:
        print("FIXTURE RESULT: no case matched the filter")
        return 1
    if all_ok:
        print(f"FIXTURE RESULT: all {ran} cases behaved as expected")
        return 0
    print("FIXTURE RESULT: at least one case did NOT behave as expected")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
