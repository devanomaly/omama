"""Mandatory exact-installed-command admission for ``omama init``.

The harness copies only the already-published target topology into private,
target-owned scratch repositories.  It never imports a payload dependency
from this package and never reads the adopter's configured token values.
"""

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .doctor import _bash_path
from .install import InstallError
from .target import GIT_CONFIG_PREFIXES, GIT_ROUTING, git_scratch_command, safe_destination


@dataclass(frozen=True)
class AdmissionItem:
    status: str
    name: str
    detail: str


class AdmissionReport:
    def __init__(self):
        self.items = []

    def add(self, status, name, detail):
        self.items.append(AdmissionItem(status, name, detail))

    @property
    def exit_code(self):
        if any(item.status == "VIOLATION" for item in self.items):
            return 1
        if any(item.status == "NOT-RUN" for item in self.items):
            return 2
        return 0

    def emit(self, stdout, stderr):
        for item in self.items:
            stream = stderr if item.status in ("VIOLATION", "NOT-RUN") else stdout
            stream.write("ADMISSION-{0}[{1}]: {2}\n".format(item.status, item.name, item.detail))
        if self.exit_code == 0:
            stdout.write("ADMISSION-OK: every mandatory installed command was evaluated and passed\n")
        elif self.exit_code == 2:
            stderr.write("ADMISSION-NOT-RUN: required installed-command coverage was unavailable\n")
        else:
            stderr.write("ADMISSION-FAILED: one or more installed-command challenges failed\n")
        return self.exit_code


class _CaseFailure(AssertionError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _clean_env(extra=None):
    env = {
        key: value for key, value in os.environ.items()
        if key not in GIT_ROUTING and not key.startswith(GIT_CONFIG_PREFIXES)
        and not key.startswith("OMAMA_")
    }
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


def _run(argv, cwd, env=None, input_text=None, timeout=180):
    try:
        return subprocess.run(
            [str(value) for value in argv], cwd=str(cwd), env=env or _clean_env(),
            input=input_text, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _CaseFailure("child command unavailable: {0}: {1}".format(type(exc).__name__, exc))


def _run_bytes(argv, cwd, env=None, timeout=180):
    try:
        return subprocess.run(
            [str(value) for value in argv], cwd=str(cwd), env=env or _clean_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _CaseFailure("child command unavailable: {0}: {1}".format(type(exc).__name__, exc))


def _output(result):
    return (result.stdout or "") + (result.stderr or "")


def _require(condition, message, result=None):
    if condition:
        return
    if result is not None:
        message += "\n--- child stdout ---\n{0}\n--- child stderr ---\n{1}".format(
            result.stdout or "", result.stderr or "")
    raise _CaseFailure(message)


def _yaml_single(value):
    return "'" + value.replace("'", "''") + "'"


def _card(verify, tier="S1"):
    return (
        "goal: 'synthetic installed admission'\n"
        "non_goals: ['no adopter state']\n"
        "tier: {0}\n"
        "task_type: implementation\n"
        "done_when: ['installed command is observed']\n"
        "verify: {1}\n"
    ).format(tier, _yaml_single(verify))


_REVIEW_INVALID = (
    "<!-- review v1 \u00b7 tier: S -->\n"
    "Verdict: PASS\n\n"
    "## Findings\n\n"
    "- No blocking issue in the synthetic fixture.\n"
)

_REVIEW_VALID = (
    "<!-- review v1 \u00b7 tier: S -->\n"
    "Verdict: PASS\n\n"
    "## Findings\n\n"
    "- No blocking issue in the synthetic fixture.\n\n"
    "## Non-findings\n\n"
    "- Installed checker structure was exercised and found clean.\n"
)


class _Harness:
    def __init__(self, target, state, scratch_root, report):
        self.target = target
        self.state = state
        self.scratch_root = Path(scratch_root)
        self.report = report
        self.shell = _bash_path()
        self.manifest = json.loads((target.root / "tools/omama/manifest.json").read_text(encoding="utf-8"))
        self.command = state.get("settings_command")
        if not isinstance(self.command, str) or not self.command:
            raise InstallError("admission-state", "installed state has no exact managed settings command")
        self.absent_editable = [
            entry["destination"] for entry in self.manifest["files"]
            if entry["ownership"] == "editable-bootstrap"
            and not safe_destination(target.root, entry["destination"]).is_file()
        ]
        if self.absent_editable:
            report.add(
                "WARNING", "editable-absent",
                "deliberately absent inert/editable material is preserved and omitted from scratch: {0}"
                .format(", ".join(self.absent_editable)),
            )

    def case(self, name, action, unavailable=False):
        try:
            detail = action()
        except _CaseFailure as exc:
            self.report.add("NOT-RUN" if unavailable else "VIOLATION", name, str(exc))
        except Exception as exc:
            self.report.add("VIOLATION", name, "harness error: {0}: {1}".format(type(exc).__name__, exc))
        else:
            self.report.add("OK", name, detail)

    def copy_topology(self, name):
        repo = self.scratch_root / name
        repo.mkdir()
        for entry in self.manifest["files"]:
            relative = entry["destination"]
            source = safe_destination(self.target.root, relative)
            if not source.is_file():
                if entry["ownership"] == "editable-bootstrap":
                    continue
                raise _CaseFailure("installed topology is missing {0}; no package/source fallback was used".format(relative))
            data = source.read_bytes()
            if entry["ownership"] != "editable-bootstrap" and _sha(data) != entry["sha256"]:
                raise _CaseFailure("installed topology drifted at {0}; no healthy copy was substituted".format(relative))
            destination = safe_destination(repo, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            os.chmod(str(destination), source.stat().st_mode & 0o777)
        settings = self.target.root / self.state["settings_path"]
        if not settings.is_file():
            raise _CaseFailure("installed local settings are missing")
        copied_settings = repo / self.state["settings_path"]
        copied_settings.parent.mkdir(parents=True, exist_ok=True)
        copied_settings.write_bytes(settings.read_bytes())
        self._git(repo, "init", "-q")
        self._git(repo, "config", "--local", "user.email", "admission@example.invalid")
        self._git(repo, "config", "--local", "user.name", "Omama admission")
        (repo / ".omama-no-hooks").mkdir()
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "tracked.txt")
        self._git_no_hooks(repo, "commit", "-qm", "base")
        return repo

    def _git(self, repo, *args, expected=0):
        # Scratch repositories measure this installation, not the adopter's
        # global signing, template or line-ending configuration.  The pins are
        # command arguments, so they reach Git subprocesses only.
        result = _run(git_scratch_command(repo, *args), repo)
        _require(result.returncode == expected, "git {0} exited {1}, expected {2}".format(args[0], result.returncode, expected), result)
        return result

    def _git_no_hooks(self, repo, *args, expected=0):
        return self._git(repo, "-c", "core.hooksPath=.omama-no-hooks", *args, expected=expected)

    def _gate(self, repo):
        if not self.shell:
            raise _CaseFailure("required sh/Git Bash is unavailable; install Git Bash or set CLAUDE_CODE_GIT_BASH_PATH")
        payload = json.dumps({"cwd": str(repo), "stop_hook_active": False, "hook_event_name": "Stop"})
        env = _clean_env({"CLAUDE_PROJECT_DIR": repo.as_posix()})
        return _run([self.shell, "-c", self.command], repo, env=env, input_text=payload)

    def _write_card_commit(self, repo, verify, tier="S1", review=None):
        (repo / "CARD.yaml").write_text(_card(verify, tier=tier), encoding="utf-8")
        paths = ["CARD.yaml"]
        if review is not None:
            (repo / "CARD.review.md").write_text(review, encoding="utf-8")
            paths.append("CARD.review.md")
        self._git_no_hooks(repo, "add", *paths)
        self._git_no_hooks(repo, "commit", "-qm", "card")

    def receipt_s1(self):
        repo = self.copy_topology("receipt-s1")
        self._write_card_commit(repo, "git rev-parse --verify refs/heads/omama-admission-never")
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        red = self._gate(repo)
        _require(red.returncode == 2 and "BLOCK[VERIFY-RED]" in red.stderr and "SCHEMA" not in red.stderr,
                 "valid S1 failing verify did not reach installed VERIFY-RED/2", red)
        (repo / "CARD.close").unlink()
        self._write_card_commit(repo, "git diff --quiet HEAD --")
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        green = self._gate(repo)
        _require(green.returncode == 0 and "VERIFIED" in green.stdout,
                 "installed S1 green did not close VERIFIED/0", green)
        _require(not (repo / "CARD.close").exists(), "installed S1 green did not consume CARD.close")
        receipt = json.loads((repo / "CARD.receipt.json").read_text(encoding="utf-8"))
        rev = self._git(repo, "rev-parse", "HEAD").stdout.strip()
        pinned = [
            "git", "-C", str(repo), "-c", "core.quotepath=false",
            "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
            "-c", "diff.interHunkContext=0", "diff", "--no-ext-diff",
            "--no-color", "--no-textconv", "-U3", "HEAD", "--", ".",
            ":(exclude)CARD.receipt.json",
        ]
        diff = _run(pinned, repo)
        _require(diff.returncode == 0, "could not recompute receipt diff binding", diff)
        diff_bytes = diff.stdout.encode("utf-8")
        _require(receipt.get("rev") == rev and receipt.get("diff_sha") == _sha(diff_bytes)
                 and receipt.get("patch_id") == ("empty-diff" if not diff_bytes else receipt.get("patch_id")),
                 "VERIFIED receipt HEAD/diff binding is not recomputable")
        return "valid failing verify produced VERIFY-RED/2; green produced VERIFIED/0, consumed close, and bound recomputable HEAD/diff"

    def receipt_s3(self):
        repo = self.copy_topology("receipt-s3")
        verify = "git diff --quiet HEAD --"
        self._write_card_commit(repo, verify, tier="S3", review=_REVIEW_INVALID)
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        red = self._gate(repo)
        _require(red.returncode == 2 and "BLOCK[S3-REVIEW]" in red.stderr
                 and "missing-non-findings" in _output(red),
                 "present PASS review without Non-findings did not reach the installed checker", red)
        (repo / "CARD.close").unlink()
        (repo / "CARD.review.md").write_text(_REVIEW_VALID, encoding="utf-8")
        self._git_no_hooks(repo, "add", "CARD.review.md")
        self._git_no_hooks(repo, "commit", "-qm", "valid review")
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        green = self._gate(repo)
        _require(green.returncode == 0 and "VERIFIED" in green.stdout,
                 "valid S3 review did not close VERIFIED/0", green)
        filler = "".join("- advisory padding {0}\n".format(index) for index in range(20))
        over = _REVIEW_VALID.replace("## Non-findings", filler + "\n## Non-findings")
        (repo / "CARD.review.md").write_text(over, encoding="utf-8")
        self._git_no_hooks(repo, "add", "CARD.review.md")
        self._git_no_hooks(repo, "commit", "-qm", "over budget review")
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        advisory = self._gate(repo)
        _require(advisory.returncode == 0 and "WARNING:" in advisory.stdout and "over-budget" in advisory.stdout,
                 "structurally valid over-budget review did not warn and close under advisory budgets", advisory)
        return "installed checker rejected genuine missing Non-findings; valid and advisory-over-budget S3 reviews closed VERIFIED/0"

    def missing_validator(self):
        repo = self.copy_topology("missing-validator")
        missing = repo / "tools/omama/work-order/validate_work_order.py"
        missing.unlink()
        self._write_card_commit(repo, "git diff --quiet HEAD --")
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        result = self._gate(repo)
        _require(result.returncode == 2 and "BLOCK[SCHEMA]" in result.stderr and "validator unrunnable" in result.stderr,
                 "removed installed validator was masked or not named separately", result)
        return "removed installed validator produced SCHEMA/2 while healthy package/source copies remained elsewhere"

    def missing_checker(self):
        repo = self.copy_topology("missing-checker")
        (repo / "tools/omama/output-discipline/scripts/check_artifact.py").unlink()
        self._write_card_commit(repo, "git diff --quiet HEAD --", tier="S3", review=_REVIEW_VALID)
        (repo / "CARD.close").write_text("CLOSE\n", encoding="utf-8")
        result = self._gate(repo)
        _require(result.returncode == 2 and "BLOCK[S3-REVIEW]" in result.stderr,
                 "removed installed checker was masked or did not produce S3-REVIEW/2", result)
        return "removed installed checker produced S3-REVIEW/2 while healthy package/source copies remained elsewhere"

    def missing_gate(self):
        repo = self.copy_topology("missing-gate")
        (repo / "tools/omama/receipt-gate/receipt_gate.py").unlink()
        result = self._gate(repo)
        _require(result.returncode != 0, "removed installed gate was reconstructed or masked", result)
        return "exact managed command failed after only the installed scratch gate was removed; no fallback was reconstructed"

    def _synthetic_privacy(self, repo, state="populated"):
        token_relative = ".omama-admission-tokens.txt"
        doc = {"deny_regexes": [], "deny_filenames": [], "tokens_file": token_relative}
        if state == "null":
            doc["tokens_file"] = None
        elif state == "omitted":
            doc.pop("tokens_file")
        (repo / "privacy-deny.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        token = "OMAMA_" + "ADMISSION_LITERAL_" + self.state["bundle_id"][:12]
        token_path = repo / token_relative
        if state == "populated":
            token_path.write_text(token + "\n", encoding="utf-8")
        elif state == "empty":
            token_path.write_bytes(b"")
        elif state == "comment":
            token_path.write_text("# intentionally empty synthetic token layer\n", encoding="utf-8")
        return token

    def _hook(self, repo, name):
        if not self.shell:
            raise _CaseFailure("required sh/Git Bash is unavailable; install Git Bash or set CLAUDE_CODE_GIT_BASH_PATH")
        return _run([self.shell, ".githooks/" + name], repo, env=_clean_env())

    def token_states(self):
        repo = self.copy_topology("token-states")
        (repo / "clean.txt").write_text("clean\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "clean.txt")
        self._synthetic_privacy(repo, "missing")
        missing = self._hook(repo, "pre-commit")
        _require(missing.returncode != 0 and "missing-tokens-file" in missing.stderr
                 and ".omama-admission-tokens.txt" in missing.stderr and "create this gitignored file" in missing.stderr,
                 "missing token file did not fail with path and remedy", missing)
        for state in ("empty", "comment"):
            self._synthetic_privacy(repo, state)
            zero = self._hook(repo, "pre-commit")
            _require(zero.returncode == 0
                     and zero.stderr.count("notice privacy-hook: tokens file") == 1
                     and "notice privacy-hook: tokens file" not in zero.stdout,
                     "{0} tokens did not emit exactly one nonblocking scanner notice".format(state), zero)
        for state in ("null", "omitted"):
            self._synthetic_privacy(repo, state)
            disabled = self._hook(repo, "pre-commit")
            _require(disabled.returncode == 0 and "zero literals" not in _output(disabled),
                     "{0} tokens_file state was not silent".format(state), disabled)
            self.report.add(
                "OK", "privacy-token-" + state,
                "intentional {0} tokens_file state was silent; no real-list completeness was implied".format(state),
            )
        token = self._synthetic_privacy(repo, "populated")
        (repo / "clean.txt").write_text("prefix " + token + " suffix\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "clean.txt")
        populated = self._hook(repo, "pre-commit")
        _require(populated.returncode != 0 and "BLOCKED deny-token clean.txt" in populated.stdout
                 and token not in _output(populated),
                 "populated synthetic token was not enforced without value disclosure", populated)
        return "missing path/remedy, exactly one empty/comment-only notice per run, silent null/omitted, and populated no-value-disclosure enforcement passed"

    def precommit_git(self):
        repo = self.copy_topology("git-precommit")
        token = self._synthetic_privacy(repo, "populated")
        self._git(repo, "config", "--local", "core.hooksPath", ".githooks")
        before = self._git(repo, "rev-parse", "HEAD").stdout.strip()
        (repo / "challenge.txt").write_text("prefix " + token + " suffix\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "challenge.txt")
        blocked = self._git(repo, "commit", "-m", "must block", expected=1)
        _require("BLOCKED deny-token challenge.txt" in _output(blocked) and token not in _output(blocked),
                 "real git commit did not execute the installed pre-commit chainer/wrapper", blocked)
        _require(self._git(repo, "rev-parse", "HEAD").stdout.strip() == before, "blocked pre-commit changed HEAD")
        (repo / "challenge.txt").write_text("clean replacement\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "challenge.txt")
        allowed = self._git(repo, "commit", "-m", "clean commit")
        _require(allowed.returncode == 0, "clean real commit was not allowed", allowed)
        return "real git pre-commit blocked the synthetic literal and allowed clean replacement"

    def premerge_git(self):
        repo = self.copy_topology("git-premerge")
        token = self._synthetic_privacy(repo, "populated")
        self._git(repo, "config", "--local", "core.hooksPath", ".githooks")
        main = self._git(repo, "branch", "--show-current").stdout.strip()
        self._git(repo, "checkout", "-q", "-b", "admission-feature")
        (repo / "merge-challenge.txt").write_text("prefix " + token + " suffix\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "merge-challenge.txt")
        self._git_no_hooks(repo, "commit", "-qm", "feature")
        self._git(repo, "checkout", "-q", main)
        blocked = self._git(repo, "merge", "--no-ff", "admission-feature", "-m", "must block merge", expected=1)
        _require("BLOCKED deny-token merge-challenge.txt" in _output(blocked) and token not in _output(blocked),
                 "real git merge did not execute the installed pre-merge-commit chainer/wrapper", blocked)
        self._git(repo, "merge", "--abort")
        self._git(repo, "checkout", "-q", "admission-feature")
        (repo / "merge-challenge.txt").write_text("clean merge replacement\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "merge-challenge.txt")
        self._git_no_hooks(repo, "commit", "--amend", "-qm", "clean feature")
        self._git(repo, "checkout", "-q", main)
        allowed = self._git(repo, "merge", "--no-ff", "admission-feature", "-m", "clean merge")
        _require(allowed.returncode == 0, "clean real merge was not allowed", allowed)
        return "real git pre-merge-commit blocked the synthetic literal and allowed the clean merge"

    def missing_privacy_component(self, label, relative, marker=None):
        repo = self.copy_topology("missing-" + label)
        self._synthetic_privacy(repo, "comment")
        (repo / relative).unlink()
        (repo / "clean.txt").write_text("clean\n", encoding="utf-8")
        self._git_no_hooks(repo, "add", "clean.txt")
        result = self._hook(repo, "pre-commit")
        _require(result.returncode != 0 and (marker is None or marker in _output(result)),
                 "removed installed {0} was masked or reconstructed".format(label), result)
        return "removed installed {0} failed while healthy package/source copies remained elsewhere".format(label)

    def complete_payload_commit(self):
        repo = self.copy_topology("complete-payload")
        config = json.loads((repo / "privacy-deny.json").read_text(encoding="utf-8"))
        token_path = config.get("tokens_file")
        token_note = "target policy deliberately disables the literal layer"
        if isinstance(token_path, str) and token_path:
            destination = safe_destination(repo, token_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("# synthetic admission only; adopter token values were not read\n", encoding="utf-8")
            token_note = "a synthetic comment-only token file was used; adopter token values were not read"
        destinations = [
            entry["destination"] for entry in self.manifest["files"]
            if safe_destination(self.target.root, entry["destination"]).is_file()
        ]
        self._git_no_hooks(repo, "add", "--", *destinations)
        self._git(repo, "config", "--local", "core.hooksPath", ".githooks")
        committed = self._git(repo, "commit", "-m", "exact installed payload")
        _require(committed.returncode == 0, "complete installed payload self-blocked under its shipped wrapper/config", committed)
        for relative in destinations:
            target_bytes = safe_destination(self.target.root, relative).read_bytes()
            blob = _run_bytes(["git", "-C", str(repo), "show", "HEAD:" + relative], repo)
            if blob.returncode != 0:
                detail = (blob.stderr or b"").decode("utf-8", "replace").strip().splitlines()
                _require(
                    False,
                    "git show failed for committed payload at {0}: exit={1}; stderr_tail={2}"
                    .format(relative, blob.returncode, detail[-1][:300] if detail else "none"),
                )
            _require(
                blob.stdout == target_bytes,
                "committed payload bytes differ from installed target at {0}: installed_sha256={1}; blob_sha256={2}; installed_size={3}; blob_size={4}"
                .format(relative, _sha(target_bytes), _sha(blob.stdout), len(target_bytes), len(blob.stdout)),
            )
        absent = "; absent editable material preserved: " + ", ".join(self.absent_editable) if self.absent_editable else ""
        return "all {0} currently installed manifest files committed through the shipped wrapper and final config; {1}{2}".format(len(destinations), token_note, absent)

    def run(self):
        if not self.shell:
            self.report.add("NOT-RUN", "shell-capability", "required sh/Git Bash is unavailable; install Git Bash or set CLAUDE_CODE_GIT_BASH_PATH")
            return
        self.case("receipt-s1", self.receipt_s1)
        self.case("receipt-s3", self.receipt_s3)
        self.case("missing-validator", self.missing_validator)
        self.case("missing-checker", self.missing_checker)
        self.case("missing-gate", self.missing_gate)
        self.case("privacy-token-states", self.token_states)
        self.case("privacy-pre-commit", self.precommit_git)
        self.case("privacy-pre-merge-commit", self.premerge_git)
        self.case(
            "missing-scanner",
            lambda: self.missing_privacy_component(
                "scanner", "tools/omama/privacy-hook/scan_staged.py", "missing-scanner"),
        )
        self.case(
            "missing-wrapper",
            lambda: self.missing_privacy_component("wrapper", ".githooks/privacy-pre-commit"),
        )
        self.case("complete-payload-commit", self.complete_payload_commit)


def admission(target, state, scratch_root):
    """Run mandatory admission from installed target bytes in private scratch."""
    report = AdmissionReport()
    try:
        harness = _Harness(target, state, scratch_root, report)
        harness.run()
    except Exception as exc:
        report.add("VIOLATION", "installed-topology", "could not construct admission solely from installed target bytes: {0}: {1}".format(type(exc).__name__, exc))
    return report
