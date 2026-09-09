# Vendoring Omama files

Omama's CLI records the source identity of the bundle it installs. If you copy a piece
manually, preserve the same property yourself: copy upstream bytes without reformatting,
record exactly where they came from, and keep repository-owned policy separate from
Omama's built-in rules. The CLI does **not** edit formatter or linter configuration.

## Preserve byte identity

Exclude copied Omama files from every formatter, linter, editor action, and pre-commit
step that could rewrite them. Reformatting makes a local copy differ from upstream and
removes the clean baseline needed to review a later update.

Adapt these examples to the paths you actually copied; do not replace an existing
configuration wholesale:

```toml
# pyproject.toml — Ruff, additive to the default exclusions
[tool.ruff]
extend-exclude = ["tools/omama/**", ".githooks/privacy-pre-commit"]
force-exclude = true # also honor exclusions when a hook passes files explicitly

# Black uses a regex; force-exclude also covers explicit filenames from hooks/editors.
[tool.black]
force-exclude = '''
^/tools/omama/|^/\.githooks/privacy-pre-commit$
'''
```

```text
# .prettierignore (gitignore syntax)
tools/omama/
.githooks/privacy-pre-commit
```

For legacy ESLint/eslintrc, put the same paths in `.eslintignore` (or
`ignorePatterns`). For current flat config, `.eslintignore` is not loaded; use a global
ignore in `eslint.config.js`:

```js
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  globalIgnores(["tools/omama/**", ".githooks/privacy-pre-commit"]),
  // existing configuration
]);
```

Run each tool's check mode after editing its configuration and confirm it neither reports
nor rewrites the copied paths. The exact syntax is tool-version dependent; the examples
follow the official Ruff, Black, Prettier, and ESLint flat-config documentation current
when this guide was written.

For Black, ordinary exclusions do not cover explicitly named files. Its
[force-exclude option](https://black.readthedocs.io/en/stable/usage_and_configuration/the_basics.html#force-exclude)
also applies when a hook or editor passes a vendored filename directly.

## Record the source

Put `PROVENANCE.md` next to the copied files. Fill every placeholder from the upstream
commit you actually inspected; a branch name or package version alone is not a commit
identity. Use this template verbatim, adding rows without changing its fields:

```markdown
# PROVENANCE

- Upstream: <UPSTREAM_REPOSITORY_URL>
- Upstream commit: <FULL_40_CHARACTER_GIT_SHA>
- License: MIT; copied license: <RELATIVE_PATH_TO_COPIED_LICENSE>
- Copied by: <TEAM_OR_AUTOMATION_IDENTITY>
- Copied on: <YYYY-MM-DD>

| Upstream path | Vendored path | SHA-256 |
|---|---|---|
| <UPSTREAM_PATH> | <LOCAL_PATH> | <64_HEX_SHA256> |
```

The source URL, full SHA, copied-file list, license, and hashes are traceability data.
They do not make a locally editable provenance note cryptographic proof of authenticity.
Review a future update against that recorded SHA and never treat `init` rerun as an
implicit update: the CLI repairs only eligible missing files from the same bundle and
refuses another bundle or conflicting immutable drift.

## Keep policy separate from built-in rules

`privacy-deny.json` is team-owned policy: filenames, custom regular expressions, and an
optional literal-token file. The scanner also contains eight built-in credential rules.
Read the complete list and its narrow allowlist behavior in
[privacy-hook/ADOPTION.md](privacy-hook/ADOPTION.md#built-in-rules-versus-team-policy)
before adding a custom expression. A team rule never receives a built-in allowlist
exception.

As optional hardening, add a custom rule for your own home path so generated artifacts do
not publish a username and machine layout. Use a benign, machine-independent placeholder
in documentation and generate the real escaped value locally; never commit the real path
to this guide or copy this example literally:

```json
{
  "id": "operator-home-path",
  "pattern": "<REGEX_ESCAPED_ABSOLUTE_HOME_PATH>"
}
```

This is adopter policy, not a built-in Omama rule. Test it with a synthetic path such as
`/example-home/operator-name/` or `C:/example-home/operator-name/`, then test your local
value without printing it into logs or receipts.

## Paths in Claude settings

Use forward slashes in JSON command paths on every platform, including Windows. This
avoids the escaped-backslash error class and is the form certified by Omama's wiring
checker. Keep the absolute interpreter path machine-local and use only
`$CLAUDE_PROJECT_DIR` for the repository portion. See
[receipt-gate/adapt/settings.example.json](receipt-gate/adapt/settings.example.json).
