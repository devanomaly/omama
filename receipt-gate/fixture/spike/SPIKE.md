# Step-0 spike — Stop-hook blocking semantics, Claude Code 2.1.236 (2026-08-19)

Every fact below was OBSERVED on this machine (Windows 11, `claude --version` =
2.1.236), not read from docs. Raw evidence: `spike_log.jsonl` (the hook's captured
stdin payloads) + the headless run's result JSON (final reply text).

Setup: scratch dir with `.claude/settings.json` declaring a Stop hook →
`python3 spike_stop_hook.py` (this directory), which logs stdin and exits 2 with the
stderr instruction "include the exact token RESUMED-AFTER-BLOCK in your reply" on its
FIRST invocation, 0 afterwards. Run: `claude -p "say READY" --output-format json`.

## Observed

1. **Stop hooks FIRE in `-p` (headless) mode.** Two invocations logged in one run.
2. **Exit 2 BLOCKS the stop and the hook's stderr is fed back to the model.** Proof:
   the run's final `result` is exactly `RESUMED-AFTER-BLOCK` — that token exists
   nowhere except the hook's stderr; `num_turns: 2`. The model saw the stderr,
   complied, and stopped again.
3. **`stop_hook_active`** arrives `false` on the first firing, `true` on the re-stop
   after a block.
4. **The stdin payload carries `cwd`** (absolute session dir), plus `session_id`,
   `transcript_path`, `hook_event_name: "Stop"`, `last_assistant_message`,
   `permission_mode`. The gate's `os.getcwd()` fallback is therefore a fallback, not
   the primary path.
5. **The hook fires once per response completion** (first stop + the post-block stop
   both fired it) — consistent with per-turn firing in interactive sessions, the
   premise of the close-intent model. (Interactive per-turn firing itself was not
   separately instrumented; the close-intent design is safe under either frequency.)

## Verdict

The plan's assumed contract (exit 0 = allow, exit 2 = block + stderr feedback,
`stop_hook_active` loop marker, `cwd` in stdin) holds on the installed version. No
surprising semantics → the ratified stop-and-ask/xhigh checkpoint was not triggered.
