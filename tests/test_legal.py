# SPDX-License-Identifier: BSD-3-Clause
"""The terms are part of the program: the license files, the README and --version must keep them."""

import contextlib
import io
import os
import re
import tomllib
import unittest

from paramlineage import __version__, cli, legal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class LicenseFiles(unittest.TestCase):
    def test_license_file_matches_the_program(self):
        self.assertEqual(read("LICENSE"), legal.LICENSE)

    def test_px4_license_file_matches_the_program(self):
        text = read("LICENSE-THIRD-PARTY")
        self.assertEqual(text, legal.LICENSE_PX4)
        self.assertTrue(text.startswith("BSD 3-Clause License"))
        self.assertIn("PX4 Development Team", text)
        self.assertIn("IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE", text)

    def test_license_command_prints_both_texts(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["license"]), 0)
        text = out.getvalue()
        self.assertIn(legal.LICENSE, text)
        self.assertIn(legal.LICENSE_PX4, text)
        self.assertIn(legal.TRADEMARK, text)

    def test_package_carries_both_licenses(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            project = tomllib.load(f)["project"]
        self.assertEqual(project["license"], "BSD-3-Clause")
        self.assertEqual(project["license-files"], ["LICENSE", "LICENSE-THIRD-PARTY"])


class Terms(unittest.TestCase):
    def test_readme_keeps_the_terms(self):
        # compare with line breaks folded, so wrapping the README does not matter
        readme = " ".join(read("README.md").split())
        for phrase in [
            "## Safety and liability",
            "without warranty of any kind",
            "accept no liability and no responsibility",
            "does not approve a vehicle as safe or airworthy",
            "Data that has not been checked is marked as such",
            "not affiliated with or endorsed by the PX4 project",
            "PX4 is a trademark of Dronecode Project, Inc.",
            "LICENSE-THIRD-PARTY",
        ]:
            self.assertIn(phrase, readme)

    def test_version_prints_the_terms(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            cli.main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        text = out.getvalue()
        self.assertTrue(text.startswith(f"param-lineage {__version__}\n"))
        for part in (legal.COPYRIGHT, legal.NO_WARRANTY, legal.INFORMATION_ONLY, legal.PX4_DATA, legal.TRADEMARK):
            self.assertIn(part, text)


class Names(unittest.TestCase):
    """PX4 is a trademark: sentences may refer to it, but nothing of this project is named with it."""

    def test_no_px4_in_names(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            project = tomllib.load(f)["project"]
        names = [project["name"], *project["scripts"], "paramlineage"]
        # the name the upgrade check page gives its checker in the browser
        names += re.findall(r"\broot\.(\w+) = api;", read("web/src/analyze.js"))
        self.assertGreater(len(names), 3)
        for name in names:
            self.assertNotIn("px4", name.lower(), name)

    def files(self):
        for top, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "dist", "node_modules", "__pycache__")]
            for name in files:
                yield os.path.relpath(os.path.join(top, name), ROOT)

    def test_no_px4_in_file_names(self):
        for path in self.files():
            self.assertNotIn("px4", path.lower(), path)

    def test_no_px4_in_headings_or_titles(self):
        heading = re.compile(r"^#{1,6} ")
        html_title = re.compile(r"<(title|h[1-6])\b[^>]*>(.*?)</\1>", re.I | re.S)
        for path in self.files():
            text = read(path) if path.endswith((".md", ".html")) else ""
            if path.endswith(".md"):
                fenced = False
                for line in text.splitlines():
                    if line.startswith("```"):
                        fenced = not fenced
                    elif not fenced and heading.match(line):
                        self.assertNotIn("PX4", line, f"{path}: {line}")
            for _, inner in html_title.findall(text):
                self.assertNotIn("PX4", inner, path)


if __name__ == "__main__":
    unittest.main()
