# Hermes Project Groups

A shareable Hermes plugin that organizes flat Projects into collapsible groups in Desktop's native **PROJECTS** section without changing repositories or Project identity.

![Status: alpha](https://img.shields.io/badge/status-alpha-orange)

## Features

- Contributes one stable `projects.grouping` provider to the existing native Projects list.
- Creates groups through Hermes's native folder-plus dialog.
- Assigns and unassigns Projects through each native Project menu.
- Persists collapse state, group order, and membership per active backend/profile.
- Keeps native Project rows, activation, sessions, worktrees, menus, and appearance core-owned.
- Leaves the canonical Hermes Project database, repositories, and filesystem paths untouched.
- Preserves CUE++, RGC-LABS, and RGC Legacy defaults when migrating an existing local cache.

## Requirements

- A recent Hermes Desktop build with the Desktop Plugin SDK.
- Existing Hermes Projects to organize.

## Install

Requires a Hermes build with unified Desktop plugins, backend plugin APIs, and the native `projects.grouping` contribution contract. There is intentionally no standalone route, navigation item, or Project Groups page.

### One-click Desktop install

[Install Project Groups in Hermes](hermes://plugin/install?repo=cueplusplus/hermes-plugin-project-groups)

Hermes opens a confirmation dialog, detects the agent and Desktop halves, and lets the user choose what to install.

### Official CLI installer

```bash
hermes plugins install cueplusplus/hermes-plugin-project-groups
hermes plugins enable project-groups
```

The repository follows Hermes's unified plugin layout, so the official installer places the backend under `~/.hermes/plugins/project-groups/` and Desktop loads `desktop/plugin.js` from the same package. Restart the dashboard/gateway only when enabling the backend persistence half.

### Development checkout

A symlink keeps Desktop hot reload attached to a working tree:

```bash
mkdir -p ~/.hermes/desktop-plugins/project-groups
ln -sf "$PWD/plugin.js" ~/.hermes/desktop-plugins/project-groups/plugin.js
```

Hermes watches this directory. If the page does not appear within a few seconds, run **Reload desktop plugins** from the command palette.

## Development

```bash
npm test
npm run check
```

The Desktop entrypoint is plain, dependency-free ESM with no build step. `plugin.js` and `desktop/plugin.js` are kept byte-identical. Tests cover the reusable grouping rules, authoritative backend mutations, provider publication semantics, offline behavior, migration, and process reloads.

## Agent and LLM awareness

The unified package registers three native Hermes surfaces when its agent half is enabled:

- `project_groups_list` — current groups, member Projects/paths, and ungrouped Projects;
- `project_group_get` — one group by id or name;
- `project-groups:project-groups` — a bundled skill explaining the model and safe interaction rules.

It also contributes a short bounded system-prompt section so new sessions know that groups are organizational parents—not working directories—and that local/remote Project IDs remain independent.

No MCP server is required. MCP would create a second protocol/process for data already owned by the current Hermes profile. Native plugin tools are smaller, profile-aware, appear in the normal Hermes tool registry, and use the same backend state as the Desktop plugin.

## Storage and scope

The preferred persistence path is the plugin's profile-scoped backend:

```text
$HERMES_HOME/project-groups/state.json
```

Writes are lock-protected, validated, bounded, and atomic. Create, assign/unassign, and collapse mutations succeed on the backend before Desktop updates its cache or publishes a new snapshot. The Desktop copy under `hermes.plugin.project-groups.state.v1` is a read-only offline fallback and one-time migration source; it is never an offline write authority. Project IDs and filesystem paths are backend/profile-specific, so local and remote Projects remain distinct even when they share a group label.

## Current limitations

- Desktop builds without `projects.grouping` cannot render the native grouping provider; no duplicate page fallback is registered.
- Cross-gateway organization identity is not merged automatically; each backend/profile owns its Project assignments.
- Nested groups and grouped drag-reordering are outside the v1 native contract.
- When the backend is unavailable, the last cache remains visible but create, move, and collapse controls are unavailable.

## License

MIT
