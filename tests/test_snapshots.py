# SPDX-License-Identifier: BSD-3-Clause
"""The snapshot files: one per tracked release, well-formed, and in agreement with PX4's own builds."""

import functools
import glob
import json
import os
import re
import struct
import unittest

from paramlineage import extract

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOTS = os.path.join(ROOT, "data", "snapshots")
FIRMWARE = os.path.join(ROOT, "tests", "fixtures", "firmware")
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


@functools.cache
def text(tag):
    with open(os.path.join(SNAPSHOTS, f"{tag}.json"), encoding="utf-8") as f:
        return f.read()


@functools.cache
def load(tag):
    return json.loads(text(tag))


def float32(x):
    return struct.unpack("f", struct.pack("f", float(x)))[0]


class Files(unittest.TestCase):
    def test_every_tracked_tag_has_a_snapshot(self):
        files = {os.path.basename(p)[: -len(".json")] for p in glob.glob(os.path.join(SNAPSHOTS, "*.json"))}
        self.assertEqual(files, set(extract.TRACKED))

    def test_files_are_written_the_one_way(self):
        for tag in extract.TRACKED:
            self.assertEqual(extract.dumps(load(tag)), text(tag), tag)

    def test_source(self):
        for tag in extract.TRACKED:
            source = load(tag)["source"]
            self.assertEqual(source["tag"], tag)
            self.assertEqual(source["repository"], extract.REPOSITORY)
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")

    def test_license(self):
        with open(os.path.join(ROOT, "LICENSE-THIRD-PARTY"), encoding="utf-8") as f:
            self.assertIn("BSD 3-Clause License", f.read())
        for tag in extract.TRACKED:
            license = load(tag)["license"]
            self.assertRegex(license["copyright"], r"^Copyright \(c\) 2012 - 20[0-9]{2}, PX4 Development Team$")
            self.assertEqual((license["license"], license["text"]), ("BSD-3-Clause", "LICENSE-THIRD-PARTY"))
            checked = license["checked"]
            self.assertEqual(checked["files"], checked["bsd_3_clause_notice"] + checked["no_notice"], tag)
            self.assertGreater(checked["bsd_3_clause_notice"], 0, tag)

    def test_extraction(self):
        for tag in extract.TRACKED:
            data = load(tag)
            self.assertEqual(data["format"], extract.FORMAT)
            self.assertEqual(data["extraction"]["extractor"], extract.EXTRACTOR, f"{tag}: extract it again")
            self.assertEqual(data["extraction"]["board"], extract.BOARD)
            for excluded in data["extraction"]["excluded_configs"]:
                self.assertTrue(any(p.search(excluded["config"]) for p, _ in extract.EXCLUDED), excluded["config"])

    def test_parameters(self):
        # The same rules as schema/snapshot.schema.json, with the standard library only.
        for tag in extract.TRACKED:
            for name, p in load(tag)["parameters"].items():
                where = f"{tag} {name}"
                self.assertRegex(name, NAME, where)
                self.assertLessEqual(len(name), 16, where)
                self.assertLessEqual(set(p), extract.FIELDS, where)
                self.assertLessEqual({"type", "default", "shortDesc", "group", "category"}, set(p), where)
                self.assertIn(p["type"], ("Int32", "Float"), where)
                self.assertIsInstance(p["default"], int if p["type"] == "Int32" else (int, float), where)
                self.assertNotIsInstance(p["default"], bool, where)


class Schema(unittest.TestCase):
    """Validation with the JSON Schema, using the pinned jsonschema of requirements/schema.txt."""

    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        with open(os.path.join(ROOT, "schema", "snapshot.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_snapshots_match_the_schema(self):
        for tag in extract.TRACKED:
            errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(load(tag))]
            self.assertEqual(errors, [], tag)

    def test_schema_rejects_broken_files(self):
        def broken(change):
            data = json.loads(text("v1.17.0"))
            change(data)
            return list(self.validator.iter_errors(data))

        self.assertTrue(broken(lambda d: d["parameters"].update({"lower_case": d["parameters"]["SYS_AUTOSTART"]})))
        self.assertTrue(broken(lambda d: d["parameters"]["SYS_AUTOSTART"].update({"default": 1.5})))
        self.assertTrue(broken(lambda d: d["parameters"]["SYS_AUTOSTART"].update({"unknownField": 1})))
        self.assertTrue(broken(lambda d: d["parameters"]["SYS_AUTOSTART"].pop("shortDesc")))
        self.assertTrue(broken(lambda d: d["source"].update({"commit": "d6f12ad"})))
        self.assertTrue(broken(lambda d: d["license"].pop("copyright")))
        self.assertFalse(broken(lambda d: None))


class KnownHistory(unittest.TestCase):
    """Facts checked by hand against PX4's source and release builds."""

    def names(self, tag):
        return load(tag)["parameters"].keys()

    def test_counts(self):
        counts = {"v1.12.0": 1738, "v1.13.0": 2169, "v1.14.0": 2280, "v1.15.0": 2478,
                  "v1.16.0": 2696, "v1.17.0": 2801, "v1.18.0": 3108}
        for tag, count in counts.items():
            self.assertEqual(len(self.names(tag)), count, tag)

    def test_no_uavcan_node_parameters(self):
        # parameters_injected.xml (until v1.16) describes UAVCAN nodes (ESCs, GNSS); PX4 does not store them
        for tag in ("v1.12.0", "v1.16.2"):
            for name in ("ctl_bw", "esc_index", "gnss.dyn_model"):
                self.assertNotIn(name, self.names(tag))

    def test_parameters_that_moved_to_yaml_stay(self):
        # v1.18 moved these from .c files to YAML files that PX4's metadata target does not read
        for name in ("TEST_1", "TEST_PARAMS", "SC_ROLL_P", "SC_YAW_P"):
            self.assertIn(name, self.names("v1.17.0"))
            self.assertIn(name, self.names("v1.18.0"))

    def test_hil_outputs_are_included(self):
        for tag in ("v1.13.0", "v1.17.0", "v1.18.0"):
            self.assertIn("HIL_ACT_FUNC1", self.names(tag))

    def test_control_allocation_comes_from_the_control_allocator(self):
        # v1.16's spacecraft build has its own copy of the CA_ parameters, with CA_AIRFRAME 14
        self.assertEqual(load("v1.16.0")["parameters"]["CA_AIRFRAME"]["default"], 0)
        spacecraft = [e for e in load("v1.16.0")["extraction"]["excluded_configs"]
                      if e["config"] == "src/modules/spacecraft/module.yaml"]
        self.assertEqual(len(spacecraft), 1)
        self.assertEqual(len(spacecraft[0]["not_in_snapshot"]), 85)
        self.assertTrue(all(n.startswith("CA_THRUSTER") for n in spacecraft[0]["not_in_snapshot"]))

    def test_simulator_outputs_beyond_eight(self):
        sim = [e for e in load("v1.17.0")["extraction"]["excluded_configs"] if e["config"].endswith("module_sim.yaml")]
        self.assertEqual(sim[0]["not_in_snapshot"], sorted(f"PWM_MAIN_FUNC{i}" for i in range(9, 17)))

    def test_removed_in_a_patch_release(self):
        self.assertIn("SYS_USE_IO", self.names("v1.14.0"))
        self.assertNotIn("SYS_USE_IO", self.names("v1.14.1"))


class Firmware(unittest.TestCase):
    """Every parameter of an official PX4 build is in the snapshot of its release, with the same type
    and default. The lists in tests/fixtures/firmware come from the release files named in each list."""

    # The serial port these use by default depends on the board's ports; the snapshot has the
    # default PX4's generator gives with every serial port present.
    BOARD_DEFAULTS = {"RC_PORT_CONFIG", "RC_SBUS_PRT_CFG"}

    def read(self, path):
        header, params = {}, []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("# ") and ": " in line:
                    key, value = line[2:].rstrip("\n").split(": ", 1)
                    header[key] = value
                elif not line.startswith("#"):
                    params.append(line.split())
        return header, params

    def test_lists_exist(self):
        self.assertGreaterEqual(len(glob.glob(os.path.join(FIRMWARE, "*.txt"))), 14)

    def test_builds_agree_with_snapshots(self):
        for path in sorted(glob.glob(os.path.join(FIRMWARE, "*.txt"))):
            tag = os.path.basename(path).rsplit("_", 1)[0]
            snapshot = load(tag)
            header, params = self.read(path)
            with self.subTest(list=os.path.basename(path)):
                if header["built from"] != "not recorded in the file":
                    self.assertEqual(header["built from"].split()[1], snapshot["source"]["commit"])
                self.assertGreater(len(params), 1000)
                missing, types, defaults = [], [], []
                for name, type_, default in params:
                    p = snapshot["parameters"].get(name)
                    if p is None:
                        missing.append(name)
                    elif type_.lower() != p["type"].lower():
                        types.append(name)
                    elif float32(default) != float32(p["default"]) and name not in self.BOARD_DEFAULTS:
                        defaults.append(name)
                # only names that are not PX4 parameters may be missing: the UAVCAN node ones
                self.assertEqual([n for n in missing if NAME.match(n)], [])
                self.assertEqual(types, [])
                self.assertEqual(defaults, [])


if __name__ == "__main__":
    unittest.main()
