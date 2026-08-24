import importlib.util
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("project_groups_plugin", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

API_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
api_spec = importlib.util.spec_from_file_location("project_groups_api_for_agent_test", API_PATH)
assert api_spec is not None and api_spec.loader is not None
api = importlib.util.module_from_spec(api_spec)
api_spec.loader.exec_module(api)


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

    def test_agent_reload_reports_backend_mutations_consistently(self):
        created = asyncio.run(api.create_group(api.CreateGroupEnvelope(name="Product Design")))
        group_id = created["state"]["groups"][-1]["id"]
        backend = asyncio.run(api.assign_project(api.AssignProjectEnvelope(
            project_id="p_design",
            group_id=group_id,
        )))

        reload_spec = importlib.util.spec_from_file_location("project_groups_plugin_reloaded", MODULE_PATH)
        assert reload_spec is not None and reload_spec.loader is not None
        reloaded = importlib.util.module_from_spec(reload_spec)
        reload_spec.loader.exec_module(reloaded)
        reloaded._projects = lambda: [
            {"id": "p_cue", "name": "Quotamate", "primary_path": "/work/cue++/quotamate", "archived": False},
            {"id": "p_design", "name": "Design System", "primary_path": "/work/design", "archived": False},
        ]

        agent = reloaded.list_groups()
        expected_assignments = backend["state"]["assignments"]
        reported_assignments = {
            project["id"]: group["id"]
            for group in agent["groups"]
            for project in group["projects"]
        }
        self.assertEqual(reported_assignments, expected_assignments)

    def test_agent_reload_reports_deleted_group_projects_as_ungrouped(self):
        asyncio.run(api.delete_group(api.DeleteGroupEnvelope(
            group_id="cue",
            expected_project_ids=["p_cue"],
            operation_id="delete-cue-for-agent-reload",
        )))

        reload_spec = importlib.util.spec_from_file_location(
            "project_groups_plugin_after_delete", MODULE_PATH
        )
        assert reload_spec is not None and reload_spec.loader is not None
        reloaded = importlib.util.module_from_spec(reload_spec)
        reload_spec.loader.exec_module(reloaded)
        reloaded._projects = lambda: [
            {
                "id": "p_cue",
                "name": "Quotamate",
                "primary_path": "/work/cue++/quotamate",
                "archived": False,
            },
        ]

        agent = reloaded.list_groups()
        self.assertEqual(agent["groups"], [])
        self.assertEqual([project["id"] for project in agent["ungrouped"]], ["p_cue"])
        self.assertFalse(reloaded.get_group("cue")["success"])


if __name__ == "__main__":
    unittest.main()
