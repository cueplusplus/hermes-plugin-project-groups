import importlib.util
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("project_groups_api", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

AGENT_MODULE_PATH = Path(__file__).resolve().parents[1] / "__init__.py"
agent_spec = importlib.util.spec_from_file_location("project_groups_agent", AGENT_MODULE_PATH)
assert agent_spec is not None and agent_spec.loader is not None
agent_module = importlib.util.module_from_spec(agent_spec)
agent_spec.loader.exec_module(agent_module)


class ProjectGroupsApiTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.previous = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.home.name

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.previous
        self.home.cleanup()

    def test_round_trip_is_profile_scoped_and_atomic(self):
        raw = {
            "groups": [{"id": "cue", "name": " CUE++ ", "collapsed": True}],
            "assignments": {"p1": "cue"},
            "projectOrder": {"cue": ["p1", "p1", "p2"]},
        }
        state = module.normalize_state(raw)
        module._atomic_write(module._state_path(), state)

        self.assertEqual(module._read_state(), {
            "version": 1,
            "groups": [{"id": "cue", "name": "CUE++", "collapsed": True}],
            "assignments": {"p1": "cue"},
            "projectOrder": {"cue": ["p1", "p2"]},
        })
        self.assertTrue((Path(self.home.name) / "project-groups" / "state.json").is_file())

    def test_dangling_assignments_are_removed(self):
        state = module.normalize_state({
            "groups": [{"id": "cue", "name": "CUE++"}],
            "assignments": {"good": "cue", "bad": "missing"},
        })
        self.assertEqual(state["assignments"], {"good": "cue"})

    def test_rejects_oversized_group_name(self):
        with self.assertRaisesRegex(ValueError, "group name"):
            module.normalize_state({"groups": [{"id": "cue", "name": "x" * 101}]})

    def test_group_names_use_utf16_limit(self):
        with self.assertRaisesRegex(ValueError, "group name"):
            module.normalize_state({"groups": [{"id": "emoji", "name": "😀" * 51}]})

    def test_authoritative_mutations_persist_and_return_current_state(self):
        created = asyncio.run(module.create_group(module.CreateGroupEnvelope(name="  Product   Design  ")))
        group_id = created["state"]["groups"][0]["id"]
        self.assertEqual(created["state"]["groups"][0]["name"], "Product Design")

        assigned = asyncio.run(module.assign_project(module.AssignProjectEnvelope(
            project_id="project-1",
            group_id=group_id,
        )))
        self.assertEqual(assigned["state"]["assignments"], {"project-1": group_id})

        collapsed = asyncio.run(module.set_group_collapsed(module.CollapseGroupEnvelope(
            group_id=group_id,
            collapsed=True,
        )))
        self.assertTrue(collapsed["state"]["groups"][0]["collapsed"])

        unassigned = asyncio.run(module.assign_project(module.AssignProjectEnvelope(
            project_id="project-1",
            group_id=None,
        )))
        self.assertEqual(unassigned["state"]["assignments"], {})
        self.assertEqual(module._read_state(), unassigned["state"])

    def test_capabilities_advertise_all_native_grouping_mutations(self):
        self.assertEqual(asyncio.run(module.get_capabilities()), {
            "mutations": ["createGroup", "assignProject", "setGroupCollapsed"],
            "version": 1,
        })

    def test_create_group_rejects_case_insensitive_duplicate(self):
        asyncio.run(module.create_group(module.CreateGroupEnvelope(name="CUE++")))

        with self.assertRaises(module.HTTPException) as raised:
            asyncio.run(module.create_group(module.CreateGroupEnvelope(name="  cue++ ")))

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual([group["name"] for group in module._read_state()["groups"]], ["CUE++"])

    def test_migration_is_one_time_and_preserves_legacy_state(self):
        legacy = {
            "groups": [{"id": "cue", "name": " CUE++ ", "collapsed": True}],
            "assignments": {"p1": "cue"},
            "projectOrder": {"cue": ["p1"]},
        }
        migrated = asyncio.run(module.migrate_state(module.StateEnvelope(state=legacy)))
        self.assertEqual(migrated["state"]["assignments"], {"p1": "cue"})

        existing = asyncio.run(module.migrate_state(module.StateEnvelope(state={
            "groups": [{"id": "other", "name": "Other"}],
        })))
        self.assertEqual(existing["state"], migrated["state"])

    def test_reads_and_repairs_v02_state_without_losing_groups_or_assignments(self):
        legacy = {
            "version": 1,
            "groups": [
                {"id": "long", "name": "L" * 101},
                {"id": "duplicate-1", "name": "Shared label"},
                {"id": "duplicate-2", "name": " shared   label "},
            ],
            "assignments": {
                "projectLong": "long",
                "projectOne": "duplicate-1",
                "projectTwo": "duplicate-2",
            },
            "projectOrder": {
                "long": ["projectLong"],
                "duplicate-1": ["projectOne"],
                "duplicate-2": ["projectTwo"],
                "__ungrouped__": ["projectTwo", "projectLong"],
            },
        }
        path = module._state_path()
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(legacy), encoding="utf-8")

        with mock.patch.object(module, "_atomic_write", wraps=module._atomic_write) as atomic_write:
            repaired = module._read_state()

            atomic_write.assert_called_once_with(path, repaired)
            self.assertEqual(agent_module._load_state(), repaired)
            self.assertEqual(module._read_state(), repaired)
            atomic_write.assert_called_once()

        self.assertEqual([(group["id"], group["name"]) for group in repaired["groups"]], [
            ("long", "L" * 100),
            ("duplicate-1", "Shared label"),
            ("duplicate-2", "shared label (2)"),
        ])
        self.assertEqual(repaired["assignments"], legacy["assignments"])
        self.assertEqual(repaired["projectOrder"], legacy["projectOrder"])

    def test_read_does_not_rewrite_unchanged_canonical_state(self):
        state = module.normalize_state({
            "groups": [{"id": "cue", "name": "CUE++"}],
            "assignments": {"p1": "cue"},
            "projectOrder": {"cue": ["p1"], "__ungrouped__": ["p2"]},
        })
        module._atomic_write(module._state_path(), state)

        with mock.patch.object(module, "_atomic_write", wraps=module._atomic_write) as atomic_write:
            self.assertEqual(module._read_state(), state)

        atomic_write.assert_not_called()

    def test_newer_schema_is_rejected_without_rewriting_state(self):
        path = module._state_path()
        path.parent.mkdir(parents=True)
        original = (
            b'{\n'
            b'  "version": 2,\n'
            b'  "groups": [{"id": "cue", "name": "CUE++", "futureGroupField": true}],\n'
            b'  "assignments": {"p1": "cue"},\n'
            b'  "projectOrder": {"cue": ["p1"]},\n'
            b'  "futureRootField": {"must": "survive"}\n'
            b'}\n'
        )
        calls = {
            "read": lambda: module.get_state(),
            "migration": lambda: module.migrate_state(module.StateEnvelope(state={
                "groups": [{"id": "other", "name": "Other"}],
            })),
            "create group": lambda: module.create_group(module.CreateGroupEnvelope(name="Other")),
            "assign project": lambda: module.assign_project(module.AssignProjectEnvelope(
                project_id="p2",
                group_id="cue",
            )),
            "collapse group": lambda: module.set_group_collapsed(module.CollapseGroupEnvelope(
                group_id="cue",
                collapsed=True,
            )),
        }

        for name, call in calls.items():
            with self.subTest(entrypoint=name):
                path.write_bytes(original)
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(call())
                self.assertEqual(raised.exception.status_code, 500)
                self.assertIn("newer schema version", raised.exception.detail)
                self.assertEqual(path.read_bytes(), original)

    def test_mutations_cannot_cross_persisted_collection_bounds(self):
        original_groups = module._MAX_GROUPS
        original_assignments = module._MAX_ASSIGNMENTS
        module._MAX_GROUPS = 1
        module._MAX_ASSIGNMENTS = 1
        try:
            state = module.normalize_state({
                "groups": [{"id": "cue", "name": "CUE++"}],
                "assignments": {"p1": "cue"},
            })
            module._atomic_write(module._state_path(), state)

            with self.assertRaises(module.HTTPException) as group_error:
                asyncio.run(module.create_group(module.CreateGroupEnvelope(name="Other")))
            self.assertEqual(group_error.exception.status_code, 422)

            with self.assertRaises(module.HTTPException) as assignment_error:
                asyncio.run(module.assign_project(module.AssignProjectEnvelope(
                    project_id="p2",
                    group_id="cue",
                )))
            self.assertEqual(assignment_error.exception.status_code, 422)
            self.assertEqual(module._read_state(), state)
        finally:
            module._MAX_GROUPS = original_groups
            module._MAX_ASSIGNMENTS = original_assignments


if __name__ == "__main__":
    unittest.main()
