import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("project_groups_api", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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
            module.normalize_state({"groups": [{"id": "cue", "name": "x" * 201}]})


if __name__ == "__main__":
    unittest.main()
