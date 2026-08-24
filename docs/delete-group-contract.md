# Delete Project Group contract

Status: owner-requested, pending adversarial review.

Plugin implementation: v0.4.0 implements the provider/backend delete slice. Core UI, transactional Project renaming, and saga orchestration remain core-owned and are not implemented in this repository.

## Empty group

The native group heading exposes a delete action. Deleting an empty group opens a simple destructive confirmation dialog naming the group. Confirm performs one authoritative backend mutation; cancel makes no changes.

## Non-empty group

Deleting a non-empty group opens a review dialog. It always states that every contained Project will be moved to Ungrouped.

The dialog contains:

- a checkbox, off by default: **Prepend old group name to Project names**;
- when unchecked, no rename preview is rendered;
- when checked, a two-column preview is rendered:
  - left: an expanded tree with the old group heading above every contained Project;
  - right: a flat list of resulting names using `<old group name> · <project name>`;
- explicit Cancel and destructive Approve/Delete controls.

## Rename semantics

When prefixing is enabled:

- trim group and Project labels;
- do not duplicate the prefix if the Project already begins with `<group> · `, case-insensitively;
- preserve stable Project IDs, folders, sessions, boards, worktrees, appearance, and active state;
- reject/resolve name collisions before any write;
- show exact final names in preview.

## Authority and atomicity

The backend group provider owns group deletion and membership. Hermes Projects backend owns Project names. Cross-authority deletion must not silently partially succeed.

The generic core API therefore gains a transactional `projects.rename_many` RPC with compare-and-swap inputs (`id`, `expectedName`, `newName`). It validates every Project and all requested final names before one database transaction, applies all renames or none, and returns the authoritative renamed records.

The grouping provider exposes a CAS mutation:

```ts
deleteGroup?(request: {
  groupId: string
  expectedProjectIds: readonly string[]
  operationId: string
}): Promise<void>
```

Its backend validates the exact expected member set, atomically deletes the group plus assignments/order, and records `operationId` for idempotent response retries.

Core orchestration is a documented saga:

1. re-read and validate the group snapshot/member set;
2. if prefixing, call transactional `projects.rename_many`;
3. call provider `deleteGroup` with expected members and operation ID;
4. if provider deletion fails, transactionally roll Project names back using CAS against the newly applied names;
5. if rollback fails, keep the dialog open, report every affected Project, and force authoritative reconciliation.

Unchecked deletion invokes only provider `deleteGroup`.

There is no claim of distributed atomicity: the rename transaction and provider deletion are separate authorities, but every partial failure has bounded compensation and an explicit visible state.

## UI placement

- Group headings gain a native More/Actions control with Delete group.
- Empty-group confirm is compact.
- Non-empty review is large enough for side-by-side previews and remains keyboard/screen-reader accessible.
- Delete action is disabled while pending.

## Safety

- Never move or rename filesystem folders.
- Never delete Hermes Projects or sessions.
- Stale snapshot/member mismatch aborts before mutation.
- All errors preserve the dialog and current selections for retry.
