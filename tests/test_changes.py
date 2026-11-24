# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the changes between consecutive releases (data/changes)."""

import json
import os
import unittest

from paramlineage import changes, extract

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(old: str, new: str) -> dict:
    with open(os.path.join(ROOT, "data", "changes", f"{old}..{new}.json"), encoding="utf-8") as f:
        return json.load(f)


def names(tag: str) -> set:
    with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
        return set(json.load(f)["parameters"])


def param(**fields) -> dict:
    return {"type": "Float", "default": 0.0, "shortDesc": "x", "group": "g", "category": "Standard", **fields}


class Compare(unittest.TestCase):
    def test_floats_are_compared_as_float32(self):
        self.assertEqual(changes.compare(param(default=0.1), param(default=0.100000001)), {})
        self.assertEqual(changes.compare(param(default=0.1), param(default=0.2)), {"default": {"from": 0.1, "to": 0.2}})

    def test_ints_are_compared_exactly(self):
        self.assertEqual(changes.compare(param(type="Int32", default=16777216), param(type="Int32", default=16777217)),
                         {"default": {"from": 16777216, "to": 16777217}})

    def test_a_bound_that_appears_or_goes(self):
        self.assertEqual(changes.compare(param(), param(min=0.0)), {"min": {"from": None, "to": 0.0}})
        self.assertEqual(changes.compare(param(max=1.0), param()), {"max": {"from": 1.0, "to": None}})

    def test_reboot_required_left_out_is_false(self):
        self.assertEqual(changes.compare(param(), param(rebootRequired=False)), {})
        self.assertEqual(changes.compare(param(rebootRequired=True), param()), {"rebootRequired": {"from": True, "to": False}})

    def test_enum_values_and_bits(self):
        old = param(type="Int32", default=0, values=[{"value": 0, "description": "Off"}, {"value": 1, "description": "On"}])
        new = param(type="Int32", default=0, values=[{"value": 0, "description": "Disabled"}, {"value": 2, "description": "Auto"}])
        self.assertEqual(changes.compare(old, new), {"values": {
            "added": [{"key": 2, "description": "Auto"}],
            "removed": [{"key": 1, "description": "On"}],
            "changed": [{"key": 0, "from": "Off", "to": "Disabled"}],
        }})
        bits = param(type="Int32", default=0, bitmask=[{"index": 0, "description": "A"}])
        self.assertEqual(changes.compare(bits, param(type="Int32", default=0)), {"bitmask": {"removed": [{"key": 0, "description": "A"}]}})

    def test_descriptions_are_not_compared(self):
        self.assertEqual(changes.compare(param(shortDesc="a", longDesc="b"), param(shortDesc="c")), {})


class KnownHistory(unittest.TestCase):
    """Checked by hand against PX4's source."""

    def test_rc_reverse_becomes_int32(self):
        # v1.18.0 defines RC*_REV as int32 with values, but PX4's generator writes values only
        # for enum and float types, so its metadata has none.
        rev = load("v1.17.0", "v1.18.0")["changed"]["RC1_REV"]
        self.assertEqual(rev["type"], {"from": "Float", "to": "Int32"})
        self.assertEqual([v["key"] for v in rev["values"]["removed"]], [-1.0, 1.0])

    def test_fd_act_en_is_off_by_default(self):
        self.assertEqual(load("v1.17.0", "v1.18.0")["changed"]["FD_ACT_EN"]["default"], {"from": 1, "to": 0})

    def test_removed_parameters_carry_the_curated_kind(self):
        data = load("v1.17.0", "v1.18.0")
        self.assertEqual(data["curated"], "complete")
        self.assertEqual(data["removed"]["COM_RC_OVERRIDE"], {"kind": "migrated", "successors": ["MAN_OVERRIDE_SPD"]})
        self.assertIn("MAN_OVERRIDE_SPD", data["added"])
        self.assertEqual(load("v1.16.2", "v1.17.0")["removed"]["MPC_HOLD_DZ"], {"kind": "renamed", "successors": ["MAN_DEADZONE"]})
        self.assertEqual(load("v1.16.1", "v1.16.2")["curated"], "none")

    def test_patch_releases_change_little(self):
        data = load("v1.12.0", "v1.12.1")
        self.assertEqual((data["added"], data["removed"], data["changed"]), ([], {}, {}))


class Schema(unittest.TestCase):
    """Validation with the JSON Schema, using the pinned jsonschema of requirements/schema.txt."""

    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        with open(os.path.join(ROOT, "schema", "changes.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_files_match_the_schema(self):
        for old, new in changes.pairs():
            errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(load(old, new))]
            self.assertEqual(errors, [], f"{old}..{new}")

    def test_schema_rejects_broken_files(self):
        def broken(change):
            data = load("v1.17.0", "v1.18.0")
            change(data)
            return list(self.validator.iter_errors(data))

        self.assertTrue(broken(lambda d: d.update({"curated": "maybe"})))
        self.assertTrue(broken(lambda d: d["changed"]["FD_ACT_EN"].update({"longDesc": {"from": "a", "to": "b"}})))
        self.assertTrue(broken(lambda d: d["changed"]["FD_ACT_EN"]["default"].pop("to")))
        self.assertTrue(broken(lambda d: d["removed"]["COM_RC_OVERRIDE"].update({"kind": "gone"})))
        self.assertTrue(broken(lambda d: d["from"].update({"commit": "abc"})))
        self.assertFalse(broken(lambda d: None))


class Files(unittest.TestCase):
    def test_every_pair_has_a_file_and_it_is_up_to_date(self):
        for old, new in changes.pairs():
            built = extract.dumps(changes.build(os.path.join(ROOT, "data", "snapshots"), os.path.join(ROOT, "data", "curated"), old, new))
            with open(os.path.join(ROOT, "data", "changes", f"{old}..{new}.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), built, f"{old}..{new}")

    def test_added_and_removed_match_the_snapshots(self):
        for old, new in changes.pairs():
            a, b = names(old), names(new)
            data = load(old, new)
            self.assertEqual(set(data["added"]), b - a)
            self.assertEqual(set(data["removed"]), a - b)


if __name__ == "__main__":
    unittest.main()
