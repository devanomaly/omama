# adapt/ — EXAMPLE — NOT INSTALLED

This directory contains **only an example** of how a team's repository could wire up the
`protect-tests.js` hook. **Nothing here is installed** in `C:\Users\...\.claude\` or in any
real repository. It is a configuration snippet to copy and adapt, not an active artifact.

## File

- `settings.example.json` — a `.claude/settings.json` snippet (the `hooks.PreToolUse` block)
  that, if pasted into a real repository's `settings.json`, would make Claude Code call the hook
  before any `Bash`, `Edit`, `MultiEdit`, or `Write`.

## How a team would adopt this (we did NOT do this here)

1. Copy `../vendor/protect-tests.js` into the team's repository, for example to
   `.claude/hooks/protect-tests.js` (versioned along with the code, not outside it).
2. Copy the `hooks` block from `settings.example.json` into the repository's
   `.claude/settings.json`, swapping `<REPO_ROOT>` for the repository's real absolute path.
3. Test locally with a deliberate attempt to delete or skip a test (see
   `../fixture/`) to confirm the block fires before relying on the protection in production.
4. Communicate to the team: the hook blocks (`permissionDecision: "deny"`) attempts to delete a
   test file (`rm`/`git rm`), rename a test to a "disabled" name
   (`.bak`/`.old`/`.disabled`/etc.), and insert a skip/xfail/ignore marker into an existing
   test. It does **not** block writing new tests nor editing a test's body.

## Why this stays separate from vendor/

`vendor/` is the original hook, untouched, with traceable provenance. `adapt/` is the "how to
plug this into a team repo" layer — purely an example, with no product opinion baked into the
vendored file. This keeps the diff between upstream and what would run locally at zero.
