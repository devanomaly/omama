# Manual recovery for an unfinished init

[Português (Brasil)](RECOVERY.pt-BR.md)

## 0. `omama init` recovers unambiguous state by itself

Before planning anything, `omama init` reconciles an interrupted installation
automatically when — and only when — every journal entry is unambiguous.

It first establishes **one** owner by taking the canonical repository lock in
the Git common directory (`<git-common-dir>/omama-install.lock`), which every
linked worktree of the repository shares. A lock whose owner may still be
running, or whose identity cannot be established, is never taken: a PID alone
is not identity because PIDs are reused, and age alone is not identity because
a slow install is not a dead one. Only a same-host, same-boot observation that
the recorded process is gone — or is demonstrably a different process — allows
the lock to be reclaimed, and the reclaimed lock is renamed aside as evidence
rather than deleted.

It then classifies every journal entry, **including entries still marked
`applied: false`**, against the bytes actually on disk:

- **before** — the recorded before-image. The operation never took effect.
- **after** — the recorded after-image. The operation did take effect, even if
  the journal had not yet recorded it. This is the real post-replace
  interruption window: a replacement can be durable before its journal update
  is, so an "applied-only" replay would silently skip an already-published
  file.
- **neither** — possibly an external edit made after the failure.

Classification finishes for every entry before anything is changed. If any
entry is **neither**, init changes nothing at all, preserves the journal, the
lock state and every byte, and stops with `recovery-ambiguous` naming the
paths and their recorded hashes. An ambiguous entry never costs the evidence
held by the unambiguous ones.

Use the manual procedure below only when init stops with `recovery-ambiguous`,
stops with `recovery-owner-uncertain`, or reports `unfinished-install` or
`recovery-required` naming `.omama/install-journal.json`. It is a finite
reconciliation of the paths in that journal, not permission to delete
`.omama`, its runtime, the lock, or the journal wholesale.

## 1. Establish quiescence and retain evidence

Stop new `omama init`, Git, and Claude operations in this worktree **and in
every linked worktree of the same repository**, because they share one
canonical lock. Confirm that the init process which reported the failure has
exited. If a lock still exists — the canonical
`<git-common-dir>/omama-install.lock` or the legacy `.omama/install.lock` —
do not remove or steal it: identify its recorded `owner`/`pid`, establish
whether that exact process is still running, and stop here for maintainer help
if ownership is uncertain.

Before changing the target, copy these items to a protected evidence directory
outside the repository and record SHA-256 hashes for both the originals and
copies:

- `.omama/install-journal.json`, byte-for-byte;
- every current path named by `operations`, `owned_trees`, and
  `config_operations` in the journal, including externally changed paths;
- the Git index and config plus any present `CARD.yaml`, `CARD.close`,
  `CARD.review.md`, and receipt files.

Do not add or commit the evidence directory. Keep the journal copy after the
repository is healthy; it contains before-images and ownership data needed to
explain the failed attempt.

## 2. Inspect the actual journal and current hashes

The supported journal has `schema: 1`, a nonempty `owner`, a status recorded
at the boundary the attempt reached (`planned`, `publishing`, `published`,
`runtime-reserved`, `runtime-published`, `activation-planned`, `activated`,
`writing-state`, `state-written` or `recovery-required`), and three finite
lists: `operations`, `owned_trees`, and `config_operations`. A status other
than `recovery-required` means the attempt died before it could record its own
failure; treat every entry by its bytes, not by its `applied` flag. Stop for
maintainer help if the schema differs, a
listed path is outside the worktree, the lock owner is unresolved, or an entry
has an unfamiliar shape. In particular, never follow an old journal's external
Git-config path: current init refuses that unsupported layout before
publication.

For each applied file operation, first compare the current kind/hash/size/mode
with its recorded `before` snapshot, then compare its SHA-256 with
`after_sha256`; retain `before.kind`, `before.sha256`,
`before.mode`, and `before.bytes_b64`. For each config operation, make the same
comparison at its exact recorded path. For each owned tree, confirm its exact
`relative` and `staging_relative` paths are within the worktree, its owner and
marker match, and its complete tree digest matches `tree_sha256`. The journal's
`error` names entries rollback already found divergent; verify them rather than
assuming that list is complete.

This inspection prints hashes and path names only; do not print before-image or
token contents into logs:

```python
# Save outside the repository as inspect_omama_recovery.py, then run:
# "<TRUSTED_PYTHON>" -B inspect_omama_recovery.py "<TARGET_REPOSITORY>"
import hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
journal_path = root / ".omama" / "install-journal.json"
raw = journal_path.read_bytes()
doc = json.loads(raw.decode("utf-8"))
if doc.get("schema") != 1 or doc.get("status") != "recovery-required" or not doc.get("owner"):
    raise SystemExit("STOP: unsupported journal schema/status/owner")

def contained(path):
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit("STOP: path outside worktree: " + str(resolved))
    return resolved

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

print("journal_sha256", hashlib.sha256(raw).hexdigest())
print("owner", doc["owner"], "error", doc.get("error"))
for record in doc.get("operations", []):
    path = contained(root / record["relative"])
    print("file", record["relative"], "applied", bool(record.get("applied")),
          "current", file_hash(path), "installer_after", record.get("after_sha256"),
          "before_kind", record.get("before", {}).get("kind"),
          "before_sha256", record.get("before", {}).get("sha256"))
for record in doc.get("owned_trees", []):
    contained(root / record["relative"])
    contained(root / record["staging_relative"])
    print("tree", record["relative"], "staging", record["staging_relative"],
          "owner", record.get("owner"), "published", bool(record.get("published")),
          "marker_sha256", record.get("marker_sha256"),
          "tree_sha256", record.get("tree_sha256"))
for record in doc.get("config_operations", []):
    path = contained(Path(record["path"]))
    print("config", path, "applied", bool(record.get("applied")),
          "current", file_hash(path), "installer_after", record.get("after_sha256"),
          "before_kind", record.get("before", {}).get("kind"),
          "before_sha256", record.get("before", {}).get("sha256"))
```

The tree row intentionally reports the recorded digest rather than recomputing
it. Recompute the complete relative-path/type/mode/content digest using the
same installed-version implementation or ask the maintainer before removing a
tree; a marker match alone is not enough.

## 3. Reconcile only recorded owned state

Work from the retained journal one entry at a time, in reverse publication
order, and update your evidence notes after every decision:

1. If an applied entry already matches its complete recorded `before` snapshot
   (including missing-before and currently absent), rollback already restored
   it. Record that result and make no change.
2. If an applied file/config current hash equals `after_sha256`, it is still
   exactly the failed attempt's output. Restore only that named entry to its
   recorded before-image: remove that one path when `before.kind` is `missing`,
   or decode `before.bytes_b64`, replace that one file atomically, and restore
   `before.mode` when `before.kind` is `file`.
3. If current state matches neither the complete `before` snapshot nor
   `after_sha256`, treat it as an
   external edit. Do not overwrite or delete it. Preserve its bytes separately
   and decide explicitly whether it is compatible team-owned material (for
   example an intentionally edited `privacy-deny.json`) or must be manually
   integrated/restored before init can accept it. An immutable or generated
   conflict cannot be relabeled as editable.
4. A recorded owned/staging tree that is absent has already been removed. Remove
   one that remains only when its contained path, recorded
   owner, owner marker, and full `tree_sha256` all match. If any differs,
   preserve the entire tree and reconcile its external content; never use
   `rm -rf .omama`, `Remove-Item .omama -Recurse`, or an unconditional runtime
   deletion.
5. Restore a recorded config before-image only when its path is inside the
   worktree and the current file still matches `after_sha256`. If it differs,
   preserve it and reconcile `core.hooksPath` manually. Never write an external
   Git database from this procedure.

Do not remove the active journal until every applied entry is either restored
to its before-image or deliberately retained as compatible team-owned state,
every tree/config entry is accounted for, and protected CARD/index/evidence
hashes still match.

A retained lock is not a dead end. Once the above holds, resolve the lock
before removing the journal:

- If the recorded owner is **running**, stop. Nothing here is safe while a
  live installer owns the repository.
- If the recorded owner is **provably gone** — same host, same boot, and that
  exact process is absent or is demonstrably a different process — rename the
  lock aside as evidence (for example to
  `<git-common-dir>/omama-install.lock.reclaimed-<your-initials>-<date>`)
  rather than deleting it, and record its hash with the rest of the evidence.
- If ownership **cannot be established** — a different host, or a legacy
  `schema: 1` lock that records only a PID — stop and escalate. A PID alone is
  not identity.

Then remove only `.omama/install-journal.json`; retain the protected copy. Do
not remove other `.omama` state as a shortcut.

## 4. Retry admission once

Rerun the same supported init route and bundle selection used originally:

```text
omama init "<TARGET_REPOSITORY>" [--python "<SAME_QUALIFIED_PYTHON>"]
omama doctor "<TARGET_REPOSITORY>"
```

Success requires init's complete dynamic doctor and installed S1/S3/privacy
admission, followed by a standalone `DOCTOR-OK`. Recheck the saved CARD, index,
config, external-edit, and evidence hashes. If retry reports a conflict or
creates another recovery-required journal, stop; preserve both generations of
evidence and use the named violation for maintainer-assisted reconciliation.
