#!/usr/bin/env python3
"""Preflight, apply, verify, or roll back the pinned Project Groups patch."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

BUNDLE = Path(__file__).resolve().parent
PLUGIN_ROOT = BUNDLE.parents[1]
BASE = (BUNDLE / "base-commit.txt").read_text().strip()
SERIES = [line.strip() for line in (BUNDLE / "series").read_text().splitlines() if line.strip()]
PLUGIN_REPO = "https://github.com/cueplusplus/hermes-plugin-project-groups.git"
PLUGIN_REF = "0c58068035202f5defcf25270bee37ffd63d9a9b"


def marker() -> str:
    return f"Project-Groups-Base: {BASE}"


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"$ {' '.join(args)}")
    print(result.stdout, end="")
    if check and result.returncode:
        raise SystemExit(result.returncode)
    return result


def git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(("git", *args), cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(result.stdout.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def require_repo(repo: Path) -> None:
    if not (repo / ".git").exists():
        raise SystemExit(f"Not a Git checkout: {repo}")
    if not (repo / "apps" / "desktop" / "package.json").exists():
        raise SystemExit(f"Not a compatible Hermes source checkout: {repo}")


def clean(repo: Path) -> None:
    if git_output(repo, "status", "--porcelain"):
        raise SystemExit("Hermes checkout is not clean. Commit/stash changes before applying or rolling back.")


def base_exists(repo: Path) -> bool:
    return subprocess.run(
        ("git", "cat-file", "-e", f"{BASE}^{{commit}}"), cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    ).returncode == 0


def is_partial_clone(repo: Path) -> bool:
    extension = subprocess.run(
        ("git", "config", "--get", "extensions.partialClone"), cwd=repo,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if extension.returncode == 0 and extension.stdout.strip():
        return True
    promisors = subprocess.run(
        ("git", "config", "--get-regexp", r"^remote\..*\.promisor$"), cwd=repo,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return promisors.returncode == 0 and any(
        line.rsplit(maxsplit=1)[-1].lower() == "true" for line in promisors.stdout.splitlines() if line.strip()
    )


def ensure_base(repo: Path) -> None:
    if not base_exists(repo):
        run(repo, "git", "fetch", "origin", BASE)
    if not base_exists(repo):
        raise SystemExit(f"Supported base object is unavailable: {BASE}")


def require_base_ancestor(repo: Path) -> None:
    ensure_base(repo)
    if subprocess.run(
        ("git", "merge-base", "--is-ancestor", BASE, "HEAD"), cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode:
        raise SystemExit(f"HEAD does not descend from supported base {BASE}; refusing destructive action.")


def git_operation(repo: Path) -> str | None:
    git_dir = Path(git_output(repo, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    for name, label in (
        ("rebase-apply", "git am/rebase"),
        ("rebase-merge", "rebase"),
        ("MERGE_HEAD", "merge"),
        ("CHERRY_PICK_HEAD", "cherry-pick"),
        ("REVERT_HEAD", "revert"),
    ):
        if (git_dir / name).exists():
            return label
    return None


def patch_ids(repo: Path) -> set[str]:
    ids: set[str] = set()
    for name in SERIES:
        result = subprocess.run(
            ("git", "patch-id", "--stable"), cwd=repo, text=True,
            input=(BUNDLE / name).read_text(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if result.returncode or not result.stdout.strip():
            raise SystemExit(f"Unable to calculate stable patch-id for {name}: {result.stderr.strip()}")
        ids.add(result.stdout.split()[0])
    return ids


def applied_patch_ids(repo: Path) -> set[str]:
    if not base_exists(repo):
        return set()
    result = subprocess.run(
        ("git", "log", "--pretty=format:", "--patch", f"{BASE}..HEAD"),
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    if result.returncode or not result.stdout.strip():
        return set()
    calculated = subprocess.run(
        ("git", "patch-id", "--stable"), cwd=repo, text=True,
        input=result.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if calculated.returncode:
        raise SystemExit(calculated.stderr.strip())
    return {line.split()[0] for line in calculated.stdout.splitlines() if line.strip()}


def preflight(repo: Path) -> dict[str, Any]:
    """Perform a read-only compatibility check; never fetch or mutate."""
    require_repo(repo)
    head = git_output(repo, "rev-parse", "HEAD")
    dirty_result = subprocess.run(
        ("git", "--no-optional-locks", "status", "--porcelain"), cwd=repo,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if dirty_result.returncode:
        raise SystemExit(dirty_result.stdout.strip() or "read-only git status failed")
    dirty = bool(dirty_result.stdout.strip())
    shallow = git_output(repo, "rev-parse", "--is-shallow-repository") == "true"
    partial_clone = is_partial_clone(repo)
    missing = [name for name in SERIES if not (BUNDLE / name).is_file()]
    operation = git_operation(repo)
    history = "" if partial_clone else git_output(repo, "log", "--format=%B", "-200")
    existing_marker = False if partial_clone else marker() in history
    previous_patch_evidence = False if partial_clone or missing else bool(patch_ids(repo) & applied_patch_ids(repo))
    if partial_clone:
        classification = "incompatible"
        action = "Stop: partial clones are unsupported by read-only preflight; use a complete clone."
    elif shallow:
        classification = "incompatible"
        action = "Stop: checkout is shallow; obtain complete history and rerun preflight before creating a recovery bundle."
    elif dirty:
        classification = "incompatible"
        action = "Stop: checkout is dirty; preserve or replace it, then rerun dry preflight."
    elif operation:
        classification = "incompatible"
        action = f"Stop: {operation} is in progress; inspect and finish or abort it before reassessment."
    elif existing_marker or previous_patch_evidence:
        classification = "incompatible"
        action = "Stop: this bundle appears already applied or partially applied; inspect history and do not reapply it."
    elif missing:
        classification = "incompatible"
        action = "Stop: the pinned bundle is incomplete; obtain a complete reviewed bundle."
    elif not base_exists(repo):
        classification = "incompatible"
        action = f"Stop: exact supported base {BASE} is not present locally; inspect/fetch it before reassessment."
    elif head == BASE:
        classification = "exact-supported"
        action = "Apply this ordered series only after creating the backup manifest."
    elif subprocess.run(
        ("git", "merge-base", "--is-ancestor", BASE, "HEAD"), cwd=repo,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0:
        classification = "safely-adaptable"
        action = (
            "Do not apply this old series. Regenerate a new versioned bundle for this exact target base, "
            "then prove that new bundle in a clean clone before installation."
        )
    else:
        classification = "incompatible"
        action = "Stop: this checkout is unrelated to the supported base; do not apply or auto-resolve."
    return {
        "classification": classification,
        "ready_to_apply": classification == "exact-supported" and not dirty and not missing,
        "supported_base": BASE,
        "head": head,
        "clean": not dirty,
        "shallow": shallow,
        "partial_clone": partial_clone,
        "patch_count": len(SERIES),
        "missing_patches": missing,
        "git_operation": operation,
        "existing_marker": existing_marker,
        "previous_patch_evidence": previous_patch_evidence,
        "plugin_ref": PLUGIN_REF,
        "required_action": action,
    }


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True))


def default_backup_root(repo: Path) -> Path:
    return repo.parent / ".hermes-project-groups-backups"


def artifact_metadata(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def create_backup(repo: Path, backup_root: Path) -> Path:
    resolved_repo = repo.resolve()
    resolved_root = backup_root.expanduser().resolve()
    plugin_root = PLUGIN_ROOT.resolve()
    if (
        resolved_root == resolved_repo
        or resolved_repo in resolved_root.parents
        or resolved_root == plugin_root
        or plugin_root in resolved_root.parents
    ):
        raise SystemExit("Backup root must be outside the Hermes source checkout and compatibility/plugin checkout.")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = resolved_root / f"project-groups-{timestamp}"
    suffix = 1
    while destination.exists():
        destination = backup_root.expanduser().resolve() / f"project-groups-{timestamp}-{suffix}"
        suffix += 1
    destination.mkdir(parents=True, mode=0o700)
    destination.chmod(0o700)
    head = git_output(repo, "rev-parse", "HEAD")
    branch = git_output(repo, "branch", "--show-current") or "(detached)"
    source_bundle = destination / "hermes-source.bundle"
    run(repo, "git", "bundle", "create", str(source_bundle), "--all")
    source_bundle.chmod(0o600)
    patch_archive = destination / "project-groups-patch-bundle.tar.gz"
    with tarfile.open(patch_archive, "w:gz") as archive:
        archive.add(BUNDLE, arcname=BUNDLE.name)
    patch_archive.chmod(0o600)
    bundle_verify = run(repo, "git", "bundle", "verify", str(source_bundle), check=False)
    if bundle_verify.returncode:
        raise SystemExit("Source Git bundle readback verification failed; refusing mutation.")
    with tempfile.TemporaryDirectory(prefix="project-groups-bundle-restore-") as restore_dir:
        restored = Path(restore_dir) / "hermes-restored"
        clone = subprocess.run(
            ("git", "clone", str(source_bundle), str(restored)),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if clone.returncode or git_output(restored, "rev-parse", "HEAD") != head:
            raise SystemExit("Source Git bundle restore drill failed; refusing mutation.")
    try:
        with tarfile.open(patch_archive, "r:gz") as archive:
            archived = {member.name for member in archive.getmembers() if member.isfile()}
            expected = {f"{BUNDLE.name}/{name}" for name in SERIES}
            if not expected.issubset(archived):
                raise SystemExit("Patch archive readback is incomplete; refusing mutation.")
    except tarfile.TarError as exc:
        raise SystemExit(f"Patch archive readback verification failed: {exc}") from exc
    source_metadata = artifact_metadata(source_bundle)
    patch_metadata = artifact_metadata(patch_archive)
    manifest = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {"checkout": str(repo), "branch": branch, "head": head, "git_bundle": str(source_bundle), **source_metadata, "verified": True},
        "patch_bundle": {"directory": str(BUNDLE), "archive": str(patch_archive), "base": BASE, "series": SERIES, **patch_metadata, "verified": True},
        "verification": {"git_bundle_verified": True, "patch_archive_verified": True},
        "restore": {
            "source_checkout": (
                f"cd {shlex.quote(str(repo))} && "
                + (
                    f"git checkout {shlex.quote(branch)} && git reset --hard {shlex.quote(head)}"
                    if branch != "(detached)"
                    else f"git checkout --detach {shlex.quote(head)}"
                )
            ),
            "from_git_bundle": f"git clone {shlex.quote(str(source_bundle))} hermes-agent-restored",
            "patch_bundle": f"tar -xzf {shlex.quote(str(patch_archive))}",
        },
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    print(f"Backup manifest: {manifest_path}")
    print("Restore details:")
    for value in manifest["restore"].values():
        print(f"  {value}")
    return manifest_path


def python_test_command(repo: Path) -> list[str]:
    candidates = (
        repo / ".venv" / "bin" / "python",
        repo / "venv" / "bin" / "python",
        repo / ".venv" / "Scripts" / "python.exe",
        repo / "venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file() and subprocess.run(
            (str(candidate), "-c", "import pytest"), cwd=repo,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return [str(candidate), "-m", "pytest"]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--with", "pytest", "python", "-m", "pytest"]
    raise SystemExit("No checkout virtualenv or uv found for required Hermes Python tests.")


def apply(repo: Path, backup_root: Path | None = None) -> None:
    report = preflight(repo)
    print_report(report)
    if not report["ready_to_apply"]:
        raise SystemExit(f"Refusing apply: {report['required_action']}")
    if marker() in git_output(repo, "log", "--format=%B"):
        print("Patch series already appears applied.")
        return
    create_backup(repo, backup_root or default_backup_root(repo))
    fresh = preflight(repo)
    if not fresh["ready_to_apply"] or fresh["head"] != report["head"]:
        raise SystemExit(
            "Checkout changed while creating/verifying the backup. Refusing mutation; rerun preflight and backup."
        )
    patches = [str(BUNDLE / name) for name in SERIES]
    result = run(repo, "git", "am", "--3way", *patches, check=False)
    if result.returncode:
        abort = run(repo, "git", "am", "--abort", check=False)
        if abort.returncode:
            raise SystemExit(
                "Patch application failed and git am --abort also failed. Do not continue. "
                "Restore the pre-apply HEAD using the printed, verified backup manifest."
            )
        raise SystemExit(
            "Patch application stopped on conflict and the whole git-am session was aborted. "
            "Do not auto-resolve or continue; preserve the verified backup and report incompatibility."
        )
    recorded = run(
        repo, "git", "commit", "--allow-empty", "-m", f"chore: record Project Groups patch base\n\n{marker()}",
        check=False,
    )
    if recorded.returncode:
        restored = run(repo, "git", "reset", "--hard", report["head"], check=False)
        if restored.returncode:
            raise SystemExit(
                "Marker commit failed and automatic source restoration also failed. "
                "Use the verified backup manifest to restore the pre-apply HEAD."
            )
        raise SystemExit("Marker commit failed; all applied patches were rolled back to the pre-apply HEAD.")
    print("Applied exact pinned series. Run verify before building or installing.")


def verify(repo: Path) -> None:
    require_repo(repo)
    require_base_ancestor(repo)
    if marker() not in git_output(repo, "log", "--format=%B"):
        raise SystemExit("Patch marker is absent; refusing to verify an unknown source state.")
    desktop = repo / "apps" / "desktop"
    run(desktop, "npm", "run", "typecheck")
    run(
        desktop, "npm", "run", "test:ui", "--",
        "src/app/chat/sidebar/projects-presentation.test.ts",
        "src/app/chat/sidebar/sessions-section.test.tsx",
        "src/app/chat/sidebar/projects/project-menu.test.tsx",
        "src/app/chat/sidebar/project-group-dialog.test.tsx",
        "src/app/chat/sidebar/project-group-delete-dialog.test.tsx",
        "src/app/chat/sidebar/project-group-delete.test.ts",
        "src/store/projects.test.ts",
    )
    run(repo, *python_test_command(repo), "tests/hermes_cli/test_projects_db.py", "tests/tui_gateway/test_projects_rpc.py")
    run(repo, "git", "diff", "--check", BASE + "..HEAD")
    print("Verification passed.")
    print(f"Required plugin: {PLUGIN_REPO} @ {PLUGIN_REF}")


def rollback(repo: Path, yes: bool) -> str:
    require_repo(repo)
    clean(repo)
    require_base_ancestor(repo)
    if marker() not in git_output(repo, "log", "--format=%B"):
        raise SystemExit("Patch marker is absent; refusing to reset an unrelated branch.")
    if not yes:
        raise SystemExit("Rollback rewrites the current branch. Re-run with --yes after confirming the checkout is disposable.")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = f"backup/project-groups-before-rollback-{timestamp}"
    suffix = 1
    while subprocess.run(
        ("git", "show-ref", "--verify", "--quiet", f"refs/heads/{backup}"), cwd=repo,
    ).returncode == 0:
        backup = f"backup/project-groups-before-rollback-{timestamp}-{suffix}"
        suffix += 1
    run(repo, "git", "branch", backup, "HEAD")
    run(repo, "git", "reset", "--hard", BASE)
    print(f"Rolled back to {BASE}. Previous HEAD retained at {backup}.")
    print(f"Restore patched source: git -C {shlex.quote(str(repo))} reset --hard {shlex.quote(backup)}")
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "apply", "verify", "rollback", "info"])
    parser.add_argument("repo", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--backup-root", type=Path, help="directory for timestamped source/bundle backups")
    parser.add_argument("--yes", action="store_true", help="confirm destructive rollback")
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    if args.action == "preflight":
        print_report(preflight(repo))
    elif args.action == "apply":
        apply(repo, args.backup_root)
    elif args.action == "verify":
        verify(repo)
    elif args.action == "rollback":
        rollback(repo, args.yes)
    else:
        print(f"Supported base: {BASE}")
        print(f"Patch count: {len(SERIES)}")
        print(f"Plugin: {PLUGIN_REPO} @ {PLUGIN_REF}")
        print("Run `preflight` for the read-only compatibility classification.")


if __name__ == "__main__":
    main()
