# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the parameter histories (data/params.json)."""

import json
import os
import unittest

from paramlineage import changes, extract, history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(ROOT, "data", "params.json")


def document() -> dict:
    with open(PARAMS, encoding="utf-8") as f:
        return json.load(f)


def load(name: str) -> dict:
    return document()["parameters"][name]


def built() -> dict:
    return history.build(os.path.join(ROOT, "data", "snapshots"), os.path.join(ROOT, "data", "curated"))


class Files(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = built()

    def test_the_file_is_up_to_date(self):
        with open(PARAMS, encoding="utf-8") as f:
            self.assertEqual(f.read(), extract.dumps(history.document(self.built)))

    def test_every_parameter_of_every_release_is_there(self):
        names = set()
        for tag in extract.TRACKED:
            with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
                names |= set(json.load(f)["parameters"])
        self.assertEqual(set(self.built), names)

    def test_states_agree_with_the_changes(self):
        tags = extract.TRACKED
        for old, new in changes.pairs():
            with open(os.path.join(ROOT, "data", "changes", f"{old}..{new}.json"), encoding="utf-8") as f:
                diff = json.load(f)
            for name, h in self.built.items():
                starts = {s["from"] for s in h["states"]}
                in_old = any(tags.index(s["from"]) <= tags.index(old) <= tags.index(s["to"]) for s in h["states"])
                in_new = any(tags.index(s["from"]) <= tags.index(new) <= tags.index(s["to"]) for s in h["states"])
                if in_old and in_new:
                    self.assertEqual(new in starts, name in diff["changed"], f"{name} {old}..{new}")
                self.assertEqual(in_new and not in_old, name in diff["added"], f"{name} {old}..{new}")
                removed = [r for r in h["removed"] if r["in"] == new]
                self.assertEqual(bool(removed), name in diff["removed"], f"{name} {old}..{new}")
                if removed:
                    self.assertEqual({k: v for k, v in removed[0].items() if k != "in"}, diff["removed"][name])

    def test_states_follow_each_other(self):
        tags = extract.TRACKED
        for name, h in self.built.items():
            last = -1
            for s in h["states"]:
                self.assertLess(last, tags.index(s["from"]), name)
                self.assertLessEqual(tags.index(s["from"]), tags.index(s["to"]), name)
                last = tags.index(s["to"])


class KnownHistory(unittest.TestCase):
    def test_a_rename_is_linked_both_ways(self):
        self.assertEqual(load("MPC_HOLD_DZ")["removed"], [{"in": "v1.17.0", "kind": "renamed", "successors": ["MAN_DEADZONE"]}])
        self.assertEqual(load("MAN_DEADZONE")["predecessors"], [{"name": "MPC_HOLD_DZ", "in": "v1.17.0", "kind": "renamed"}])

    def test_a_type_change_starts_a_state(self):
        states = load("RC1_REV")["states"]
        self.assertEqual([(s["from"], s["to"], s["type"]) for s in states],
                         [("v1.12.0", "v1.17.0", "Float"), ("v1.18.0-rc1", "v1.18.0-rc1", "Int32")])

    def test_a_parameter_that_comes_back_has_a_gap(self):
        h = load("CANNODE_NODE_ID")
        self.assertEqual([(s["from"], s["to"]) for s in h["states"]], [("v1.12.0", "v1.14.4"), ("v1.18.0-rc1", "v1.18.0-rc1")])
        self.assertEqual(h["removed"], [{"in": "v1.15.0"}])

    def test_float_defaults_are_compared_as_float32(self):
        old = {"parameters": {"A": {"type": "Float", "default": 0.1}}}
        new = {"parameters": {"A": {"type": "Float", "default": 0.100000001}}}
        h = history.histories([("v1.0.0", old), ("v1.0.1", new)], {})
        self.assertEqual([(s["from"], s["to"]) for s in h["A"]["states"]], [("v1.0.0", "v1.0.1")])


class Schema(unittest.TestCase):
    """Validation with the JSON Schema, using the pinned jsonschema of requirements/schema.txt."""

    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        with open(os.path.join(ROOT, "schema", "params.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_file_matches_the_schema(self):
        errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(document())]
        self.assertEqual(errors, [])

    def test_schema_rejects_broken_files(self):
        def broken(change):
            data = {"format": 1, "parameters": {"MAN_DEADZONE": load("MAN_DEADZONE")}}
            change(data["parameters"]["MAN_DEADZONE"])
            return list(self.validator.iter_errors(data))

        self.assertTrue(broken(lambda d: d.update({"states": []})))
        self.assertTrue(broken(lambda d: d["states"][0].pop("rebootRequired")))
        self.assertTrue(broken(lambda d: d["states"][0].update({"shortDesc": "x"})))
        self.assertTrue(broken(lambda d: d["predecessors"][0].update({"kind": "fixed"})))
        self.assertFalse(broken(lambda d: None))


if __name__ == "__main__":
    unittest.main()
