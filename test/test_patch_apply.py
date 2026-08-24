import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "patches"
    / "hermes-0.20.5-project-groups"
    / "apply.py"
)
spec = importlib.util.spec_from_file_location("project_groups_patch_apply", MODULE_PATH)
assert spec is not None and spec.loader is not None
apply_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_module)


def git(repo, *args):
    return subprocess.run(
        ("git", *args), cwd=repo, text=True, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout.strip()


class PatchApplySafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "hermes"
        self.bundle = self.root / "bundle"
        self.repo.mkdir()
        self.bundle.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Patch Test")
        (self.repo / "apps" / "desktop").mkdir(parents=True)
        (self.repo / "apps" / "desktop" / "package.json").write_text("{}\n")
        (self.repo / "feature.txt").write_text("base\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "feature.txt").write_text("patched\n")
        git(self.repo, "commit", "-qam", "feature")
        patch = self.bundle / "0001-feature.patch"
        patch.write_text(git(self.repo, "format-patch", "-1", "--stdout") + "\n")
        git(self.repo, "reset", "--hard", self.base)

        self.old = (apply_module.BUNDLE, apply_module.PLUGIN_ROOT, apply_module.BASE, apply_module.SERIES)
        apply_module.BUNDLE = self.bundle
        apply_module.PLUGIN_ROOT = self.root / "plugin"
        apply_module.BASE = self.base
        apply_module.SERIES = [patch.name]

    def tearDown(self):
        apply_module.BUNDLE, apply_module.PLUGIN_ROOT, apply_module.BASE, apply_module.SERIES = self.old
        self.temp.cleanup()

    def test_preflight_exact_base_is_read_only_and_reports_supported(self):
        before = git(self.repo, "status", "--porcelain=v1")
        report = apply_module.preflight(self.repo)
        after = git(self.repo, "status", "--porcelain=v1")
        self.assertEqual(report["classification"], "exact-supported")
        self.assertTrue(report["ready_to_apply"])
        self.assertEqual(before, after)
        self.assertFalse((self.root / ".hermes-project-groups-backups").exists())

    def test_preflight_descendant_refuses_old_series_and_requires_new_bundle(self):
        (self.repo / "later.txt").write_text("later\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "later upstream")
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "safely-adaptable")
        self.assertFalse(report["ready_to_apply"])
        self.assertIn("new versioned bundle", report["required_action"])
        with self.assertRaises(SystemExit):
            apply_module.apply(self.repo, self.root / "backups")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), "later upstream")

    def test_preflight_classifies_dirty_exact_base_as_incompatible(self):
        (self.repo / "dirty.txt").write_text("dirty\n")
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "incompatible")
        self.assertFalse(report["ready_to_apply"])
        self.assertIn("dirty", report["required_action"])

    def test_preflight_rejects_shallow_checkout(self):
        original = apply_module.git_output
        apply_module.git_output = lambda repo, *args: (
            "true" if args == ("rev-parse", "--is-shallow-repository") else original(repo, *args)
        )
        try:
            report = apply_module.preflight(self.repo)
        finally:
            apply_module.git_output = original
        self.assertEqual(report["classification"], "incompatible")
        self.assertIn("shallow", report["required_action"])

    def test_preflight_rejects_partial_clone(self):
        git(self.repo, "config", "remote.upstream.promisor", "true")
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "incompatible")
        self.assertTrue(report["partial_clone"])
        self.assertIn("partial", report["required_action"])

    def test_preflight_refuses_in_progress_git_am_at_exact_base(self):
        git_dir = Path(git(self.repo, "rev-parse", "--git-dir"))
        if not git_dir.is_absolute():
            git_dir = self.repo / git_dir
        (git_dir / "rebase-apply").mkdir()
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "incompatible")
        self.assertFalse(report["ready_to_apply"])
        self.assertIn("in progress", report["required_action"])

    def test_preflight_recognizes_previously_applied_patch_commit(self):
        (self.repo / "feature.txt").write_text("patched\n")
        git(self.repo, "commit", "-qam", "feature")
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "incompatible")
        self.assertFalse(report["ready_to_apply"])
        self.assertTrue(report["previous_patch_evidence"])
        self.assertIn("already applied", report["required_action"])

    def test_preflight_recognizes_existing_marker(self):
        git(self.repo, "commit", "--allow-empty", "-qm", f"installed\n\nProject-Groups-Base: {self.base}")
        report = apply_module.preflight(self.repo)
        self.assertEqual(report["classification"], "incompatible")
        self.assertTrue(report["existing_marker"])

    def test_apply_creates_recoverable_bundle_and_manifest_before_mutation(self):
        backup_root = self.root / "backups"
        apply_module.apply(self.repo, backup_root)
        manifests = list(backup_root.glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text())
        self.assertEqual(manifests[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(manifests[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(manifest["source"]["head"], self.base)
        self.assertTrue(Path(manifest["source"]["git_bundle"]).is_file())
        self.assertTrue(Path(manifest["patch_bundle"]["archive"]).is_file())
        for section, key in (("source", "git_bundle"), ("patch_bundle", "archive")):
            artifact = Path(manifest[section][key])
            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest[section]["size_bytes"], artifact.stat().st_size)
            self.assertEqual(
                manifest[section]["sha256"],
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
            self.assertTrue(manifest[section]["verified"])
        self.assertTrue(manifest["verification"]["git_bundle_verified"])
        self.assertTrue(manifest["verification"]["patch_archive_verified"])
        self.assertIn("git reset --hard", manifest["restore"]["source_checkout"])
        self.assertIn("git clone", manifest["restore"]["from_git_bundle"])
        self.assertEqual((self.repo / "feature.txt").read_text(), "patched\n")

    def test_failed_multi_patch_apply_aborts_entire_series(self):
        bad = self.bundle / "0002-bad.patch"
        bad.write_text("not a patch\n")
        apply_module.SERIES = ["0001-feature.patch", bad.name]
        before = git(self.repo, "rev-parse", "HEAD")
        with self.assertRaises(SystemExit):
            apply_module.apply(self.repo, self.root / "backups")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual((self.repo / "feature.txt").read_text(), "base\n")

    def test_marker_commit_failure_restores_preapply_head(self):
        hook = self.repo / ".git" / "hooks" / "commit-msg"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        before = git(self.repo, "rev-parse", "HEAD")
        with self.assertRaisesRegex(SystemExit, "rolled back"):
            apply_module.apply(self.repo, self.root / "backups")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)

    def test_apply_revalidates_after_backup_before_mutation(self):
        original = apply_module.create_backup

        def mutate_after_backup(repo, backup_root):
            manifest = original(repo, backup_root)
            (repo / "raced.txt").write_text("race\n")
            return manifest

        apply_module.create_backup = mutate_after_backup
        before = git(self.repo, "rev-parse", "HEAD")
        try:
            with self.assertRaisesRegex(SystemExit, "changed"):
                apply_module.apply(self.repo, self.root / "backups")
        finally:
            apply_module.create_backup = original
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual((self.repo / "feature.txt").read_text(), "base\n")

    def test_restore_commands_quote_paths_with_spaces(self):
        spaced_root = self.root / "backup root"
        manifest_path = apply_module.create_backup(self.repo, spaced_root)
        manifest = json.loads(manifest_path.read_text())
        self.assertIn("'", manifest["restore"]["from_git_bundle"])
        self.assertIn("'", manifest["restore"]["patch_bundle"])

    def test_backup_root_inside_checkout_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "outside"):
            apply_module.create_backup(self.repo, self.repo / "backups")
        self.assertFalse((self.repo / "backups").exists())

    def test_backup_root_inside_plugin_bundle_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "plugin"):
            apply_module.create_backup(self.repo, apply_module.PLUGIN_ROOT / "backups")
        self.assertFalse((apply_module.PLUGIN_ROOT / "backups").exists())

    def test_rollback_refuses_divergent_or_unmarked_branch(self):
        git(self.repo, "checkout", "--orphan", "unrelated")
        for child in self.repo.iterdir():
            if child.name != ".git" and child.is_file():
                child.unlink()
        (self.repo / "apps" / "desktop").mkdir(parents=True, exist_ok=True)
        (self.repo / "apps" / "desktop" / "package.json").write_text("{}\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "unrelated")
        with self.assertRaisesRegex(SystemExit, "does not descend"):
            apply_module.rollback(self.repo, True)

    def test_rollback_uses_unique_backup_branch_and_prints_restore_details(self):
        apply_module.apply(self.repo, self.root / "backups")
        patched = git(self.repo, "rev-parse", "HEAD")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            branch = apply_module.rollback(self.repo, True)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.base)
        self.assertEqual(git(self.repo, "rev-parse", branch), patched)
        self.assertIn(branch, output.getvalue())
        self.assertIn("git reset --hard", output.getvalue())

    def test_python_test_command_prefers_checkout_virtualenv(self):
        python = self.repo / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n")
        python.chmod(0o755)
        command = apply_module.python_test_command(self.repo)
        self.assertEqual(command[0], str(python))
        self.assertEqual(command[1:3], ["-m", "pytest"])

    def test_python_test_command_supports_windows_virtualenv(self):
        python = self.repo / ".venv" / "Scripts" / "python.exe"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n")
        python.chmod(0o755)
        command = apply_module.python_test_command(self.repo)
        self.assertEqual(command[0], str(python))
        self.assertEqual(command[1:3], ["-m", "pytest"])

    def test_python_test_command_uv_installs_pytest_for_isolated_checkout(self):
        original = apply_module.shutil.which
        apply_module.shutil.which = lambda name: "/usr/bin/uv" if name == "uv" else None
        try:
            command = apply_module.python_test_command(self.repo)
        finally:
            apply_module.shutil.which = original
        self.assertEqual(command, ["/usr/bin/uv", "run", "--with", "pytest", "python", "-m", "pytest"])


if __name__ == "__main__":
    unittest.main()
