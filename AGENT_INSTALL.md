# Agent-led installation protocol

This is the **canonical installation procedure** for Hermes Project Groups. You are the installation agent. Treat installation as a version-pinned source and state migration, not as a copy-paste plugin command.

> [!IMPORTANT]
> The native UI currently requires upstream draft PR [NousResearch/hermes-agent#93229](https://github.com/NousResearch/hermes-agent/pull/93229) or a compatibility bundle proven for the exact Hermes revision. The bundled series supports only base `981101239a064c020a9d18fc3b1060ae306934ed`. The plugin pin is `0c58068035202f5defcf25270bee37ffd63d9a9b`.

## Non-negotiable rules

1. Inspect before mutation; prefer current official Hermes docs and live source over assumptions in this file.
2. Do not publish, push, open/modify a PR, or mutate an external repository.
3. Do not hand-edit Hermes configuration; use supported `hermes config` commands after recording prior values.
4. Do not auto-resolve, skip, or continue a patch conflict. Never call a conflicted apply compatible.
5. Do not apply this old series to a different base—even if `git am --3way` might succeed.
6. Do not restart or stop a shared Desktop, Gateway, dashboard, bot, or active session without explicit owner approval and a safe window.
7. Do not use `--force` to bypass an unreviewed dangerous plugin verdict. Stop and report it.
8. Keep backups outside every source/plugin directory that may be replaced. Confirm each backup is readable before mutation.
9. Report the preflight, proposed mutations, backup manifest, and restart needs to the human before making changes. If approval policy requires confirmation, wait.

## Phase 1 — inspect the live environment

Record commands, paths, output, and timestamps in an installation report.

1. Read current official references, starting with:
   - <https://hermes-agent.nousresearch.com/docs/llms.txt>
   - the current Plugins, Profiles, Configuration, Desktop, update/build, and security pages it links;
   - `hermes --help`, `hermes plugins install --help`, `hermes plugins doctor --help`, `hermes profile --help`, and relevant subcommand help;
   - live Hermes source for plugin loading, Desktop contribution areas, build/test commands, config path resolution, session state, and Projects persistence.
2. Identify the effective Hermes executable and version, install method, source checkout, current source `HEAD`, branch/detached state, remotes, tags, dirty/untracked files, submodules, and existing patch marker.
3. Resolve the **effective profile and home**. Respect `HERMES_HOME` and named profiles; do not assume `~/.hermes`.
4. Identify local versus remote Gateway ownership. The backend plugin belongs on the agent host/profile that owns Projects; the compatible Desktop belongs on the client rendering the sidebar.
5. Inventory existing plugin copies at both unified and standalone Desktop doors, their revisions, enablement, permissions, health, and duplicate plugin IDs.
6. Locate and inspect, without changing:
   - config and supported config readback;
   - Project Groups state and Desktop cache/migration state;
   - the canonical Projects database and SQLite sidecars (`-wal`, `-shm`) if present;
   - Desktop installation/build and user-data location;
   - active Hermes/Gateway/Desktop/dashboard/bot processes and active/busy sessions.
7. Confirm the immutable GitHub install syntax from the live CLI. Expected current form:

   ```text
   hermes plugins install cueplusplus/hermes-plugin-project-groups \
     --ref 0c58068035202f5defcf25270bee37ffd63d9a9b \
     --no-enable
   ```

If any authoritative path or state cannot be identified, stop and ask rather than guessing.

## Phase 2 — timestamped, full, recoverable backups

Create one UTC-timestamped backup root with restrictive permissions. Before mutation, capture a manifest containing absolute source/destination paths, type, size, checksum, owner/mode where available, Git revisions, profile, Hermes version, process/session inventory, and exact restore commands.

Back up **all** of the following when present:

- **Hermes source:** current branch/ref, `HEAD`, status/diff, untracked-file inventory, remotes, submodules, a full `git bundle --all`, and any local source archive needed to restore non-Git files.
- **Compatibility bundle:** this entire repository or patch directory, `series`, every patch, base/patched-head pins, and checksums.
- **Configuration:** effective profile config plus relevant plugin install metadata and a supported config readback; include secrets only if already required by the user's secure backup policy—never print them in the report.
- **Installed plugin:** every existing unified/standalone copy, symlink target, revision, status, and permissions.
- **Project Groups state:** `$HERMES_HOME/project-groups/`, relevant plugin cache/export, and any migration source.
- **Projects DB:** the exact Projects SQLite database and sidecars. Use a SQLite-consistent backup (`sqlite3 … '.backup …'` or the application's supported method), not a live byte-copy alone; also record `PRAGMA integrity_check` on the backup.
- **Runtime state:** active process/session inventory and the owner-approved restart plan. This is evidence, not permission to stop anything.

Use the bundle tool's source/bundle backup as an additional source safety layer. **This tool backs up only the Hermes Git source and this patch bundle. It does not back up config, installed plugins, Project Groups state, `projects.db`, Desktop user data, or runtime state; all of those require the separate full-environment backup above.**

```text
python3 patches/hermes-0.20.5-project-groups/apply.py apply /path/to/hermes-agent \
  --backup-root /absolute/safe/backup/root
```

Do not run that yet: its apply phase is allowed only after exact-supported classification below. For preflight, run `preflight` only.

Verify recovery before proceeding: parse the manifest, verify checksums, `git bundle verify`, list archives, open the backed-up SQLite DB read-only and run integrity check, and prove the recorded plugin/config/state paths can be restored. A backup that has not been read back is not complete.

## Phase 3 — dry preflight and compatibility classification

Run the non-mutating preflight:

```text
python3 patches/hermes-0.20.5-project-groups/apply.py preflight /path/to/hermes-agent
```

Cross-check its result against live source and classify exactly one:

### `exact-supported`

All of these must hold:

- `HEAD` equals `981101239a064c020a9d18fc3b1060ae306934ed`;
- worktree is clean;
- expected Hermes Desktop structure is present;
- all 14 patches exist in `series` order;
- no prior/partial `git am` or ambiguous patch marker exists;
- plugin full SHA and documented build/test commands remain exact.

Only this classification may use the bundled series directly.

### `safely-adaptable`

The target differs, but source inspection suggests the feature can be ported without changing its safety contract. **Do not apply the old series.** Instead:

1. create a new directory named for the exact target Hermes version/base;
2. port/rebase deliberately on a dedicated branch, reviewing every semantic change;
3. regenerate a complete ordered series with `git format-patch`;
4. update exact base, patched-head, patch count, plugin pin, README, and tests;
5. clone a new clean disposable Hermes checkout;
6. check out the exact new base;
7. apply only the newly generated bundle through its own script;
8. install dependencies and pass the full Desktop/Python/plugin verification below;
9. build and exercise isolated native UI;
10. preserve proof output and request human review before any real installation.

Until every step passes, classification remains incompatible for installation. Never “adapt” by resolving conflicts during installation.

### `incompatible`

Stop without source/plugin/config/runtime mutation. Report the exact failed checks, the safest next step, and tested rollback/readback status.

## Phase 4 — exact-supported application

After the human has seen the report/backups and policy permits mutation:

1. Work on a dedicated local branch or disposable worktree at the exact base—not an unknown main branch.
2. Run `apply.py apply` with the verified external backup root. It creates a source-only full Git bundle, patch archive, SHA-256/size metadata, readback verification results, and JSON restore manifest **before** `git am`. This supplements rather than replaces the full-environment backup in Phase 2.
3. Apply all patches in `series` order. On any failure, stop; do not run `git am --continue`, do not resolve automatically, and do not claim support.
4. Confirm the final marker records the exact supported base and inspect the resulting commit sequence against `series`.

## Phase 5 — install the immutable plugin

On the host/profile that owns the Projects:

1. Validate the source repository and full SHA before installation.
2. Remove or quarantine duplicate plugin doors only after backup; never allow the same plugin ID to load twice.
3. Install disabled with the confirmed CLI syntax and full 40-character SHA:

   ```text
   hermes plugins install cueplusplus/hermes-plugin-project-groups \
     --ref 0c58068035202f5defcf25270bee37ffd63d9a9b \
     --no-enable
   ```

4. Read back installed `HEAD`, clean status, remote, `plugin.yaml`, required files, and checksums. It must equal the full pin exactly.
5. Run `hermes plugins doctor` and inspect all findings. Enable only after health and capability review succeeds, using the supported CLI.
6. Do not restart an active shared Gateway. If backend route mounting requires restart, report it as pending and wait for explicit owner approval and idle sessions.

## Phase 6 — verification

Run and preserve real output for every applicable layer:

### Repository plugin

```text
npm test
npm run check
```

This covers Node behavior, Python backend/agent tests, ESM syntax, entrypoint identity, and temporary-Git-repository patch safety tests.

### Patched Hermes source

Install dependencies using the live official source instructions, then run:

```text
python3 patches/hermes-0.20.5-project-groups/apply.py verify /path/to/hermes-agent
```

The bundle verification includes the deletion dialog/helper tests and `tests/hermes_cli/test_projects_db.py` plus `tests/tui_gateway/test_projects_rpc.py`, using the checkout's `.venv`/`venv` Python when present or `uv run` otherwise. Also run the current repository's required Python test/lint chain and Desktop build/package command discovered in Phase 1. Do not substitute source tests for a packaged Desktop build.

### Isolated runtime and UI

Before touching the normal app, use an isolated `HERMES_HOME`/profile and Desktop user-data directory to prove:

- plugin inventory, doctor, enablement, tools, skill, and prompt section;
- backend API mount and state round-trip;
- native group create, collapse, move/unassign, persistence/reload, and guarded delete;
- native Project activation, sessions, worktrees, menus, and ordering still work;
- no duplicate fallback page/nav or plugin load-error toast;
- local/remote profile switching does not mix Project IDs;
- built/package artifact provenance matches the patched source.

Desktop verification must inspect the rendered UI and exercise interactions; passing unit tests alone is insufficient.

## Phase 7 — restart gate, readback, and handoff

Before any restart, re-read active sessions/processes. If any shared session is active or ownership is unclear, do not restart. Present the command, expected interruption, rollback, and verification plan and wait for explicit approval.

After an approved restart, read back:

- running Hermes/Desktop versions and source/build stamp;
- active profile/home and Gateway target;
- plugin exact `HEAD`, enabled/loaded status, doctor result, tools and skill;
- backend route/state and Project Groups state checksum/schema;
- Projects DB integrity and unchanged Project identity/path records;
- native UI interactions and absence of load errors.

Provide the human with the install report, backup manifest path, checksums, exact pins, verification output, any deferred restart, and all rollback commands. Do not call installation complete while any required layer is merely assumed.

## Rollback

Rollback must be owner-approved and use the manifest from this installation:

1. Re-check active shared sessions; do not restart/stop them without approval.
2. Disable the plugin with the supported CLI, then restore or uninstall only the backed-up target copy.
3. Restore Project Groups state/config/plugin metadata from checksummed backups; use supported config commands rather than hand-editing live config.
4. Restore the Projects DB with the application stopped only in an approved window, including consistent sidecar handling; rerun integrity check.
5. Restore source using the manifest's exact prior `HEAD`/branch or clone from its full Git bundle. `apply.py rollback … --yes` also creates a unique timestamped backup branch before resetting to the pinned base.
6. Rebuild/relaunch the prior Desktop artifact only in an approved window.
7. Read back version, profile, plugin inventory, state checksums, DB integrity, sessions, and native UI. Report anything not restored exactly.

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/cueplusplus-wordmark.svg">
    <img src="assets/cueplusplus-wordmark-dark.svg" alt="CUE++" width="104">
  </picture><br>
  <sub>Safe installation workflow by CUE++</sub>
</p>
