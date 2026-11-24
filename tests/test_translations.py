# SPDX-License-Identifier: BSD-3-Clause
"""The translations: the data files, and the extractor run on a small fake release.

The extractor tests need a C++17 compiler ($CXX, or c++); they are skipped without one unless
PARAMLINEAGE_REQUIRE_CXX is set, as in CI. Set PARAMLINEAGE_REPO (a git repository of PX4) to also
run chosen probes on real releases and to extract every tracked release again.
"""

import functools
import hashlib
import json
import os
import re
import shutil
import tempfile
import textwrap
import unittest
from unittest import mock

from paramlineage import extract, translations
from tests.test_extract import BSD_HEADER, THIRD_PARTY, git, write

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS = os.path.join(ROOT, "data", "translations")
CXX = os.environ.get("CXX", "c++")


@functools.cache
def text(tag):
    with open(os.path.join(TRANSLATIONS, f"{tag}.json"), encoding="utf-8") as f:
        return f.read()


@functools.cache
def load(tag):
    return json.loads(text(tag))


@functools.cache
def snapshot(tag):
    with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
        return json.load(f)


def groups(tag, name, type_=None):
    return [g for g in load(tag)["parameters"][name] if type_ is None or g["stored"]["type"] == type_]


def group_of(tag, name, type_, value):
    found = [g for g in groups(tag, name, type_) if value in g["stored"]["values"]]
    assert len(found) == 1, (tag, name, value, found)
    return found[0]


def needs_cxx(test):
    found = shutil.which(CXX) is not None
    if not found and os.environ.get("PARAMLINEAGE_REQUIRE_CXX"):
        raise RuntimeError(f"no C++ compiler {CXX!r}")
    return unittest.skipUnless(found, f"no C++ compiler {CXX!r}")(test)


class Files(unittest.TestCase):
    def test_every_tracked_tag_has_a_file(self):
        files = {name[: -len(".json")] for name in os.listdir(TRANSLATIONS) if name.endswith(".json")}
        self.assertEqual(files, set(extract.TRACKED))

    def test_files_are_written_the_one_way(self):
        for tag in extract.TRACKED:
            self.assertEqual(translations.dumps(load(tag)), text(tag), tag)

    def test_source_and_extraction(self):
        for tag in extract.TRACKED:
            data = load(tag)
            self.assertEqual(data["format"], translations.FORMAT)
            self.assertEqual(data["source"], dict(snapshot(tag)["source"], file=translations.TRANSLATION), tag)
            extraction = data["extraction"]
            self.assertEqual(extraction["extractor"], translations.EXTRACTOR, f"{tag}: extract it again")
            self.assertEqual(extraction["flags"], translations.FLAGS)
            self.assertEqual(extraction["platforms"], sorted(translations.PLATFORMS))
            self.assertEqual(extraction["snapshots"], extract.TRACKED[: extract.TRACKED.index(tag) + 1])
            probes = extraction["probes"]
            self.assertEqual(probes["values"], probes["listed"] + probes["untouched_not_listed"], tag)
            self.assertEqual(data["notes"], translations.NOTES)

    def test_license(self):
        for tag in extract.TRACKED:
            license = load(tag)["license"]
            self.assertEqual(license["copyright"], snapshot(tag)["license"]["copyright"])
            self.assertEqual((license["license"], license["text"]), ("BSD-3-Clause", "LICENSE-THIRD-PARTY"))
            checked = license["checked"]
            self.assertEqual(checked["files"], checked["bsd_3_clause_notice"] + checked["no_notice"], tag)
            self.assertGreater(checked["bsd_3_clause_notice"], 0, tag)

    def test_import_model(self):
        for tag in extract.TRACKED:
            old = extract.TRACKED.index(tag) < extract.TRACKED.index("v1.15.0")
            self.assertEqual(load(tag)["extraction"]["import"], "return ignored" if old else "PARAM_SKIP_IMPORT skips", tag)


class Consistency(unittest.TestCase):
    """The rules of the data, checked with the standard library: every outcome follows from the
    import code and the release's snapshot, and every probe is listed once."""

    def test_outcomes_follow_the_import(self):
        for tag in extract.TRACKED:
            data, params = load(tag), snapshot(tag)["parameters"]
            skip = data["extraction"]["import"] == "PARAM_SKIP_IMPORT skips"
            for name, cases in data["parameters"].items():
                for c in cases:
                    where = f"{tag} {name} {c['stored']}"
                    node, result = c["node"], c["outcome"]
                    self.assertIsInstance(c["return"], str if skip else bool, where)
                    if skip and c["return"] == "PARAM_SKIP_IMPORT":
                        self.assertEqual(result["result"], "skipped", where)
                    elif node["name"] not in params:
                        self.assertEqual(result, dict({"result": "ignored-unknown-name", "name": node["name"]},
                                                      **({"also_set": result["also_set"]} if "also_set" in result else {})), where)
                    elif node["type"] != params[node["name"]]["type"]:
                        self.assertEqual(result["result"], "ignored-type", where)
                    else:
                        self.assertEqual((result["result"], result["name"]), ("stored", node["name"]), where)
                        if node["type"] == "Float" or isinstance(node["value"], str):
                            self.assertEqual(result["value"], node["value"], where)
                    for set_name in result.get("also_set", {}):
                        self.assertIn(set_name, params, where)

    def test_untouched_cases_are_left_alone(self):
        for tag in extract.TRACKED:
            data = load(tag)
            for name, cases in data["parameters"].items():
                self.assertTrue(any(c["touched"] or "depends_on" in c for c in cases), f"{tag} {name}")
                for c in cases:
                    if not c["touched"]:
                        self.assertEqual((c["node"]["name"], c["node"]["type"]), (name, c["stored"]["type"]))
                        self.assertEqual((c["matched"], c["calls"]), ([], []))
                        self.assertIn(c["return"], (False, "PARAM_NOT_MODIFIED"))

    def test_every_probe_is_listed_once(self):
        for tag in extract.TRACKED:
            for name, cases in load(tag)["parameters"].items():
                seen = {}
                for c in cases:
                    for value in c["stored"]["values"]:
                        seen.setdefault((c["stored"]["type"], value), []).append(c.get("platform"))
                for key, platforms in seen.items():
                    self.assertIn(sorted(platforms, key=str), ([None], ["nuttx", "posix"]), f"{tag} {name} {key}")

    def test_lines_are_calls_in_the_coverage(self):
        for tag in extract.TRACKED:
            data = load(tag)
            calls = {(c["call"], c["line"]) for c in data["coverage"]["calls"]}
            comparisons = {line for call, line in calls if call in translations.COMPARISONS}
            for name, cases in data["parameters"].items():
                for c in cases:
                    self.assertLessEqual(set(c["matched"]), comparisons, f"{tag} {name}")
                    for call in c["calls"]:
                        self.assertIn((call["call"], call["line"]), calls, f"{tag} {name}")
            reached = {(c["call"], c["line"]) for c in data["coverage"]["calls"] if c["reached"]}
            for name, cases in data["parameters"].items():
                for c in cases:
                    for line in c["matched"]:
                        self.assertTrue(any((k, line) in reached for k in translations.COMPARISONS), f"{tag} {name} {line}")


class Schema(unittest.TestCase):
    """Validation with the JSON Schema, using the pinned jsonschema of requirements/schema.txt."""

    def setUp(self):
        try:
            import jsonschema
        except ImportError:
            if os.environ.get("PARAMLINEAGE_REQUIRE_JSONSCHEMA"):
                raise
            self.skipTest("jsonschema is not installed (pip install -r requirements/schema.txt)")
        with open(os.path.join(ROOT, "schema", "translations.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.validator = jsonschema.Draft202012Validator(schema)

    def test_files_match_the_schema(self):
        for tag in extract.TRACKED:
            errors = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in self.validator.iter_errors(load(tag))]
            self.assertEqual(errors, [], tag)

    def test_schema_rejects_broken_files(self):
        def broken(change):
            data = json.loads(text("v1.18.0"))
            change(data)
            return list(self.validator.iter_errors(data))

        first = lambda d: d["parameters"]["COM_RC_OVERRIDE"][0]  # noqa: E731
        self.assertTrue(broken(lambda d: first(d)["outcome"].update({"result": "kept"})))
        self.assertTrue(broken(lambda d: first(d)["outcome"].pop("name")))
        self.assertTrue(broken(lambda d: first(d).update({"depends_on": ["luck"]})))
        self.assertTrue(broken(lambda d: first(d)["stored"].update({"values": []})))
        self.assertTrue(broken(lambda d: first(d)["node"].update({"value": "copied"})))
        self.assertTrue(broken(lambda d: d["coverage"]["calls"][0].update({"reached": ["windows"]})))
        self.assertTrue(broken(lambda d: d["source"].update({"file": "other.cpp"})))
        self.assertFalse(broken(lambda d: None))


class KnownHistory(unittest.TestCase):
    """Facts checked by hand against PX4's source (src/lib/parameters/param_translation.cpp)."""

    def test_gnss_offsets_move_to_the_sensor(self):
        # v1.18: EKF2_GPS_POS_X/Y/Z -> SENS_GPS0_OFFX/Y/Z, value kept
        for axis in "XYZ":
            (case,) = groups("v1.18.0", f"EKF2_GPS_POS_{axis}")
            self.assertEqual(case["outcome"], {"result": "stored", "name": f"SENS_GPS0_OFF{axis}", "value": "stored"})
            self.assertEqual(case["return"], "PARAM_MODIFIED")

    def test_rc_override_off_becomes_override_speed(self):
        # v1.18: only COM_RC_OVERRIDE = 0 is converted (to MAN_OVERRIDE_SPD = -1); other values are dropped
        self.assertEqual(group_of("v1.18.0", "COM_RC_OVERRIDE", "Int32", 0)["outcome"],
                         {"result": "stored", "name": "MAN_OVERRIDE_SPD", "value": -1})
        self.assertEqual(group_of("v1.18.0", "COM_RC_OVERRIDE", "Int32", 1)["outcome"],
                         {"result": "ignored-unknown-name", "name": "COM_RC_OVERRIDE"})

    def test_rc_reverse_becomes_an_integer(self):
        self.assertEqual(group_of("v1.18.0", "RC1_REV", "Float", -1.0)["outcome"],
                         {"result": "stored", "name": "RC1_REV", "value": -1})
        self.assertEqual(group_of("v1.18.0", "RC1_REV", "Float", 1.0)["outcome"],
                         {"result": "stored", "name": "RC1_REV", "value": 1})

    def test_motor_pole_count_goes_to_every_motor(self):
        (case,) = groups("v1.18.0", "MOT_POLE_COUNT")
        self.assertEqual(case["outcome"], {"result": "skipped",
                                           "also_set": {f"DSHOT_MOT_POL{i}": "stored" for i in range(1, 13)}})

    def test_heater_rule_is_not_reached(self):
        # HEATER*_IMU_ID only existed on main, after v1.17 had branched off and before v1.18, so no tracked parameter reaches it
        (heater,) = [n for n in load("v1.18.0")["coverage"]["names"] if n["name"] == "HEATER"]
        self.assertEqual((heater["prefix"], heater["tracked"], heater["reached"]), (True, False, False))

    def test_airspeed_circuit_breaker(self):
        # v1.15: CBRK_AIRSPD_CHK = 162128 -> SYS_HAS_NUM_ASPD = 0; other values keep the old name and are dropped
        self.assertEqual(group_of("v1.15.0", "CBRK_AIRSPD_CHK", "Int32", 162128)["outcome"],
                         {"result": "stored", "name": "SYS_HAS_NUM_ASPD", "value": 0})
        other = group_of("v1.15.0", "CBRK_AIRSPD_CHK", "Int32", 0)
        self.assertEqual((other["return"], other["outcome"]["result"]), ("PARAM_MODIFIED", "ignored-unknown-name"))

    def test_l1_rules_are_dead_code_in_v1_14_0(self):
        # v1.14.0 and v1.14.1 return before the L1 rules; v1.14.2 moved the return
        for tag in ("v1.14.0", "v1.14.1"):
            self.assertNotIn("FW_L1_PERIOD", load(tag)["parameters"])
            (entry,) = [n for n in load(tag)["coverage"]["names"] if n["name"] == "FW_L1_PERIOD"]
            self.assertFalse(entry["reached"])
        self.assertEqual(groups("v1.14.2", "FW_L1_PERIOD")[0]["outcome"],
                         {"result": "stored", "name": "NPFG_PERIOD", "value": "stored"})

    def test_pusher_slew_depends_on_the_parameter_handle(self):
        # v1.14: VT_PSHER_SLEW = param_find("VT_F_TRANS_THR") / VT_PSHER_RMP_DT, a handle, not a value
        case = group_of("v1.14.4", "VT_PSHER_RMP_DT", "Float", 3.0)
        self.assertEqual(case["depends_on"], ["parameter handles"])
        self.assertEqual(case["outcome"]["name"], "VT_PSHER_SLEW")

    def test_v1_13_renames_to_a_name_it_does_not_have(self):
        # v1.13: VT_DWN_PITCH_MAX -> VT_PITCH_MIN, which only v1.14 has
        for case in groups("v1.13.0", "VT_DWN_PITCH_MAX"):
            self.assertEqual(case["outcome"], {"result": "ignored-unknown-name", "name": "VT_PITCH_MIN"})

    def test_velocity_gains_scale_by_twenty(self):
        self.assertEqual(group_of("v1.12.0", "MPC_XY_VEL_P", "Float", 1.0)["outcome"],
                         {"result": "stored", "name": "MPC_XY_VEL_P_ACC", "value": 20})

    def test_device_id_rule_is_not_reached_by_the_probes(self):
        # v1.12: the device ID rule needs legacy device types; RealReleases runs it with such values
        unreached = [c for c in load("v1.12.0")["coverage"]["calls"] if not c["reached"]]
        self.assertEqual([c["call"] for c in unreached], ["log"])


class SourceParts(unittest.TestCase):
    CODE = textwrap.dedent('''\
        // "NOT_A_LITERAL" in a comment
        #include "param_translation.h"
        /* strcmp("COMMENTED", x)
           spans lines */
        int f(bson_node_t node) {
        	if (strncmp("PFX", node->name, 3) == 0 && strstr(node->name, "_X") != nullptr) {
        		PX4_INFO("migrating %s -> %s",
        			 "OLD_A", "NEW_A");
        	}
        	char c = 'x';
        	node->d = 0x10 + 2.5f * 1e3 + node->i32;
        	return strcmp("OLD_A", node->name);
        }
        ''')

    def test_literals_and_calls(self):
        source = translations.Source(self.CODE)
        self.assertEqual(source.names(), {"PFX": {"lines": {6}, "prefix": True},
                                          "OLD_A": {"lines": {8, 12}, "prefix": False},
                                          "NEW_A": {"lines": {8}, "prefix": False}})
        self.assertEqual([(c["call"], c["line"], c["last"]) for c in source.calls],
                         [("strncmp", 6, 6), ("strstr", 6, 6), ("log", 7, 8), ("strcmp", 12, 12)])
        self.assertEqual(source.site("log", 8), 7)
        with self.assertRaisesRegex(extract.ExtractError, "no call"):
            source.site("strcmp", 3)
        self.assertEqual(source.numbers(), {0, 16, -16, 2.5, -2.5, 1000.0, -1000.0, 3, -3})
        self.assertEqual(source.includes(), ['#include "param_translation.h"'])

    def test_short_floats(self):
        # PX4 stores 0.09 as a float32; v1.12 multiplies the stored double by 20
        self.assertEqual(translations.short(translations.float32(0.09) * 20), 1.8000001)
        self.assertEqual(translations.short(translations.float32(1.8)), 1.8)
        self.assertEqual(translations.short(0.1), 0.1)
        self.assertEqual(translations.short(-0.0), 0.0)

    def test_outcome(self):
        params = {"A": {"type": "Int32"}, "B": {"type": "Float"}}
        node = {"name": "A", "type": "Int32", "value": 2**32 - 1}
        self.assertEqual(translations.outcome(node, False, "return ignored", params, []),
                         {"result": "stored", "name": "A", "value": -1})
        self.assertEqual(translations.outcome(node, "PARAM_SKIP_IMPORT", "PARAM_SKIP_IMPORT skips", params, []),
                         {"result": "skipped"})
        self.assertEqual(translations.outcome(dict(node, type="Float"), True, "return ignored", params, []),
                         {"result": "ignored-type", "name": "A"})
        calls = [{"call": "param_set", "param": "B", "value": 1.5, "result": 0},
                 {"call": "param_set", "param": None, "result": -1}]
        self.assertEqual(translations.outcome(dict(node, name="C"), True, "return ignored", params, calls),
                         {"result": "ignored-unknown-name", "name": "C", "also_set": {"B": 1.5}})

    def test_compare(self):
        a = translations.dumps({"extraction": {"compiler": "clang 21"}, "parameters": {"A": []}})
        b = translations.dumps({"extraction": {"compiler": "g++ 13"}, "parameters": {"A": []}})
        c = translations.dumps({"extraction": {"compiler": "clang 21"}, "parameters": {"B": []}})
        self.assertEqual(translations.compare(a, a), "same")
        self.assertEqual(translations.compare(a, b), "same data")
        self.assertEqual(translations.compare(a, c), "different")


# A fake release: PX4's file layout, with a translation that has one rule of each kind.
FAKE_TRANSLATION = BSD_HEADER + textwrap.dedent('''\
    #include "param_translation.h"
    #include <px4_platform_common/log.h>
    #include <lib/parameters/param.h>
    #include <string.h>

    param_modify_on_import_ret param_modify_on_import(bson_node_t node)
    {
    	if (strcmp("OLD_NAME", node->name) == 0) {
    		strcpy(node->name, "NEW_NAME");
    		PX4_INFO("renamed");
    		return param_modify_on_import_ret::PARAM_MODIFIED;
    	}

    	if ((node->type == BSON_INT32) && (strcmp("MODE_OLD", node->name) == 0)) {
    		if (node->i32 == 7) {
    			int32_t on = 1;
    			param_set(param_find("FEATURE_EN"), &on);
    		}

    		return param_modify_on_import_ret::PARAM_SKIP_IMPORT;
    	}

    	if (strcmp("LOST_NAME", node->name) == 0) {
    		strcpy(node->name, "MISSING_NAME");
    	}

    	if (strcmp("HANDLE_OLD", node->name) == 0) {
    		node->d = param_find("FEATURE_EN");
    		strcpy(node->name, "HANDLE_NEW");
    		return param_modify_on_import_ret::PARAM_MODIFIED;
    	}

    	if (strcmp("BYTES_OLD", node->name) == 0) {
    		node->i32 = static_cast<int32_t>(node->d);
    		strcpy(node->name, "BYTES_NEW");
    		return param_modify_on_import_ret::PARAM_MODIFIED;
    	}

    #ifdef __PX4_NUTTX
    	if (strcmp("NUTTX_ONLY", node->name) == 0) {
    		node->i32 = 0;
    		return param_modify_on_import_ret::PARAM_MODIFIED;
    	}
    #endif

    	if ((strncmp("PFX", node->name, 3) == 0) && (strstr(node->name, "_NEVER") != nullptr)) {
    		PX4_INFO("never");
    	}

    	return param_modify_on_import_ret::PARAM_NOT_MODIFIED;
    }
    ''')
FAKE_FILES = {
    "src/lib/parameters/param_translation.h": BSD_HEADER + textwrap.dedent('''\
        #pragma once
        #include "tinybson/tinybson.h"
        enum class param_modify_on_import_ret { PARAM_SKIP_IMPORT = 0, PARAM_NOT_MODIFIED = 1, PARAM_MODIFIED = 2 };
        param_modify_on_import_ret param_modify_on_import(bson_node_t node);
        '''),
    "src/lib/tinybson/tinybson.h": BSD_HEADER + textwrap.dedent('''\
        #pragma once
        #include <stdint.h>
        typedef enum { BSON_EOO = 0, BSON_DOUBLE = 1, BSON_INT32 = 16, BSON_INT64 = 18 } bson_type_t;
        #define BSON_MAXNAME 32
        typedef struct bson_node_s {
        	char name[BSON_MAXNAME];
        	bson_type_t type;
        	int subtype;
        	union { double d; bool b; int32_t i32; int64_t i64; };
        } *bson_node_t;
        '''),
    "src/lib/parameters/param.h": textwrap.dedent('''\
        #pragma once
        #include <stdint.h>
        typedef uint16_t param_t;
        #define PARAM_INVALID ((uint16_t)0xffff)
        __EXPORT param_t param_find(const char *name);
        __EXPORT int param_set(param_t param, const void *val);
        '''),
    "src/lib/parameters/parameters.cpp": textwrap.dedent('''\
        static int
        param_import_callback(bson_decoder_t decoder, bson_node_t node)
        {
        	if (param_modify_on_import(node) == param_modify_on_import_ret::PARAM_SKIP_IMPORT) {
        		return 1;
        	}

        	return 1;
        }
        '''),
}
FAKE_IMPORT = textwrap.dedent('''\
    param_import_callback(bson_decoder_t decoder, bson_node_t node)
    {
    	if (param_modify_on_import(node) == param_modify_on_import_ret::PARAM_SKIP_IMPORT) {
    		return 1;
    	}

    	return 1;
    }''')
IMPORT_CODE = {hashlib.sha256(" ".join(FAKE_IMPORT.split()).encode()).hexdigest()[:16]: "PARAM_SKIP_IMPORT skips"}


def fake_snapshot(tag, commit, params):
    full = {name: {"type": type_, "default": default} for name, (type_, default) in params.items()}
    return tag, {"source": {"repository": extract.REPOSITORY, "tag": tag, "commit": commit}, "parameters": full}


@needs_cxx
class FakeRelease(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="paramlineage-test-")
        self.addCleanup(shutil.rmtree, self.repo)
        with open(THIRD_PARTY, encoding="utf-8") as f:
            write(self.repo, "LICENSE", f.read())
        write(self.repo, translations.TRANSLATION, FAKE_TRANSLATION)
        for path, content in FAKE_FILES.items():
            write(self.repo, path, content)

    def extract(self):
        if not os.path.isdir(os.path.join(self.repo, ".git")):
            git(self.repo, "init", "-q")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", "release")
            git(self.repo, "tag", "v9.1.0")
        commit = git(self.repo, "rev-parse", "HEAD")
        old = fake_snapshot("v9.0.0", "0" * 40, {
            "OLD_NAME": ("Float", 1.5), "MODE_OLD": ("Int32", 0), "LOST_NAME": ("Float", 0), "HANDLE_OLD": ("Float", 1),
            "BYTES_OLD": ("Int32", 0), "NUTTX_ONLY": ("Int32", 3), "KEEP": ("Int32", 3)})
        new = fake_snapshot("v9.1.0", commit, {
            "NEW_NAME": ("Float", 0), "FEATURE_EN": ("Int32", 0), "HANDLE_NEW": ("Float", 0), "BYTES_NEW": ("Int32", 0),
            "NUTTX_ONLY": ("Int32", 3), "KEEP": ("Int32", 3), "PFX_A": ("Int32", 0)})
        return translations.translations(self.repo, "v9.1.0", CXX, [old, new], IMPORT_CODE)

    def test_rules(self):
        data = self.extract()
        p = data["parameters"]
        self.assertEqual(sorted(p), ["BYTES_OLD", "HANDLE_OLD", "LOST_NAME", "MODE_OLD", "NUTTX_ONLY", "OLD_NAME"])
        (rename,) = p["OLD_NAME"]
        self.assertEqual(rename["outcome"], {"result": "stored", "name": "NEW_NAME", "value": "stored"})
        self.assertEqual((rename["return"], rename["matched"]), ("PARAM_MODIFIED", [len(BSD_HEADER.splitlines()) + 8]))
        # 0, 1, -1, the numbers of the code (7, 1, 0, 3) and their negatives, and the default
        self.assertEqual(rename["stored"]["values"], [-7.0, -3.0, -1.0, 0.0, 1.0, 1.5, 3.0, 7.0])
        mode = {tuple(c["stored"]["values"]): c["outcome"] for c in p["MODE_OLD"]}
        self.assertEqual(mode[(7,)], {"result": "skipped", "also_set": {"FEATURE_EN": 1}})
        self.assertEqual(mode[(-7, -3, -1, 0, 1, 3)], {"result": "skipped"})
        for case in p["LOST_NAME"]:
            self.assertEqual(case["outcome"], {"result": "ignored-unknown-name", "name": "MISSING_NAME"})
        self.assertTrue(all(c["depends_on"] == ["parameter handles"] for c in p["HANDLE_OLD"]))
        self.assertTrue(all(c["depends_on"] == ["node bytes"] for c in p["BYTES_OLD"]))
        by_platform = {c["platform"]: c for c in p["NUTTX_ONLY"] if 7 in c["stored"]["values"]}
        self.assertEqual(by_platform["nuttx"]["outcome"], {"result": "stored", "name": "NUTTX_ONLY", "value": 0})
        self.assertFalse(by_platform["posix"]["touched"])
        self.assertEqual(by_platform["posix"]["outcome"], {"result": "stored", "name": "NUTTX_ONLY", "value": "stored"})
        self.assertEqual(data["extraction"]["snapshots"], ["v9.0.0", "v9.1.0"])
        self.assertEqual(data["extraction"]["import"], "PARAM_SKIP_IMPORT skips")
        self.assertEqual(data["license"]["checked"], {"files": 4, "bsd_3_clause_notice": 3, "no_notice": 1})

    def test_coverage(self):
        data = self.extract()
        reached = {(c["call"], c["line"] - len(BSD_HEADER.splitlines())): c["reached"] for c in data["coverage"]["calls"]}
        self.assertEqual(reached[("strcmp", 40)], ["nuttx"])  # NUTTX_ONLY
        self.assertEqual(reached[("strncmp", 46)], ["nuttx", "posix"])  # PFX_A matches the prefix
        self.assertEqual(reached[("strstr", 46)], [])
        self.assertEqual(reached[("log", 47)], [])
        names = {n["name"]: n for n in data["coverage"]["names"]}
        self.assertEqual(names["PFX"], {"name": "PFX", "lines": [46 + len(BSD_HEADER.splitlines())], "tracked": False,
                                        "prefix": True, "reached": False})
        self.assertEqual((names["MISSING_NAME"]["tracked"], names["MISSING_NAME"]["reached"]), (False, True))
        self.assertEqual((names["FEATURE_EN"]["tracked"], names["FEATURE_EN"]["reached"]), (True, True))

    def test_same_bytes_twice(self):
        self.assertEqual(translations.dumps(self.extract()), translations.dumps(self.extract()))

    def test_unknown_import_code_fails(self):
        write(self.repo, "src/lib/parameters/parameters.cpp", FAKE_FILES["src/lib/parameters/parameters.cpp"].replace("return 1;\n}", "return 2;\n}"))
        with self.assertRaisesRegex(extract.ExtractError, "import code"):
            self.extract()

    def test_other_license_fails(self):
        write(self.repo, "src/lib/parameters/param.h", "/* Licensed under the Apache License */\n" + FAKE_FILES["src/lib/parameters/param.h"])
        with self.assertRaisesRegex(extract.ExtractError, "param.h"):
            self.extract()

    def test_compile_error_is_reported(self):
        write(self.repo, translations.TRANSLATION, FAKE_TRANSLATION.replace("PARAM_MODIFIED;", "PARAM_CHANGED;", 1))
        with self.assertRaisesRegex(extract.ExtractError, "does not compile"):
            self.extract()

    def test_main_needs_tracked_tags(self):
        with mock.patch("sys.stderr"):
            self.assertEqual(translations.main(["--repo", self.repo, "--cxx", CXX, "v9.1.0"]), 1)


@unittest.skipUnless(os.environ.get("PARAMLINEAGE_REPO"), "set PARAMLINEAGE_REPO to a git repository of PX4")
@needs_cxx
class RealReleases(unittest.TestCase):
    """Values the generic probes do not reach, run on the release's own code."""

    def setUp(self):
        self.repo = os.environ["PARAMLINEAGE_REPO"]

    def test_v1_12_device_ids(self):
        # SPI (bus type 2), bus 1, address 5, legacy MPU6000 accelerometer (0x13): becomes the MPU6000
        # IMU (0x21); on NuttX the SPI address is set to 0
        device_id = 2 | 1 << 3 | 5 << 8 | 0x13 << 16
        out = translations.run_probes(self.repo, "v1.12.0", CXX, snapshot("v1.12.0")["parameters"],
                                      [("CAL_ACC0_ID", "i", device_id)])
        self.assertEqual(out["nuttx"][0]["node"]["value"], 2 | 1 << 3 | 0 << 8 | 0x21 << 16)
        self.assertEqual(out["posix"][0]["node"]["value"], 2 | 1 << 3 | 5 << 8 | 0x21 << 16)
        self.assertIs(out["posix"][0]["return"], True)

    def test_v1_18_heater_sensor_ids(self):
        out = translations.run_probes(self.repo, "v1.18.0", CXX, snapshot("v1.18.0")["parameters"],
                                      [("HEATER1_IMU_ID", "i", 5), ("HEATER3_IMU_ID", "i", -1)])
        for platform in translations.PLATFORMS:
            self.assertEqual([r["node"] for r in out[platform]], [{"name": "HEATER1_SENS_ID", "type": "i", "value": 5},
                                                                  {"name": "HEATER3_SENS_ID", "type": "i", "value": -1}])

    def test_translations_are_reproducible(self):
        snapshots = os.path.join(ROOT, "data", "snapshots")
        for tag in extract.TRACKED:
            new = translations.dumps(translations.translations(self.repo, tag, CXX, translations.load_snapshots(snapshots, tag)))
            self.assertIn(translations.compare(text(tag), new), ("same", "same data"), tag)


if __name__ == "__main__":
    unittest.main()
