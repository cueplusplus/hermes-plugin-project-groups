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

Clone the repository, then copy or symlink `plugin.js` into the active Hermes profile:

```bash
mkdir -p ~/.hermes/desktop-plugins/project-groups
cp plugin.js ~/.hermes/desktop-plugins/project-groups/plugin.js
```

For development, a symlink keeps hot reload attached to the checkout:

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

## Storage and scope

Group definitions and assignments are stored under the plugin's namespaced Desktop storage key:

```text
hermes.plugin.project-groups.state.v1
```

They are local to a Hermes Desktop profile. Project IDs and filesystem paths are backend/profile-specific, so the plugin deliberately does not claim that a local Project and a remote Project are the same record.

## Current limitations

- Groups appear on the plugin page, not inline within the built-in Projects list.
- Group state does not yet sync between Hermes profiles or gateways.
- Drag-and-drop ordering is not yet implemented; assignments use a select control.
- The plugin relies on current `projects.*` JSON-RPC methods.

## License

MIT
