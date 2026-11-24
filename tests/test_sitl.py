# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the SITL upgrade results (data/sitl), their schema, and the curated basis they back."""

import glob
import json
import os
import unittest

from paramlineage import curated, sitl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sitl", "parameters-v1.17.0.bson")


def files() -> list[str]:
    return sorted(glob.glob(os.path.join(DATA, "sitl", "*..*.json")))


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Storage(unittest.TestCase):
    def test_a_file_px4_wrote_reads_and_writes_back_the_same(self):
        # saved by v1.17.0 px4_sitl_default with the SIH quadrotor, nothing set by hand
        with open(FIXTURE, "rb") as f:
            data = f.read()
        elements = sitl.bson_decode(data)
        self.assertEqual(elements[0], ("CAL_ACC0_ID", 1310988))
        self.assertIn(("EKF2_MAG_DECL", 3.4056053), elements)
        self.assertEqual(sitl.bson_encode(elements), data)

    def test_order_and_types_are_kept(self):
        elements = [("SYS_AUTOSTART", 10040), ("EKF2_GPS_DELAY", 0.5), ("SENS_GPS0_DELAY", 77), ("MNT_MAX_PITCH", -0.1)]
        self.assertEqual(sitl.bson_decode(sitl.bson_encode(elements)), elements)

    def test_other_files_are_refused(self):
        with self.assertRaises(ValueError):
            sitl.bson_decode(b"\x05\x00\x00\x00")
        with self.assertRaises(ValueError):
            sitl.bson_decode(b"\x0d\x00\x00\x00\x02A\x00\x01\x00\x00\x00\x00\x00")


class Values(unittest.TestCase):
    def test_candidates_are_values_the_older_release_accepts(self):
        meta = {"type": "Int32", "default": 1, "min": 0, "max": 3}
        cases = [{"stored": {"type": "Int32", "values": [-20, -1, 0, 1, 2, 20]}},
                 {"stored": {"type": "Int32", "values": [3]}},
                 {"stored": {"type": "Float", "values": [2.0]}}]
        self.assertEqual(sitl.candidates(meta, cases), [[0, 1, 2], [3]])
        meta = {"type": "Float", "default": 1.0, "min": -1.0, "max": 1.0, "values": [{"value": -1}, {"value": 1}]}
        cases = [{"stored": {"type": "Float", "values": [-2.0, -1.0, -0.5]}}, {"stored": {"type": "Float", "values": [0.0, 0.5]}}]
        self.assertEqual(sitl.candidates(meta, cases), [[-1.0]])

    def test_expected_values_take_the_type_of_the_newer_release(self):
        params = {"SENS_GPS0_DELAY": {"type": "Int32"}, "SENS_GPS0_OFFX": {"type": "Float"}}
        case = {"outcome": {"result": "ignored-unknown-name", "name": "EKF2_GPS_DELAY", "also_set": {"SENS_GPS0_DELAY": 20}}}
        self.assertEqual(sitl.expected(case, 20.0, params), {"SENS_GPS0_DELAY": 20})
        case = {"outcome": {"result": "stored", "name": "SENS_GPS0_OFFX", "value": "stored"}}
        self.assertEqual(sitl.expected(case, -0.5, params), {"SENS_GPS0_OFFX": -0.5})

    def test_crafted_values_avoid_the_default_and_the_given_values(self):
        plan = object.__new__(sitl.Plan)
        plan.new_params = {"A": {"type": "Int32", "default": 0, "values": [{"value": 0}, {"value": 1}, {"value": 2}]},
                           "MODE": {"type": "Int32", "default": 0, "values": [{"value": 0}, {"value": 1}]},
                           "F": {"type": "Float", "default": 1.0, "min": 0.0, "max": 2.0}}
        self.assertEqual(plan.craft_value("A", [1]), 2)
        # an enum with no other value gets one near its default
        self.assertEqual(plan.craft_value("MODE", [1]), -1)
        self.assertEqual(plan.craft_value("F", [2.0]), 0.0)
        with self.assertRaises(SystemExit):
            plan.craft_value("F", [0.0, 2.0])

    def test_float_values_compare_as_float32(self):
        self.assertTrue(sitl.same(0.1, 0.10000000149011612))
        self.assertFalse(sitl.same(0.1, 0.1001))
        self.assertTrue(sitl.same(None, None))
        self.assertFalse(sitl.same(0, None))


class Schema(unittest.TestCase):
    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        schema = load(os.path.join(ROOT, "schema", "sitl.schema.json"))
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_files_match_the_schema(self):
        self.assertTrue(files())
        for path in files():
            errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(load(path))]
            self.assertEqual(errors, [], path)


class Results(unittest.TestCase):
    """The results follow from the runs and agree with the translations of the newer release."""

    def test_file_names_and_commits(self):
        for path in files():
            data = load(path)
            self.assertEqual(os.path.basename(path), f"{data['from']['tag']}..{data['to']['tag']}.json")
            for release in (data["from"], data["to"]):
                snapshot = load(os.path.join(DATA, "snapshots", f"{release['tag']}.json"))
                self.assertEqual(release["commit"], snapshot["source"]["commit"])

    def test_checks_follow_from_the_runs(self):
        for path in files():
            data = load(path)
            plan = sitl.Plan(DATA, data["from"]["tag"], data["to"]["tag"])
            self.assertEqual(data["unsteady"], sitl.unsteady(data["runs"]), path)
            self.assertEqual(data["checks"], sitl.checks(data, plan), path)
            self.assertEqual(data["unexpected"], sitl.unexpected(data, plan), path)

    def test_nothing_fails_and_nothing_else_changes(self):
        for path in files():
            data = load(path)
            self.assertEqual([c for c in data["checks"] if c["result"] == "fail"], [], path)
            self.assertEqual(data["unexpected"], {}, path)

    def test_old_names_set_by_name_are_refused(self):
        # what loading a parameter file does: the newer release has no such names, so nothing converts
        for path in files():
            data = load(path)
            runs = {r["name"]: r for r in data["runs"]}
            by_name = runs["by-name"]
            self.assertTrue(by_name["set_by_name"], path)
            self.assertEqual(set(by_name["set_by_name"].values()), {False}, path)
            self.assertEqual(by_name["after"], runs["control-1"]["after"], path)

    def test_every_converted_parameter_was_run(self):
        for path in files():
            data = load(path)
            plan = sitl.Plan(DATA, data["from"]["tag"], data["to"]["tag"])
            missing = {n for r in data["runs"] for n in r["not_in_build"]}
            self.assertEqual(set(plan.converted) - missing, {c["parameter"] for c in data["checks"]} & set(plan.converted), path)


class Basis(unittest.TestCase):
    """basis sitl-tested exactly for the migrated entries whose every successor passed in SITL."""

    def test_sitl_tested_where_the_runs_pass(self):
        results = {(d["from"]["tag"], d["to"]["tag"]): d for d in map(load, files())}
        for path in sorted(glob.glob(os.path.join(DATA, "curated", "*..*.json"))):
            facts = load(path)
            data = results.get((facts["from"], facts["to"]))
            for name, entry in facts["removed"].items():
                checks = [c for c in (data or {"checks": []})["checks"] if c["parameter"] == name]
                passed = {c["target"] for c in checks if c["result"] == "pass" and not c["run"].startswith("order-")}
                tested = (entry["kind"] == "migrated" and bool(checks) and not any(c["result"] == "fail" for c in checks)
                          and set(entry["successors"]) <= passed)
                self.assertEqual(entry["basis"] == "sitl-tested", tested, f"{facts['from']}..{facts['to']}: {name}")

    def test_curated_files_still_load(self):
        for path in sorted(glob.glob(os.path.join(DATA, "curated", "*..*.json"))):
            data = load(path)
            self.assertEqual(curated.load(os.path.join(DATA, "curated"), data["from"], data["to"]), data)


if __name__ == "__main__":
    unittest.main()
