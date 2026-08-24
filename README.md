# Hermes Project Groups

**Turn a long, flat Hermes Project list into clear, collapsible groups—without changing Project identity, repositories, worktrees, or paths.**

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#project-status)
[![Hermes Agent plugin](https://img.shields.io/badge/Hermes-Agent-8A63D2)](https://hermes-agent.nousresearch.com/docs)

Hermes Projects are intentionally flat. That is simple at small scale, but product portfolios and multi-repository organizations quickly become hard to scan. Project Groups adds an organizational presentation layer to the **native PROJECTS sidebar**, while Hermes continues to own Project activation, sessions, worktrees, menus, and storage.

> [!IMPORTANT]
> Native Project Groups UI is **not in an official Hermes release yet**. It currently requires the upstream draft [NousResearch/hermes-agent#93229](https://github.com/NousResearch/hermes-agent/pull/93229) or this repository's version-pinned compatibility patch. Do not install the plugin alone and expect native groups to appear.

## Why Project Groups?

- **Find work faster:** collapse product, client, team, or organization groups.
- **Keep Hermes semantics:** a group is a label and membership relationship—not a working directory or parent Project.
- **Stay native:** grouped rows reuse core Project behavior instead of duplicating it on a separate page.
- **Remain profile-safe:** each Hermes backend/profile owns its own assignments; local and remote Project IDs are never silently merged.
- **Recover safely:** backend writes are validated, lock-protected, bounded, and atomic.

## Features

- Native collapsible groups in the existing **PROJECTS** section.
- Native create-group dialog and folder-plus action.
- **Move to group** / **Ungrouped** actions in each Project menu.
- Guarded exact-membership group deletion; deleting a group never deletes Projects.
- Stable group IDs, explicit order, collapse state, and membership.
- Profile-scoped backend persistence with a read-only Desktop cache for offline display and migration.
- Agent tools: `project_groups_list` and `project_group_get`.
- Bundled skill and bounded prompt context explaining group semantics.
- No MCP server, repository moves, path changes, or duplicate Project Groups page.

## Safe installation

Installation is deliberately **agent-led**, because native support may require a source patch and a Desktop build. A Hermes Agent can inspect its live version, checkout, profile, sessions, and official documentation before deciding whether installation is safe.

### Give Hermes one canonical instruction file

Open a Hermes Agent session with access to this repository and your Hermes environment, then say:

> Read and follow `AGENT_INSTALL.md` in this repository. Perform the dry preflight and report the compatibility classification and backup plan before making changes. Do not publish, push, auto-resolve conflicts, or restart active shared sessions.

**Do not manually copy patch commands from the patch README.** [`AGENT_INSTALL.md`](AGENT_INSTALL.md) is the single installation procedure and includes discovery, complete environment backups, compatibility classification, immutable plugin installation, verification, rollback, and readback. The patch script's own source/bundle backup is only one supplemental layer; it does not back up config, plugins, Project Groups state, or the Projects database.

### Confirmed Hermes GitHub installer syntax

The current Hermes CLI accepts both Git URLs and `owner/repo` shorthand, and requires a 40-character immutable commit with `--ref`:

```text
hermes plugins install cueplusplus/hermes-plugin-project-groups \
  --ref 0c58068035202f5defcf25270bee37ffd63d9a9b \
  --no-enable
```

This syntax was confirmed against `hermes plugins install --help` and the live Hermes plugin documentation. It is shown for transparency; the installation agent must run it only after the preflight and backups in `AGENT_INSTALL.md`.

## How it works

The unified plugin has three coordinated parts:

1. **Desktop provider** — contributes one stable `projects.grouping` provider to Hermes's native list.
2. **Profile backend** — stores authoritative state at `$HERMES_HOME/project-groups/state.json` and exposes guarded mutations.
3. **Agent integration** — registers read tools and a skill so agents understand that groups organize Projects but do not change their filesystem scope.

A local Desktop connected to a remote Hermes host needs the compatible Desktop UI locally and the plugin backend enabled on the remote profile that owns the Projects.

## Storage and safety

Authoritative state:

```text
$HERMES_HOME/project-groups/state.json
```

Writes are atomic and validated. Delete uses an exact member-set compare-and-swap plus a bounded durable operation ledger, so retries are idempotent. The Desktop cache (`hermes.plugin.project-groups.state.v1`) is an offline display and migration source, never an offline write authority.

## Compatibility

| Component | Supported pin |
|---|---|
| Plugin | `0c58068035202f5defcf25270bee37ffd63d9a9b` (`v0.4.0`) |
| Bundled patch base | `981101239a064c020a9d18fc3b1060ae306934ed` |
| Patch bundle | `patches/hermes-0.20.5-project-groups/` (19 ordered patches) |
| Upstream path | Draft PR [#93229](https://github.com/NousResearch/hermes-agent/pull/93229) |

A different Hermes revision is never implicitly compatible. The agent must classify it as exact-supported, safely adaptable, or incompatible. “Safely adaptable” means creating a **new versioned bundle**, proving it in a clean clone, and only then considering installation; it never means applying the old series with conflict resolution.

## Development

```bash
npm test
npm run check
```

`plugin.js` and `desktop/plugin.js` remain byte-identical plain ESM. Tests cover grouping rules, backend mutations, deletion CAS/idempotency, provider publication, migration, reloads, and patch installer safety with disposable Git repositories.

## Current limitations

- Native UI requires draft PR #93229 or a proven compatibility patch until the seam ships upstream.
- Groups are profile/backend-specific; same-name groups across gateways are not one entity.
- Nested groups and grouped drag-reordering are outside the v1 contract.
- Offline state is read-only; mutations require the backend.

## Project status

Alpha. The repository is public, but native compatibility remains version-pinned and should be installed only through the reviewed agent-led workflow.

## License

MIT

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/cueplusplus-wordmark.svg">
    <img src="assets/cueplusplus-wordmark-dark.svg" alt="CUE++" width="116">
  </picture><br>
  <sub>Built by CUE++</sub>
</p>
