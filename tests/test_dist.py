# SPDX-License-Identifier: BSD-3-Clause
"""The built wheel and sdist, before a release: they hold exactly the committed files, the data the
commands read and the licenses, and nothing else."""

import email
import os
import subprocess
import tarfile
import tomllib
import unittest
import zipfile

from paramlineage import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.environ.get("PARAMLINEAGE_DIST")
NAME = f"param_lineage-{__version__}"
INFO = f"{NAME}.dist-info/"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def tracked():
    return sorted(git("ls-files", "-z").split("\0")[:-1])


def read(path):
    with open(os.path.join(ROOT, path), "rb") as f:
        return f.read()


def wheel_files():
    """What pyproject.toml puts in the wheel: the package, and the data forced into it."""
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        wheel = tomllib.load(f)["tool"]["hatch"]["build"]["targets"]["wheel"]
    places = {package: os.path.basename(package) for package in wheel["packages"]}
    places.update(wheel["force-include"])
    files = {}
    for path in tracked():
        for source, target in places.items():
            if path == source or path.startswith(source + "/"):
                files[target + path[len(source):]] = path
    return files


@unittest.skipUnless(DIST, "set PARAMLINEAGE_DIST to the directory with the built wheel and sdist")
class Distributions(unittest.TestCase):
    def setUp(self):
        self.wheel = zipfile.ZipFile(os.path.join(DIST, f"{NAME}-py3-none-any.whl"))
        self.addCleanup(self.wheel.close)
        self.sdist = tarfile.open(os.path.join(DIST, f"{NAME}.tar.gz"))
        self.addCleanup(self.sdist.close)

    def test_checkout_is_clean(self):
        # the other tests compare the distributions with the files of this checkout
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no"), "")

    def test_wheel_holds_the_package_the_data_and_the_licenses(self):
        files = wheel_files()
        self.assertIn("paramlineage/data/params.json", files)
        info = [INFO + name for name in ("METADATA", "WHEEL", "entry_points.txt", "RECORD")]
        licenses = {INFO + "licenses/" + name: name for name in ("LICENSE", "LICENSE-THIRD-PARTY")}
        self.assertEqual(sorted(self.wheel.namelist()), sorted([*files, *info, *licenses]))
        for name, path in {**files, **licenses}.items():
            self.assertEqual(self.wheel.read(name), read(path), name)

    def test_wheel_metadata(self):
        meta = email.message_from_bytes(self.wheel.read(INFO + "METADATA"))
        self.assertEqual(meta["Name"], "param-lineage")
        self.assertEqual(meta["Version"], __version__)
        self.assertEqual(meta["License-Expression"], "BSD-3-Clause")
        self.assertEqual(meta.get_all("License-File"), ["LICENSE", "LICENSE-THIRD-PARTY"])
        self.assertIsNone(meta.get_all("Requires-Dist"))
        # the README, with the terms, is the description
        self.assertEqual(meta.get_payload(), read("README.md").decode())
        entry_points = self.wheel.read(INFO + "entry_points.txt").decode()
        self.assertIn("param-lineage = paramlineage.cli:main", entry_points)

    def test_sdist_holds_the_committed_files(self):
        members = {m.name: m for m in self.sdist.getmembers() if m.isfile()}
        self.assertTrue(all(name.startswith(NAME + "/") for name in self.sdist.getnames()))
        self.assertEqual(sorted(members), sorted(f"{NAME}/{path}" for path in [*tracked(), "PKG-INFO"]))
        for path in tracked():
            self.assertEqual(self.sdist.extractfile(members[f"{NAME}/{path}"]).read(), read(path), path)

    def test_no_px4_in_file_names(self):
        for name in [*self.wheel.namelist(), *self.sdist.getnames()]:
            self.assertNotIn("px4", name.lower(), name)


if __name__ == "__main__":
    unittest.main()
