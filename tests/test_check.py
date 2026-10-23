# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the check of a parameter file (param-lineage check)."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from paramlineage import check, cli, query

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
# Saved from v1.17.0 SITL (SIH quad) after setting EKF2_GPS_DELAY=150 EKF2_GPS_POS_X=0.12
# EKF2_GPS_POS_Y=-0.05 COM_RC_OVERRIDE=0 MPC_LAND_RC_HELP=1 MPC_XY_VEL_MAX=8 RC1_REV=-1 RC3_REV=-1
# COM_KILL_DISARM=3; also used by the upgrade check page's tests.
SITL = os.path.join(ROOT, "web", "test", "fixtures", "v1.17.0_sihsim_quadx_custom.params")


def sitl() -> str:
    with open(SITL, encoding="utf-8") as f:
        return f.read()


def kinds(report: dict) -> dict:
    out = {}
    for f in report["findings"]:
        out.setdefault(f["kind"], []).append(f["name"])
    return {k: sorted(v) for k, v in out.items()}


def run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Parse(unittest.TestCase):
    def test_formats(self):
        p = check.parse("# Vehicle: x\n# Version: 1.17.0 dev\n1\t1\tA\t1.5\t9\nB,2\n1 154 C 3 6\nbroken line here x y z\n\n")
        self.assertEqual(p["header"], {"Vehicle": "x", "Version": "1.17.0 dev"})
        self.assertEqual([(r["name"], r["component"], r["type"], r["value"]) for r in p["rows"]],
                         [("A", 1, "Float", 1.5), ("B", 1, None, 2.0), ("C", 154, "Int32", 3.0)])
        self.assertEqual(p["skipped"], [{"line": 6, "text": "broken line here x y z"}])

    def test_release_of_the_header(self):
        self.assertEqual(check.release_of({"Version": "1.17.0"}), "v1.17.0")
        self.assertEqual(check.release_of({"Version": "1.18.0-rc1 (abc)"}), "v1.18.0-rc1")
        self.assertIsNone(check.release_of({"Version": "1.11.3"}))
        self.assertIsNone(check.release_of({}))


class SitlFile(unittest.TestCase):
    """The same findings as the upgrade check page gives for this file, apart from the airframe's
    defaults (NAV_ACC_RAD), which the page reads from the startup scripts."""

    @classmethod
    def setUpClass(cls):
        cls.report = check.check(sitl(), DATA, "v1.17.0", "v1.18.0-rc1")
        cls.kinds = kinds(cls.report)

    def test_removed(self):
        self.assertEqual(len(self.kinds["removed"]), 32)
        migrated = sorted(f["name"] for f in self.report["findings"] if f["kind"] == "removed" and f["removal"].get("kind") == "migrated")
        self.assertEqual(migrated, ["COM_RC_OVERRIDE", "EKF2_GPS_DELAY", "EKF2_GPS_POS_X", "EKF2_GPS_POS_Y", "EKF2_GPS_POS_Z", "MPC_LAND_RC_HELP"])
        changed = sorted(f["name"] for f in self.report["findings"] if f["kind"] == "removed" and not f.get("at_old_default"))
        self.assertEqual(changed, ["COM_KILL_DISARM", "COM_RC_OVERRIDE", "EKF2_GPS_DELAY", "EKF2_GPS_POS_X", "EKF2_GPS_POS_Y", "MPC_LAND_RC_HELP"])

    def test_other_findings(self):
        self.assertEqual(self.kinds["type-changed"], sorted(f"RC{i}_REV" for i in range(1, 19)))
        self.assertEqual(self.kinds["reverts-default"], ["FD_ACT_EN", "MPC_LAND_RADIUS", "SENS_MAG_AUTOCAL"])
        self.assertEqual(self.kinds["instance"], sorted(f"PWM_MAIN_FUNC{i}" for i in range(9, 17)))
        self.assertEqual(self.kinds["internal"], ["_HASH_CHECK"])
        self.assertEqual(set(self.kinds), {"removed", "type-changed", "reverts-default", "instance", "internal"})

    def test_the_release_loaded_on_must_be_newer(self):
        with self.assertRaisesRegex(query.DataError, "v1.17.0 is not older than v1.17.0"):
            check.check(sitl(), DATA, "v1.17.0", "v1.17.0")


class Rules(unittest.TestCase):
    def test_only_a_range_the_new_release_narrowed(self):
        h = query.histories(DATA)
        name = next(n for n, x in h.items() if (s := query.state_at(x, "v1.18.0-rc1")) and s["type"] == "Float"
                    and "max" in s and query.state_at(x, "v1.17.0") == s)
        too_big = query.state_at(h[name], "v1.18.0-rc1")["max"] + 1
        report = check.check(f"1\t1\t{name}\t{too_big}\t9\n", DATA, "v1.17.0", "v1.18.0-rc1")
        self.assertEqual(report["findings"], [], "already outside the old range")

    def test_other_components_are_not_checked(self):
        report = check.check("1\t154\tCOM_KILL_DISARM\t3\t9\n", DATA, "v1.17.0", "v1.18.0-rc1")
        self.assertEqual((report["findings"], report["counts"]["autopilot"]), ([], 0))


class Command(unittest.TestCase):
    def test_text_ends_with_the_limits_and_the_terms(self):
        code, out, _ = run("check", SITL, "--from", "v1.17.0", "--to", "v1.18.0-rc1", "--data", DATA)
        self.assertEqual(code, 0)
        self.assertIn("  COM_RC_OVERRIDE = 0 (migrated: MAN_OVERRIDE_SPD)\n      " + cli.MIGRATED, out)
        for text in check.LIMITS + cli.TERMS:
            self.assertIn(text, out)

    def test_json(self):
        code, out, _ = run("check", SITL, "--from", "v1.17.0", "--to", "v1.18.0-rc1", "--data", DATA, "--json")
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual((d["terms"], d["limits"]), (cli.TERMS, check.LIMITS))

    def test_release_from_the_file_or_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            named = os.path.join(tmp, "named.params")
            with open(named, "w", encoding="utf-8") as f:
                f.write("# Version: 1.17.0\n1\t1\tCOM_RC_OVERRIDE\t0\t6\n")
            code, out, _ = run("check", named, "--to", "v1.18.0-rc1", "--data", DATA)
            self.assertEqual(code, 0)
            self.assertIn("saved on v1.17.0 against v1.18.0-rc1", out)
            code, _, err = run("check", SITL, "--to", "v1.18.0-rc1", "--data", DATA)
            self.assertEqual(code, 2)
            self.assertIn("give --from", err)
            code, _, err = run("check", os.path.join(tmp, "missing.params"), "--from", "v1.17.0", "--to", "v1.18.0-rc1", "--data", DATA)
            self.assertEqual(code, 2)
            self.assertIn("cannot read", err)

    def test_a_file_that_names_another_release_is_flagged(self):
        report = check.check("# Version: 1.16.2\n", DATA, "v1.17.0", "v1.18.0-rc1")
        self.assertIn("The file says it was saved on v1.16.2, not v1.17.0.", cli.check_text(report))
        self.assertIn("Nothing found.", cli.check_text(report))


if __name__ == "__main__":
    unittest.main()
