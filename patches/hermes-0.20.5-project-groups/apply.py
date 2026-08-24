#!/usr/bin/env python3
"""Apply, verify, or roll back the pinned Hermes Project Groups patch."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
BASE = (BUNDLE / "base-commit.txt").read_text().strip()
SERIES = [line.strip() for line in (BUNDLE / "series").read_text().splitlines() if line.strip()]
PLUGIN_REPO = "https://github.com/cueplusplus/hermes-plugin-project-groups.git"
PLUGIN_REF = "0c58068035202f5defcf25270bee37ffd63d9a9b"


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(f"$ {' '.join(args)}")
    print(result.stdout, end="")
    if check and result.returncode:
        raise SystemExit(result.returncode)
    return result


def require_repo(repo: Path) -> None:
    if not (repo / ".git").exists():
        raise SystemExit(f"Not a Git checkout: {repo}")
    if not (repo / "apps" / "desktop" / "package.json").exists():
        raise SystemExit(f"Not a compatible Hermes source checkout: {repo}")


def clean(repo: Path) -> None:
    if run(repo, "git", "status", "--porcelain").stdout.strip():
        raise SystemExit("Hermes checkout is not clean. Commit/stash changes before applying or rolling back.")


def ensure_base(repo: Path) -> None:
    if run(repo, "git", "cat-file", "-e", f"{BASE}^{{commit}}", check=False).returncode:
        run(repo, "git", "fetch", "origin", BASE)
    if run(repo, "git", "merge-base", "--is-ancestor", BASE, "HEAD", check=False).returncode:
        raise SystemExit(f"HEAD does not descend from supported base {BASE}. Refusing unsafe apply.")


def apply(repo: Path) -> None:
    require_repo(repo)
    clean(repo)
    ensure_base(repo)
    marker = f"Project-Groups-Base: {BASE}"
    if marker in run(repo, "git", "log", "--format=%B", "-80").stdout:
        print("Patch series already appears applied.")
        return
    for name in SERIES:
        patch = BUNDLE / name
        if not patch.exists():
            raise SystemExit(f"Missing patch: {patch}")
        run(repo, "git", "am", "--3way", str(patch))
    run(repo, "git", "commit", "--allow-empty", "-m", f"chore: record Project Groups patch base\n\n{marker}")
    print("Applied. Run verify before building or installing.")


def verify(repo: Path) -> None:
    require_repo(repo)
    ensure_base(repo)
    desktop = repo / "apps" / "desktop"
    run(desktop, "npm", "run", "typecheck")
    run(
        desktop,
        "npm",
        "run",
        "test:ui",
        "--",
        "src/app/chat/sidebar/projects-presentation.test.ts",
        "src/app/chat/sidebar/sessions-section.test.tsx",
        "src/app/chat/sidebar/projects/project-menu.test.tsx",
        "src/app/chat/sidebar/project-group-dialog.test.tsx",
        "src/store/projects.test.ts",
    )
    run(repo, "git", "diff", "--check", BASE + "..HEAD")
    print("Verification passed.")
    print(f"Required plugin: {PLUGIN_REPO} @ {PLUGIN_REF}")


def rollback(repo: Path, yes: bool) -> None:
    require_repo(repo)
    clean(repo)
    ensure_base(repo)
    if not yes:
        raise SystemExit("Rollback rewrites the current branch. Re-run with --yes after confirming the checkout is disposable.")
    backup = "backup/project-groups-before-rollback"
    run(repo, "git", "branch", "-f", backup, "HEAD")
    run(repo, "git", "reset", "--hard", BASE)
    print(f"Rolled back to {BASE}. Previous HEAD retained at {backup}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["apply", "verify", "rollback", "info"])
    parser.add_argument("repo", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--yes", action="store_true", help="confirm destructive rollback")
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    if args.action == "apply":
        apply(repo)
    elif args.action == "verify":
        verify(repo)
    elif args.action == "rollback":
        rollback(repo, args.yes)
    else:
        print(f"Supported base: {BASE}")
        print(f"Patch count: {len(SERIES)}")
        print(f"Plugin: {PLUGIN_REPO} @ {PLUGIN_REF}")


if __name__ == "__main__":
    main()
