import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("project_groups_plugin", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProjectGroupsToolsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.home.name
        self.root = Path(self.home.name)
        (self.root / "project-groups").mkdir()
        (self.root / "project-groups" / "state.json").write_text(json.dumps({
            "groups": [{"id": "cue", "name": "CUE++", "collapsed": False}],
            "assignments": {"p_cue": "cue"},
            "projectOrder": {"cue": ["p_cue"]},
        }))

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.previous
        self.home.cleanup()

    def test_list_groups_joins_backend_state_to_projects(self):
        original = getattr(module, "_projects")
        setattr(module, "_projects", lambda: [
            {"id": "p_cue", "name": "Quotamate", "primary_path": "/work/cue++/quotamate", "archived": False},
            {"id": "p_other", "name": "Other", "primary_path": "/work/other", "archived": False},
        ])
        try:
            result = module.list_groups()
        finally:
            setattr(module, "_projects", original)

        self.assertTrue(result["success"])
        self.assertEqual(result["groups"][0]["projects"][0]["name"], "Quotamate")
        self.assertEqual(result["ungrouped"][0]["id"], "p_other")

    def test_get_group_fails_honestly_for_missing_group(self):
        original = getattr(module, "_projects")
        setattr(module, "_projects", lambda: [])
        try:
            result = module.get_group("missing")
        finally:
            setattr(module, "_projects", original)
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])


if __name__ == "__main__":
    unittest.main()
