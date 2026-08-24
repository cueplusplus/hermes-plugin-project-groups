# Hermes 0.20.5 Native Project Groups compatibility bundle

This directory contains a deterministic, version-pinned 19-patch series for the native Project Groups extension seam while upstream draft PR [NousResearch/hermes-agent#93229](https://github.com/NousResearch/hermes-agent/pull/93229) is pending.

> [!CAUTION]
> **Do not install from this page.** Humans should point a Hermes Agent at the repository's canonical [`AGENT_INSTALL.md`](../../AGENT_INSTALL.md). That workflow discovers the live checkout/profile/sessions, creates full recoverable backups, classifies compatibility, applies only an exact-supported bundle, installs the immutable plugin, verifies every layer, and supplies rollback/readback.

## Exact pins

| Component | Pin |
|---|---|
| Hermes upstream base | `981101239a064c020a9d18fc3b1060ae306934ed` |
| Source line | Hermes Desktop 0.20.5-era checkout |
| Ordered series | 19 patches listed in `series` |
| Project Groups plugin | `0c58068035202f5defcf25270bee37ffd63d9a9b` (`v0.4.0`) |
| Plugin repository | <https://github.com/cueplusplus/hermes-plugin-project-groups> |

This is **not a floating patch**. Only a clean checkout whose `HEAD` exactly equals the pinned base is eligible to apply this series.

## What the bundle adds

- public `projects.grouping` Desktop plugin API;
- grouping in the existing native Projects sidebar;
- native create, move/unassign, collapse, and guarded delete controls;
- Home/Ungrouped safety behavior;
- profile/backend reactivity and Project adoption hardening;
- SDK types, accessibility, translations, and focused tests.

It does not bundle the external plugin, create a duplicate page, move repositories, change Project identity, or imply support for another Hermes revision.

## Tool contract

`apply.py` exposes:

- `info` — pins and patch count;
- `preflight` — **read-only** JSON compatibility classification;
- `apply` — exact-base-only application, preceded by a timestamped source Git bundle and patch archive, SHA-256/size manifest, readback verification, and printed source restore commands;
- `verify` — affected Desktop typecheck/tests plus `git diff --check`;
- `rollback` — explicit-confirmation reset with a unique timestamped backup branch and restore command.

The dry preflight classifications are:

- **exact-supported:** exact pinned `HEAD`, clean tree, complete series; direct application is allowed after the canonical backup review.
- **safely-adaptable:** a different descendant may be assessed only by generating a **new target-versioned bundle** and proving it in a clean clone. The old series is refused.
- **incompatible:** stop without mutation.

A `git am --3way` conflict always stops installation. It must never be auto-resolved or treated as compatibility evidence.

## Maintainer proof for a new Hermes version

Do not edit this bundle to float forward. Create a new versioned directory and:

1. record the exact new upstream base;
2. port and review the changes on a dedicated branch;
3. regenerate the entire ordered series with `git format-patch`;
4. update all pins, marker, tests, and documentation;
5. clone a fresh disposable Hermes checkout at that exact base;
6. run the new bundle's `apply` and `verify` actions;
7. run the complete Hermes Python/Desktop test and package build chain;
8. install the exact plugin SHA in an isolated profile and exercise the rendered native UI;
9. retain proof and obtain human review before publication or real installation.

Never apply this old series to the new target and resolve conflicts in place.

## Verification scope

The bundle's `verify` action runs renderer/Electron/E2E typecheck, grouping resolver tests, native sidebar tests, Project menu tests, create/delete-group dialog and delete-helper tests, Project materialization/store tests, `tests/hermes_cli/test_projects_db.py`, `tests/tui_gateway/test_projects_rpc.py`, and `git diff --check` from the pinned base. It safely prefers the checkout virtualenv and otherwise uses `uv run`. The canonical workflow additionally requires repository Python/plugin tests, a packaged Desktop build, isolated backend/tool/skill checks, and real UI interaction.

## Rollback model

`apply` records and verifies a source Git bundle and patch archive before mutation. It is intentionally **not** a full Hermes environment backup: it does not capture configuration, installed plugins, Project Groups state, the Projects DB, Desktop user data, or runtime state. Those are handled by the separate full-environment manifest required by [`AGENT_INSTALL.md`](../../AGENT_INSTALL.md). `rollback --yes` preserves the patched `HEAD` at a unique `backup/project-groups-before-rollback-<UTC timestamp>` branch before resetting.

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../../assets/cueplusplus-wordmark.svg">
    <img src="../../assets/cueplusplus-wordmark-dark.svg" alt="CUE++" width="104">
  </picture><br>
  <sub>Version-pinned compatibility engineering by CUE++</sub>
</p>
