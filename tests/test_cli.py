# SPDX-License-Identifier: BSD-3-Clause
"""Tests of the commands that read the data (history, diff)."""

import contextlib
import io
import json
import os
import unittest

from paramlineage import changes, cli, legal, query

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(["--data" if a == "@data" else a for a in argv])
    return code, out.getvalue(), err.getvalue()


class Diff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.histories = query.histories(DATA)

    def test_consecutive_releases_give_the_changes(self):
        for old, new in changes.pairs():
            with open(os.path.join(DATA, "changes", f"{old}..{new}.json"), encoding="utf-8") as f:
                expected = json.load(f)
            got = query.diff(self.histories, old, new)
            for key in ("added", "removed", "changed"):
                self.assertEqual(got[key], expected[key], f"{old}..{new} {key}")

    def test_successors_are_followed_to_the_newer_release(self):
        def h(name, states, removed=()):
            return {"states": [{"from": a, "to": b, "type": "Int32", "default": 0, "rebootRequired": False}
                                             for a, b in states], "removed": list(removed), "predecessors": []}
        histories = {
            "OLD": h("OLD", [("v1.12.0", "v1.14.4")], [{"in": "v1.15.0", "kind": "renamed", "successors": ["MID"]}]),
            "MID": h("MID", [("v1.15.0", "v1.16.2")], [{"in": "v1.17.0", "kind": "migrated", "successors": ["NEW"]}]),
            "NEW": h("NEW", [("v1.17.0", "v1.18.0-rc1")]),
        }
        d = query.diff(histories, "v1.14.4", "v1.18.0-rc1")
        self.assertEqual(d["removed"], {"OLD": {"kind": "renamed", "successors": ["NEW"]}})
        self.assertEqual(d["added"], ["NEW"])
        self.assertEqual(query.diff(histories, "v1.14.4", "v1.16.2")["removed"]["OLD"]["successors"], ["MID"])

    def test_states_are_found_by_release(self):
        self.assertEqual(query.state_at(self.histories["RC1_REV"], "v1.17.0")["type"], "Float")
        self.assertEqual(query.state_at(self.histories["RC1_REV"], "v1.18.0-rc1")["type"], "Int32")
        self.assertIsNone(query.state_at(self.histories["CANNODE_NODE_ID"], "v1.16.0"))


class Commands(unittest.TestCase):
    def test_history_text_ends_with_the_terms(self):
        code, out, _ = run("history", "MPC_HOLD_DZ", "@data", DATA)
        self.assertEqual(code, 0)
        self.assertIn("removed in v1.17.0 (renamed: MAN_DEADZONE)", out)
        self.assertTrue(out.rstrip().endswith(legal.PX4_DATA))
        for term in cli.TERMS:
            self.assertIn(term, out)

    def test_json_carries_the_terms(self):
        for argv in (("history", "MAN_DEADZONE"), ("diff", "v1.16.2", "v1.17.0")):
            code, out, _ = run(*argv, "--json", "@data", DATA)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["terms"], cli.TERMS)

    def test_diff_text(self):
        code, out, _ = run("diff", "v1.16.2", "v1.17.0", "@data", DATA)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("v1.16.2 to v1.17.0: 164 added, 59 removed, 50 changed\n"))
        self.assertIn("  ASPD_FALLBACK_GW (migrated: ASPD_FALLBACK)", out)

    def test_errors(self):
        for argv, message in ((("history", "NOPE"), "NOPE is not a parameter of any tracked release"),
                              (("diff", "v1.17.0", "v9.9.9"), "v9.9.9 is not a tracked release"),
                              (("diff", "v1.17.0", "v1.12.0"), "v1.17.0 is not older than v1.12.0")):
            code, out, err = run(*argv, "@data", DATA)
            self.assertEqual((code, out), (2, ""), argv)
            self.assertIn(message, err)
        code, _, err = run("history", "MAN_DEADZONE", "@data", os.path.join(ROOT, "tests"))
        self.assertEqual(code, 2)
        self.assertIn("no data found", err)

    def test_the_data_is_found_without_being_given(self):
        self.assertTrue(os.path.isfile(os.path.join(query.data_dir(), "params.json")))


if __name__ == "__main__":
    unittest.main()
