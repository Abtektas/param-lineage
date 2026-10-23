# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the curated facts (data/curated) and their schema."""

import copy
import glob
import json
import os
import unittest

from paramlineage import curated, extract

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURATED = os.path.join(ROOT, "data", "curated")


def files() -> list[str]:
    return sorted(glob.glob(os.path.join(CURATED, "*..*.json")))


def snapshot(tag: str) -> dict:
    with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
        return json.load(f)

EXAMPLE = {
    "format": 1,
    "from": "v1.17.0",
    "to": "v1.18.0-rc1",
    "status": "partial",
    "removed": {
        "EKF2_GPS_POS_X": {"kind": "migrated", "commit": "a" * 40, "pr": 26634, "successors": ["SENS_GPS0_OFFX"],
                           "note": "Replaced by the per-receiver SENS_GPS0_OFFX.", "basis": "code-inspection"},
        "COM_KILL_DISARM": {"kind": "fixed", "commit": "b" * 40, "fixed_value": 5.0,
                            "note": "The vehicle disarms 5 s after the kill switch is engaged.", "basis": "code-inspection"},
        "GF_PREDICT": {"kind": "removed", "commit": "c" * 40, "note": "The feature was removed.", "basis": "code-inspection"},
    },
}


class Schema(unittest.TestCase):
    """Validation with the JSON Schema, using the pinned jsonschema of requirements/schema.txt."""

    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        with open(os.path.join(ROOT, "schema", "curated.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_example_matches_the_schema(self):
        self.assertEqual(list(self.validator.iter_errors(EXAMPLE)), [])

    def test_files_match_the_schema(self):
        for name in files():
            with open(name, encoding="utf-8") as f:
                errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(json.load(f))]
            self.assertEqual(errors, [], name)

    def test_schema_rejects_broken_entries(self):
        def broken(change):
            data = copy.deepcopy(EXAMPLE)
            change(data["removed"])
            return list(self.validator.iter_errors(data))

        self.assertTrue(broken(lambda r: r["GF_PREDICT"].update({"kind": "gone"})))
        self.assertTrue(broken(lambda r: r["GF_PREDICT"].update({"commit": "c" * 10})))
        self.assertTrue(broken(lambda r: r["GF_PREDICT"].pop("basis")))
        self.assertTrue(broken(lambda r: r["GF_PREDICT"].update({"note": ""})))
        self.assertTrue(broken(lambda r: r["GF_PREDICT"].update({"successors": ["GF_ACTION"]})))
        self.assertTrue(broken(lambda r: r["GF_PREDICT"].update({"fixed_value": 0})))
        self.assertTrue(broken(lambda r: r["EKF2_GPS_POS_X"].pop("successors")))
        self.assertTrue(broken(lambda r: r["EKF2_GPS_POS_X"].update({"successors": []})))
        self.assertTrue(broken(lambda r: r.update({"lower_case": r["GF_PREDICT"]})))
        self.assertFalse(broken(lambda r: r["COM_KILL_DISARM"].pop("fixed_value")))
        self.assertFalse(broken(lambda r: None))


class Files(unittest.TestCase):
    def test_there_is_a_file(self):
        self.assertIn(os.path.join(CURATED, "v1.17.0..v1.18.0-rc1.json"), files())

    def test_files_are_written_the_one_way(self):
        for name in files():
            with open(name, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text, extract.dumps(json.loads(text)), name)

    def test_files_agree_with_the_snapshots(self):
        for name in files():
            with open(name, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(os.path.basename(name), f"{data['from']}..{data['to']}.json")
            self.assertEqual(curated.problems(data, snapshot(data["from"]), snapshot(data["to"])), [], name)

    def test_problems_are_found(self):
        data = curated.load(CURATED, "v1.17.0", "v1.18.0-rc1")
        old, new = snapshot("v1.17.0"), snapshot("v1.18.0-rc1")

        def found(change):
            d = copy.deepcopy(data)
            change(d)
            return curated.problems(d, old, new)

        self.assertEqual(found(lambda d: d["removed"].pop("GF_PREDICT")), ["GF_PREDICT: removed in v1.18.0-rc1 but not listed"])
        self.assertEqual(found(lambda d: d["removed"]["MOT_POLE_COUNT"].update({"successors": ["DSHOT_MOT_POL13"]})),
                         ["MOT_POLE_COUNT: successor DSHOT_MOT_POL13 is not a parameter of v1.18.0-rc1"])
        self.assertEqual(found(lambda d: d["removed"].update({"MC_ROLL_P": d["removed"]["GF_PREDICT"]})),
                         ["MC_ROLL_P: still a parameter of v1.18.0-rc1"])
        self.assertEqual(found(lambda d: d["removed"].update({"NO_SUCH_PARAM": d["removed"]["GF_PREDICT"]})),
                         ["NO_SUCH_PARAM: not a parameter of v1.17.0"])
        self.assertEqual(found(lambda d: (d.update({"status": "partial"}), d["removed"].pop("GF_PREDICT"))), [])


class Translations(unittest.TestCase):
    """An entry is migrated exactly when the translation code of 'to' passes the value on."""

    def translations(self, tag: str) -> dict:
        with open(os.path.join(ROOT, "data", "translations", f"{tag}.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_files_agree_with_the_translations(self):
        for name in files():
            with open(name, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(curated.translation_problems(data, self.translations(data["to"])), [], name)

    def test_disagreements_are_found(self):
        data = curated.load(CURATED, "v1.17.0", "v1.18.0-rc1")
        translations = self.translations("v1.18.0-rc1")

        def found(change):
            d = copy.deepcopy(data)
            change(d["removed"])
            return curated.translation_problems(d, translations)

        self.assertEqual(found(lambda r: r["EKF2_GPS_POS_X"].update({"kind": "renamed"})),
                         ["EKF2_GPS_POS_X: renamed, but v1.18.0-rc1 converts it to SENS_GPS0_OFFX"])
        self.assertEqual(found(lambda r: r["SENS_TEMP_ID"].update({"kind": "migrated"})),
                         ["SENS_TEMP_ID: migrated, but v1.18.0-rc1 does not convert it"])
        self.assertEqual(found(lambda r: r["EKF2_GPS_DELAY"].update({"successors": ["SENS_GPS0_DELAY"]})),
                         ["EKF2_GPS_DELAY: converted to SENS_GPS1_DELAY, which are not its successors"])


@unittest.skipUnless(os.environ.get("PARAMLINEAGE_REPO"), "set PARAMLINEAGE_REPO to a git repository of PX4")
class RealCommits(unittest.TestCase):
    def test_commits_are_between_the_releases(self):
        repo = os.environ["PARAMLINEAGE_REPO"]
        for name in files():
            with open(name, encoding="utf-8") as f:
                self.assertEqual(curated.commit_problems(repo, json.load(f)), [], name)

    def test_a_commit_outside_the_range_is_found(self):
        repo = os.environ["PARAMLINEAGE_REPO"]
        data = curated.load(CURATED, "v1.17.0", "v1.18.0-rc1")
        outside = extract.git(repo, "rev-parse", "v1.17.0^{commit}").decode().strip()
        data["removed"]["GF_PREDICT"]["commit"] = outside
        self.assertEqual(curated.commit_problems(repo, data), [f"{outside}: not between v1.17.0 and v1.18.0-rc1"])



if __name__ == "__main__":
    unittest.main()
