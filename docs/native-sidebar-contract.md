# Native Project Groups — implementation contract

**Status:** owner-approved direction; implementation contract for the draft Hermes PR and external Project Groups plugin.  
**Date:** 2026-08-24

## Required UX

Hermes's existing **PROJECTS** section remains the only Project navigation surface.

```text
PROJECTS                           [+ project] [+ folder] [filters]

▾ CUE++
    Analytics                           […]
    Knowledgebase                       […]
    Product Design System               […]

▾ RGC-LABS
    RGC ID                              […]
    Skills                              […]

▾ RGC Legacy
    BTS v3                              […]

  Ungrouped
    Another Project                     […]
```

### Create a group

- A folder-plus control appears beside the existing new-Project control.
- It is visible only when a Project-group provider is active.
- Activating it opens a native small dialog.
- Group name is required, trimmed, unique under the active provider and bounded.
- Creation invokes the active provider's mutation callback.
- Failure is surfaced through native Hermes notification/error UI.

### Move a Project

Each native Project row's existing Actions/More menu gains:

```text
Move to group  ›
    CUE++
    RGC-LABS
    RGC Legacy
    ─────────
    Ungrouped
```

- The submenu is visible only when a Project-group provider is active.
- Current membership is indicated.
- Choosing a group invokes the provider's assign callback using stable Project and group IDs.
- Choosing Ungrouped removes membership.
- No filesystem path, Git checkout, worktree, session or board is moved.

### Group behavior

- Groups expand/collapse in the native Project list.
- Native Project rows remain core-owned and retain activation, session previews/counts, worktrees, context menus and appearance.
- Ungrouped Projects remain accessible even when the provider omits them.
- Unknown/stale Project IDs fail soft into Ungrouped.
- Only one provider wins through normal contribution ordering; core does not merge competing authorities.
- Group order and membership are provider-owned.
- Collapse state may be provider-owned so local/remote profiles remain correctly scoped.

## Generic contribution contract

The core API must be generic and data/action based. It must not import or depend on the CUE++ plugin.

Proposed shape:

```ts
interface ProjectGroupDescriptor {
  readonly id: string
  readonly label: string
  readonly projectIds: readonly string[]
  readonly collapsed?: boolean
}

interface ProjectsGroupingSnapshot {
  readonly groups: readonly ProjectGroupDescriptor[]
}

interface ProjectsGroupingContribution {
  /** Referentially stable until subscribe announces a change. */
  getSnapshot(): ProjectsGroupingSnapshot
  subscribe(listener: () => void): () => void
  createGroup?(name: string): Promise<void> | void
  assignProject?(projectId: string, groupId: string | null): Promise<void> | void
  setGroupCollapsed?(groupId: string, collapsed: boolean): Promise<void> | void
}
```

The implementation may use an equivalent provider/resolver interface if required for reactivity, but these capabilities and ownership boundaries are acceptance criteria.

### Authority and mutation semantics

- The active Hermes profile/backend is authoritative.
- A provider mutation persists first and publishes a new stable snapshot only after success.
- Core performs no optimistic grouping update and keeps the current snapshot visible while pending.
- Backend rejection preserves current presentation and is surfaced through native error UI.
- Offline/older-backend fallback may show cached groups read-only; create/move/collapse controls are unavailable.
- Group names collapse surrounding/internal whitespace, require 1–100 UTF-16 code units, and are unique case-insensitively in the current snapshot. Providers repeat validation authoritatively.
- Repeated Project IDs, stale IDs and malformed descriptors fail soft; first valid claim wins.
- The synthetic Home row is not a Project and remains fixed before provider groups.
- Core owns an **Ungrouped** header whenever real Projects remain unclaimed; it is not collapsible in v1.
- When grouping is active, top-level Project drag-reordering is disabled in v1. Native row, session and worktree interactions remain. A future provider reorder capability may restore grouped DnD.

## Plugin responsibilities

The external `cueplusplus/hermes-plugin-project-groups` plugin owns:

- group IDs, labels, ordering and membership;
- validation and persistence per Hermes profile/backend;
- create, assign/unassign and collapse mutations;
- agent tools and skill explaining/querying groups;
- migration from its earlier local state format.

The separate Project Groups full page and sidebar-nav item are removed from the target UX. The plugin can retain no-page command/palette affordances only if they do not duplicate native management.

## Core responsibilities

Hermes core owns:

- Projects heading folder-plus affordance;
- native create-group dialog;
- native group header rendering;
- Project Actions → Move to group submenu;
- Project rows and their existing behavior;
- safe callback error handling and notification;
- accessibility labels and keyboard behavior;
- provider precedence and fail-soft fallback.

## TDD acceptance cases

1. No provider produces byte-for-byte equivalent flat Project behavior and no new controls.
2. Active provider renders group headers and preserves omitted/stale Projects under Ungrouped.
3. Folder-plus opens the native create dialog and invokes `createGroup` with a trimmed valid name.
4. Duplicate/blank names are rejected before mutation.
5. Project menu shows all groups, marks current membership and invokes `assignProject`.
6. Ungrouped invokes `assignProject(projectId, null)`.
7. Mutation rejection leaves current UI state intact and surfaces a native error.
8. Collapse invokes `setGroupCollapsed` and does not interfere with Project ordering.
9. Native Project menus/actions, sessions, worktrees and activation still operate inside a group.
10. Multiple providers choose one deterministic winner.
11. Runtime provider registration/update/unload is reactive.
12. Plugin state persists across a safe backend/Desktop restart and agent tools report the same memberships.

## Out of scope

- Parent Projects in `projects.db`.
- Moving repositories or filesystem paths.
- Nested groups within groups.
- Cross-profile or cross-backend Project-ID equivalence.
- Bundling the external Project Groups plugin into Hermes core.
