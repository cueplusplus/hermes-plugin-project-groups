# Hermes 0.20.5 Native Project Groups patch

This directory is a version-pinned Git patch series for adding the native Project Groups extension surface to a Hermes Agent source checkout while the upstream draft PR is pending.

It is intended to be safe for a human **or another coding agent** to apply. The script refuses an unclean checkout, verifies the pinned base exists and is an ancestor, uses `git am --3way`, and runs the focused Desktop test/typecheck chain.

## Pinned compatibility

| Component | Pin |
|---|---|
| Hermes upstream base | `981101239a064c020a9d18fc3b1060ae306934ed` |
| Source line | Hermes Desktop 0.20.5-era checkout |
| Patch count | 9 ordered commits |
| Project Groups plugin | `40e068a4361889d4e46862c49d17ae177fc07d87` |
| Plugin repository | <https://github.com/cueplusplus/hermes-plugin-project-groups> |

This is **not** a floating patch. A newer Hermes version is unsupported until the series is rebased and verification passes again.

## What it adds

- `projects.grouping` public Desktop plugin API;
- grouped Projects in the existing left sidebar;
- folder-plus create-group action beside **PROJECTS**;
- native create-group dialog;
- Project Actions → **Move to group** submenu;
- Home and Ungrouped safety behavior;
- profile/backend reactivity and auto-Project adoption hardening;
- SDK types, accessibility and translations.

The patch does not bundle the external plugin and does not move repositories or folders.

## Agent procedure

Give an agent this repository and the Hermes source checkout, then instruct it:

> Read `patches/hermes-0.20.5-project-groups/README.md`. Do not edit the patch files. Run `apply.py info`, confirm the Hermes base is supported and the checkout is clean, run `apply`, then `verify`. Stop on any failure. Do not force, skip tests, restart a shared Gateway, or install over the user's normal Desktop without explicit approval.

### 1. Prepare a source checkout

Use a fresh clone or disposable worktree. Do not apply this to an installation directory containing user state.

```bash
git clone https://github.com/NousResearch/hermes-agent.git hermes-agent-project-groups
cd hermes-agent-project-groups
git checkout 981101239a064c020a9d18fc3b1060ae306934ed
```

### 2. Inspect the bundle

```bash
python3 /path/to/hermes-plugin-project-groups/patches/hermes-0.20.5-project-groups/apply.py info .
```

### 3. Apply

```bash
python3 /path/to/hermes-plugin-project-groups/patches/hermes-0.20.5-project-groups/apply.py apply .
```

If `git am --3way` reports a conflict, stop. Do not resolve it automatically and claim compatibility; rebase the patch series for that Hermes version.

### 4. Install Desktop dependencies

```bash
cd apps/desktop
npm install
cd ../..
```

### 5. Verify

```bash
python3 /path/to/hermes-plugin-project-groups/patches/hermes-0.20.5-project-groups/apply.py verify .
```

Verification runs:

- renderer/Electron/E2E TypeScript typecheck;
- Project grouping resolver tests;
- native sidebar grouping tests;
- Project menu tests;
- create-group dialog tests;
- Project materialization/store tests;
- `git diff --check` against the pinned base.

### 6. Install the pinned plugin on the agent host

```bash
hermes plugins install https://github.com/cueplusplus/hermes-plugin-project-groups.git \
  --ref 40e068a4361889d4e46862c49d17ae177fc07d87 \
  --force --no-enable
hermes plugins enable project-groups
```

The plugin backend must run on the Hermes agent host that owns the Projects. A local Desktop connected to a remote Hermes agent needs the patched Desktop locally and the plugin enabled remotely.

Do not restart a shared Gateway while sessions are active. Schedule a safe restart window so the backend route mounts.

### 7. Build/run

Follow the Hermes Desktop build instructions for the target platform. For evaluation, prefer an isolated `HERMES_HOME` and Electron user-data directory rather than replacing the normal Desktop application.

## Rollback

Rollback is destructive to the current branch, so the script requires `--yes`. It first preserves the prior HEAD at `backup/project-groups-before-rollback`.

```bash
python3 patches/hermes-0.20.5-project-groups/apply.py rollback . --yes
```

Uninstall the plugin separately if desired:

```bash
hermes plugins disable project-groups
hermes plugins uninstall project-groups
```

## Updating to another Hermes version

Do not reuse this bundle silently against another release.

1. Create a new directory named for the target Hermes version.
2. Record the exact upstream base SHA.
3. Rebase the Project Groups commits onto that base.
4. Regenerate patches with `git format-patch`.
5. Update `base-commit.txt`, `patched-head.txt`, plugin pin and README.
6. Run `apply.py apply` and `verify` against a clean clone.
7. Run isolated Desktop UI verification.
8. Publish only after every check passes.

## Expected UI

```text
PROJECTS                         [+ project] [+ folder] [filters]

Home

▾ CUE++
    Analytics                         […]
    Knowledgebase                     […]

▾ RGC-LABS
    RGC ID                            […]

Ungrouped
    Another Project                   […]
```

Project Actions includes **Move to group** with every group plus **Ungrouped**.
