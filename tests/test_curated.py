# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the curated facts (data/curated) and their schema."""

import copy
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


if __name__ == "__main__":
    unittest.main()
