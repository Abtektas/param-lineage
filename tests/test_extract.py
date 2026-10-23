# SPDX-License-Identifier: BSD-3-Clause
"""The extractor, run on a small fake source tree whose generator scripts behave like PX4's.

Set PARAMLINEAGE_REPO (a git repository of PX4) and PARAMLINEAGE_PYTHON (a python with
requirements/extract.txt) to also extract every tracked release again and compare it with
data/snapshots. Set PARAMLINEAGE_FULL_TREE to a checkout of a tracked tag with all submodules
to compare a full tree with the snapshot made from git archive.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

from paramlineage import extract

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIRD_PARTY = os.path.join(ROOT, "LICENSE-THIRD-PARTY")
TOOLS = {"python": "test", "pyyaml": "test", "jinja2": "test"}

BSD_HEADER = "/* Redistribution and use in source and binary forms ... Neither the name of PX4 ... */\n"

# Fakes of PX4's three generators. A config lists parameter names as lines "  NAME:"; a source
# file as PARAM_DEFINE_INT32(NAME, 0). The last step fails on a name defined twice, as PX4's does.
# Until Tools/module_config existed (v1.13), the serial generator also wrote the parameters sections.
SERIAL = """
import argparse, json, os
p = argparse.ArgumentParser()
p.add_argument("--all-ports", action="store_true"); p.add_argument("--ethernet", action="store_true")
p.add_argument("--params-file"); p.add_argument("--config-files", nargs="*", default=[])
a = p.parse_args()
old = not os.path.exists("Tools/module_config/generate_params.py")
open(a.params_file, "w").write(json.dumps([c for c in a.config_files if old and "parameters:" in open(c).read()]))
"""
MODULE = """
import argparse, json
p = argparse.ArgumentParser()
p.add_argument("--timer-config"); p.add_argument("--board-with-io", action="store_true")
p.add_argument("--ethernet", action="store_true")
p.add_argument("--params-file"); p.add_argument("--config-files", nargs="*", default=[])
a = p.parse_args()
open(a.params_file, "w").write(json.dumps([c for c in a.config_files if "parameters:" in open(c).read()]))
"""
PROCESS = """
import argparse, json, os, re, sys
p = argparse.ArgumentParser()
p.add_argument("--src-path", nargs="*"); p.add_argument("--json")
INJECT
a = p.parse_args()
names = []
for d in a.src_path:
    for f in sorted(os.listdir(d)):
        if not f.endswith((".c", ".h")):
            continue
        text = open(os.path.join(d, f)).read()
        if f.endswith("_params.c") and text.startswith("["):
            for config in json.loads(text):
                names += re.findall(r"^  ([A-Z0-9_]+):", open(config).read(), re.M)
        else:
            names += re.findall(r"PARAM_DEFINE_INT32\\(([A-Z0-9_]+)", text)
if getattr(a, "inject_xml", None):
    names += re.findall(r'name="([^"]+)"', open(a.inject_xml).read())
if len(names) != len(set(names)):
    sys.exit("Duplicate parameter definition")
params = [{"name": n, "type": "Int32", "default": 0, "shortDesc": n, "group": "G", "category": "Standard"} for n in names]
json.dump({"version": 1, "translation": {}, "parameters": params}, open(a.json, "w"))
"""


def write(tree, path, content):
    full = os.path.join(tree, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                           "-c", "tag.gpgsign=false", *args], check=True, capture_output=True, env=env).stdout.decode().strip()


class FakeRelease(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="paramlineage-test-")
        self.addCleanup(shutil.rmtree, self.repo)
        with open(THIRD_PARTY, encoding="utf-8") as f:
            license_text = f.read().replace("2012 - 2025", "2012 - 2024")
        write(self.repo, "LICENSE", license_text)
        write(self.repo, "Tools/serial/generate_config.py", SERIAL)
        write(self.repo, "Tools/module_config/generate_params.py", MODULE)
        write(self.repo, "src/lib/parameters/px_process_params.py", PROCESS.replace("INJECT", ""))
        write(self.repo, "src/lib/parameters/px4params/__init__.py", "")
        write(self.repo, extract.TIMER_CONFIG, BSD_HEADER)
        write(self.repo, extract.OUTPUT_FUNCTIONS, "functions:\n")
        write(self.repo, "src/modules/commander/commander_params.c", BSD_HEADER + "PARAM_DEFINE_INT32(COM_A, 0);\n")
        write(self.repo, "src/modules/gps/module.yaml", "serial_config:\nparameters:\n  GPS_A:\n")
        write(self.repo, "src/modules/control_allocator/module.yaml", "parameters:\n  CA_AIRFRAME:\n")
        write(self.repo, "src/modules/spacecraft/module.yaml", "parameters:\n  CA_AIRFRAME:\n  CA_THRUSTER0_AX:\n")
        write(self.repo, "src/drivers/x/.github/workflows/ci.yaml", "# Licensed under the Apache License\nname: ci\n")
        self.patch_tools = mock.patch.object(extract.Generators, "tools", return_value=TOOLS)
        self.patch_tools.start()
        self.addCleanup(self.patch_tools.stop)

    def tag(self, tag="v9.9.9"):
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "release")
        git(self.repo, "tag", tag)
        return git(self.repo, "rev-parse", "HEAD")

    def snapshot(self, tag="v9.9.9"):
        return extract.snapshot(self.repo, tag, sys.executable)

    def test_snapshot_of_a_tag(self):
        commit = self.tag()
        data = self.snapshot()
        self.assertEqual(data["source"], {"repository": extract.REPOSITORY, "tag": "v9.9.9", "commit": commit})
        self.assertEqual(sorted(data["parameters"]), ["CA_AIRFRAME", "COM_A", "GPS_A"])
        self.assertEqual(data["parameters"]["COM_A"], {"type": "Int32", "default": 0, "shortDesc": "COM_A",
                                                       "group": "G", "category": "Standard"})
        self.assertEqual(data["license"]["copyright"], "Copyright (c) 2012 - 2024, PX4 Development Team")
        self.assertEqual(data["extraction"]["tools"], TOOLS)
        self.assertEqual(len(data["extraction"]["steps"]), 3)
        self.assertEqual(extract.dumps(data), extract.dumps(self.snapshot()))

    def test_excluded_configs_are_listed_with_what_only_they_define(self):
        self.tag()
        excluded = self.snapshot()["extraction"]["excluded_configs"]
        self.assertEqual(excluded, [{
            "config": "src/modules/spacecraft/module.yaml",
            "reason": extract.EXCLUDED[2][1],
            "parameters": 2,
            "not_in_snapshot": ["CA_THRUSTER0_AX"],
        }])

    def test_release_without_module_config(self):
        # v1.12: no Tools/module_config, so parameters sections come from the serial generator
        os.remove(os.path.join(self.repo, "Tools/module_config/generate_params.py"))
        self.tag()
        data = self.snapshot()
        self.assertEqual(len(data["extraction"]["steps"]), 2)
        self.assertEqual(sorted(data["parameters"]), ["CA_AIRFRAME", "COM_A", "GPS_A"])

    def test_injected_parameters_are_left_out(self):
        # before v1.17 the generator takes --inject-xml, and the release's file lists UAVCAN node parameters
        write(self.repo, "src/lib/parameters/px_process_params.py", PROCESS.replace("INJECT", 'p.add_argument("--inject-xml")'))
        write(self.repo, "src/lib/parameters/parameters_injected.xml", '<parameter name="ctl_bw"/>')
        self.tag()
        data = self.snapshot()
        self.assertNotIn("ctl_bw", data["parameters"])
        self.assertTrue(data["extraction"]["steps"][-1].endswith("--inject-xml <empty>"))

    def test_other_license_fails(self):
        write(self.repo, "src/modules/commander/gpl_params.c", "/* GNU General Public License */\nPARAM_DEFINE_INT32(COM_B, 0);\n")
        self.tag()
        with self.assertRaisesRegex(extract.ExtractError, "gpl_params.c"):
            self.snapshot()

    def test_changed_license_text_fails(self):
        with open(os.path.join(self.repo, "LICENSE"), encoding="utf-8") as f:
            text = f.read()
        write(self.repo, "LICENSE", text.replace("Neither the name", "The name"))
        self.tag()
        with self.assertRaisesRegex(extract.ExtractError, "LICENSE"):
            self.snapshot()

    def test_generator_failure_is_reported(self):
        write(self.repo, "src/modules/navigator/navigator_params.c", BSD_HEADER + "PARAM_DEFINE_INT32(COM_A, 1);\n")
        self.tag()
        with self.assertRaisesRegex(extract.ExtractError, "Duplicate parameter definition"):
            self.snapshot()

    def test_unknown_tag_fails(self):
        self.tag()
        with self.assertRaisesRegex(extract.ExtractError, "rev-parse"):
            self.snapshot("v0.0.0")

    def test_main_writes_and_checks(self):
        self.tag()
        out = os.path.join(self.repo, "out")
        with mock.patch("sys.stdout"):
            self.assertEqual(extract.main(["--repo", self.repo, "--python", sys.executable, "--out", out, "v9.9.9"]), 0)
            self.assertEqual(extract.main(["--repo", self.repo, "--python", sys.executable, "--out", out, "--check", "v9.9.9"]), 0)
            with open(os.path.join(out, "v9.9.9.json"), "a", encoding="utf-8") as f:
                f.write(" ")
            self.assertEqual(extract.main(["--repo", self.repo, "--python", sys.executable, "--out", out, "--check", "v9.9.9"]), 1)


class Parts(unittest.TestCase):
    def test_source_dirs_stop_at_depth_four(self):
        with tempfile.TemporaryDirectory() as tree:
            os.makedirs(os.path.join(tree, "src/a/b/c/d/e"))
            self.assertEqual(extract.source_dirs(tree), ["src", "src/a", "src/a/b", "src/a/b/c", "src/a/b/c/d"])

    def test_by_name(self):
        p = {"type": "Int32", "default": 0, "shortDesc": "", "group": "", "category": "Standard"}
        self.assertEqual(extract.by_name({"parameters": [dict(p, name="A")]}, "t"), {"A": p})
        with self.assertRaisesRegex(extract.ExtractError, "twice"):
            extract.by_name({"parameters": [dict(p, name="A"), dict(p, name="A")]}, "t")
        with self.assertRaisesRegex(extract.ExtractError, "does not know"):
            extract.by_name({"parameters": [dict(p, name="A", newField=1)]}, "t")

    def test_license_of(self):
        with tempfile.TemporaryDirectory() as tree:
            cases = {
                "bsd.c": (BSD_HEADER, "bsd-3-clause"),
                "spdx.py": ("# SPDX-License-Identifier: BSD-3-Clause\n", "bsd-3-clause"),
                "plain.yaml": ("module_name: x\n", "none"),
                "mit.c": ("/* Permission is hereby granted, free of charge (MIT License) */\n", "other"),
                "bsd2.c": ("/* Copyright (c) 2020 Someone. Redistribution and use in source and binary forms */\n", "other"),
            }
            for name, (content, kind) in cases.items():
                write(tree, name, content)
                self.assertEqual(extract.license_of(os.path.join(tree, name)), kind, name)

    def test_compare(self):
        a = extract.dumps({"extraction": {"tools": {"python": "3.14.9"}}, "parameters": {"A": {}}})
        b = extract.dumps({"extraction": {"tools": {"python": "3.14.10"}}, "parameters": {"A": {}}})
        c = extract.dumps({"extraction": {"tools": {"python": "3.14.9"}}, "parameters": {"B": {}}})
        self.assertEqual(extract.compare(a, a), "same")
        self.assertEqual(extract.compare(a, b), "same data")
        self.assertEqual(extract.compare(a, c), "different")

    def test_dumps_is_stable(self):
        self.assertEqual(extract.dumps({"b": 1, "a": "ü"}), '{\n "a": "ü",\n "b": 1\n}\n')


@unittest.skipUnless(os.environ.get("PARAMLINEAGE_REPO"), "set PARAMLINEAGE_REPO to a git repository of PX4")
class RealReleases(unittest.TestCase):
    def setUp(self):
        self.repo = os.environ["PARAMLINEAGE_REPO"]
        self.python = os.environ.get("PARAMLINEAGE_PYTHON", sys.executable)

    def test_snapshots_are_reproducible(self):
        for tag in extract.TRACKED:
            with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
                old = f.read()
            new = extract.dumps(extract.snapshot(self.repo, tag, self.python))
            self.assertIn(extract.compare(old, new), ("same", "same data"), tag)


@unittest.skipUnless(os.environ.get("PARAMLINEAGE_FULL_TREE"), "set PARAMLINEAGE_FULL_TREE to a checkout with submodules")
class FullTree(unittest.TestCase):
    def test_archive_gives_the_same_snapshot_as_a_full_checkout(self):
        tree = os.environ["PARAMLINEAGE_FULL_TREE"]
        tag = subprocess.run(["git", "-C", tree, "describe", "--tags", "--exact-match"], check=True,
                             capture_output=True, text=True).stdout.strip()
        commit = subprocess.run(["git", "-C", tree, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        python = os.environ.get("PARAMLINEAGE_PYTHON", sys.executable)
        source = {"repository": extract.REPOSITORY, "tag": tag, "commit": commit}
        with open(os.path.join(ROOT, "data", "snapshots", f"{tag}.json"), encoding="utf-8") as f:
            old = f.read()
        new = extract.dumps(extract.snapshot_of_tree(tree, python, source))
        self.assertIn(extract.compare(old, new), ("same", "same data"))


if __name__ == "__main__":
    unittest.main()
