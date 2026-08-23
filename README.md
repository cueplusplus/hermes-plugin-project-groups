# Hermes Project Groups

A shareable runtime plugin for **Hermes Desktop** that organizes flat Hermes Projects into collapsible groups without changing project repositories or Hermes core.

![Status: alpha](https://img.shields.io/badge/status-alpha-orange)

## Features

- Adds a native-looking **Project Groups** page and sidebar navigation row.
- Seeds CUE++, RGC-LABS, and RGC Legacy groups from Project paths/names.
- Create, rename, collapse, and delete groups.
- Assign or unassign Projects through a group picker.
- Activate a Project through Hermes's existing `projects.set_active` RPC.
- Stores group metadata in the plugin's namespaced Desktop storage.
- Leaves the canonical Hermes Project database and repositories untouched.

> Hermes Desktop does not currently expose a contribution slot inside its built-in Projects list. This plugin therefore provides a dedicated grouped page. A future version can adopt an upstream Projects presentation slot if Hermes adds one.

## Requirements

- A recent Hermes Desktop build with the Desktop Plugin SDK.
- Existing Hermes Projects to organize.

## Install

> Requires a Hermes build with unified Desktop plugins and backend plugin APIs (current 2026 Desktop line). Native inline sidebar grouping additionally requires the upstream `projects.presentation` SDK contribution proposed in [NousResearch/hermes-agent#93229](https://github.com/NousResearch/hermes-agent/pull/93229); older builds still get the dedicated Project Groups page.

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

The runtime plugin is plain ESM and has no build step. Its only runtime imports are the SDK-supported modules:

- `@hermes/plugin-sdk`
- `react`
- `react/jsx-runtime`

The reusable grouping rules in `src/groups.js` are covered by Node's built-in test runner.

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

Writes are validated, bounded, and atomic. The Desktop copy under `hermes.plugin.project-groups.state.v1` is retained as an offline/older-backend fallback and migration source. Project IDs and filesystem paths are backend/profile-specific, so a local Project and a remote Project remain distinct records even when they share an organization group name.

## Current limitations

- Groups appear on the plugin page, not inline within the built-in Projects list. An upstream `projects.presentation` contribution seam is being prepared.
- Cross-gateway organization identity is not merged automatically; each backend/profile owns its Project assignments.
- Project ordering currently uses accessible up/down controls; pointer drag-and-drop is planned after the native presentation seam lands.
- The plugin relies on current `projects.*` JSON-RPC methods and degrades to local storage if the backend API is unavailable.

## License

MIT
