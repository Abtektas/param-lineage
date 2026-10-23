# SPDX-License-Identifier: BSD-3-Clause
"""Snapshots: all parameter metadata of one PX4 release, made by PX4's own generators.

The source of a release comes from ``git archive <tag>`` of a PX4 repository. PX4's generator
scripts run from that source, the way PX4's ``metadata_parameters`` build target runs them
(cmake/metadata.cmake). The generators are not copied into this project.

    python -m paramlineage.extract --repo <PX4 git repository> --python <python> --all

The python given with --python runs PX4's scripts and needs PyYAML and Jinja2.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

from .legal import LICENSE_PX4

# The layout of a snapshot file. Changes when a field is added, renamed or removed.
FORMAT = 1
# Changes when the same release would give a different snapshot, so old files can be told apart.
EXTRACTOR = 1

REPOSITORY = "https://github.com/PX4/PX4-Autopilot"

# The releases with a snapshot (docs/DESIGN.md, "Tracked versions"): every stable tag from v1.12.0
# on, and the newest release candidate until its final release.
TRACKED = [
    "v1.12.0", "v1.12.1", "v1.12.2", "v1.12.3",
    "v1.13.0", "v1.13.1", "v1.13.2", "v1.13.3",
    "v1.14.0", "v1.14.1", "v1.14.2", "v1.14.3", "v1.14.4",
    "v1.15.0", "v1.15.1", "v1.15.2", "v1.15.3", "v1.15.4",
    "v1.16.0", "v1.16.1", "v1.16.2",
    "v1.17.0",
    "v1.18.0-rc1",
]
ARCHIVE_PATHS = ["LICENSE", "src", "Tools", "boards/px4/fmu-v5", "boards/px4/io-v2"]

# The board PX4's metadata_parameters target generates for: the fmu-v5 timers with an IO board,
# Ethernet, and every serial port. Output and serial parameters that depend on the board
# (how many channels, which port is the default) follow this choice.
TIMER_CONFIG = "boards/px4/fmu-v5/src/timer_config.cpp"
BOARD = {"timer_config": TIMER_CONFIG, "io_board": True, "ethernet": True, "serial_ports": "all"}

# Module configs that define the same parameters as another module. PX4's metadata target leaves
# them out too. Each one is still generated on its own, and the names it has that the snapshot
# lacks are listed in the snapshot, so nothing is dropped silently.
EXCLUDED = [
    (
        re.compile(r"(^|/)pwm_out_sim/module_sim\.yaml$"),
        "Output driver of the simulator. It defines PWM_MAIN parameters, as the px4io driver does.",
    ),
    (
        re.compile(r"(^|/)linux_pwm_out/module\.yaml$"),
        "Output driver of Linux boards. It defines PWM_MAIN parameters, as the px4io driver does.",
    ),
    (
        re.compile(r"^src/modules/spacecraft/module\.yaml$"),
        "Control allocation config of the spacecraft build. It defines the CA_ parameters of "
        "src/modules/control_allocator with other defaults.",
    ),
]

# PX4 releases before v1.17 inject 21 parameters of UAVCAN nodes (ESCs and GNSS receivers) from
# src/lib/parameters/parameters_injected.xml. They are set on the node, not stored by PX4, and PX4
# removed the file for that reason (7b68c5dbfc, PX4 #25549). The generator gets an empty list.
EMPTY_INJECT_XML = "<?xml version='1.0' encoding='UTF-8'?>\n<parameters>\n  <version>3</version>\n</parameters>\n"

# The fields of a parameter, as PX4's JSON generator writes them. "name" becomes the key.
FIELDS = {
    "bitmask", "category", "decimalPlaces", "default", "group", "increment", "longDesc", "max",
    "min", "rebootRequired", "shortDesc", "type", "units", "values", "volatile",
}

# The top-level sections of a module config that the generators read, and the file
# Tools/module_config/generate_params.py reads the names of output functions from.
DATA_SECTION = re.compile(r"^(parameters|serial_config|actuator_output)\s*:", re.M)
OUTPUT_FUNCTIONS = "src/lib/mixer_module/output_functions.yaml"

BSD_3 = ("Redistribution and use in source and binary forms", "Neither the name")
LICENSE_WORDS = re.compile(r"licen[cs]e|copyright|spdx", re.I)


class ExtractError(Exception):
    pass


def git(repo: str, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if result.returncode:
        raise ExtractError(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def unpack(repo: str, commit: str, dest: str, paths: list[str] = ARCHIVE_PATHS) -> None:
    """Write ``paths`` (by default those the generators need), as committed at ``commit``, to ``dest``."""
    paths = [p for p in paths if git(repo, "ls-tree", "--name-only", commit, "--", p).strip()]
    data = git(repo, "archive", "--format=tar", commit, "--", *paths)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")


def config_files(tree: str) -> tuple[list[str], list[str]]:
    """All module configs under src/, and the excluded ones, as paths relative to ``tree``."""
    used, excluded = [], []
    for top, dirs, files in os.walk(os.path.join(tree, "src")):
        for name in files:
            if name.endswith(".yaml"):
                path = os.path.relpath(os.path.join(top, name), tree).replace(os.sep, "/")
                (excluded if any(p.search(path) for p, _ in EXCLUDED) else used).append(path)
    return sorted(used), sorted(excluded)


def source_dirs(tree: str) -> list[str]:
    """What ``find src -maxdepth 4 -type d`` lists: the directories PX4's target scans for parameters."""
    found = []
    for top, dirs, _ in os.walk(os.path.join(tree, "src")):
        rel = os.path.relpath(top, tree).replace(os.sep, "/")
        found.append(rel)
        if rel.count("/") >= 4:
            dirs.clear()
    return sorted(found)


class Generators:
    """Runs one release's generator scripts. The steps depend on which scripts and options exist."""

    def __init__(self, tree: str, python: str, work: str):
        self.tree, self.python, self.work = tree, python, work
        self.module_config = os.path.isfile(os.path.join(tree, "Tools/module_config/generate_params.py"))
        with open(os.path.join(tree, "src/lib/parameters/px_process_params.py"), encoding="utf-8") as f:
            self.inject_xml = "--inject-xml" in f.read()

    def steps(self) -> list[str]:
        steps = ["Tools/serial/generate_config.py --all-ports --ethernet"]
        if self.module_config:
            steps.append(f"Tools/module_config/generate_params.py --timer-config {TIMER_CONFIG} --board-with-io --ethernet")
        steps.append("src/lib/parameters/px_process_params.py" + (" --inject-xml <empty>" if self.inject_xml else ""))
        return steps

    def run(self, *args: str) -> None:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
        result = subprocess.run([self.python, "-s", *args], cwd=self.tree, env=env, capture_output=True, text=True)
        if result.returncode:
            output = (result.stdout + result.stderr).strip().splitlines()[-10:]
            raise ExtractError(f"{args[0]} failed:\n  " + "\n  ".join(output))

    def parameters(self, configs: list[str], scan: list[str], name: str) -> dict:
        """Generate the parameters of ``configs`` and of the sources in ``scan``; returns PX4's JSON."""
        out = os.path.join(self.work, name)
        os.makedirs(out)
        self.run("Tools/serial/generate_config.py", "--all-ports", "--ethernet",
                 "--params-file", os.path.join(out, "serial_params.c"), "--config-files", *configs)
        if self.module_config:
            self.run("Tools/module_config/generate_params.py", "--params-file", os.path.join(out, "module_params.c"),
                     "--timer-config", TIMER_CONFIG, "--board-with-io", "--ethernet", "--config-files", *configs)
        extra = []
        if self.inject_xml:
            empty = os.path.join(self.work, "empty_inject.xml")
            with open(empty, "w", encoding="utf-8") as f:
                f.write(EMPTY_INJECT_XML)
            extra = ["--inject-xml", empty]
        result = os.path.join(self.work, name + ".json")
        self.run("src/lib/parameters/px_process_params.py", "--src-path", *scan, out, "--json", result, *extra)
        with open(result, encoding="utf-8") as f:
            return json.load(f)

    def tools(self) -> dict:
        code = "import json, platform, yaml, jinja2; print(json.dumps({'python': platform.python_version(), 'pyyaml': yaml.__version__, 'jinja2': jinja2.__version__}))"
        result = subprocess.run([self.python, "-s", "-c", code], capture_output=True, text=True)
        if result.returncode:
            raise ExtractError(f"{self.python} cannot run PX4's generators (needs PyYAML and Jinja2):\n{result.stderr.strip()}")
        return json.loads(result.stdout)


def by_name(generated: dict, where: str) -> dict:
    params = {}
    for p in generated["parameters"]:
        p = dict(p)
        name = p.pop("name")
        if name in params:
            raise ExtractError(f"{where}: {name} is defined twice")
        unknown = set(p) - FIELDS
        if unknown:
            raise ExtractError(f"{where}: {name} has fields this extractor does not know: {sorted(unknown)}")
        params[name] = p
    return params


def license_of(path: str) -> str:
    """The license notice at the top of a file: "bsd-3-clause", "none", or "other"."""
    with open(path, encoding="utf-8", errors="replace") as f:
        head = "".join(f.readline() for _ in range(60))
    if all(clause in head for clause in BSD_3) or "SPDX-License-Identifier: BSD-3-Clause" in head:
        return "bsd-3-clause"
    return "other" if LICENSE_WORDS.search(head) else "none"


def check_licenses(tree: str, configs: list[str], scan: list[str]) -> dict:
    """Check that every file the parameter data can come from is under PX4's BSD-3-Clause license.

    Files with no notice of their own fall under the license of the repository (LICENSE).
    Configs count when they have a section the generators read; other YAML files under src/
    (such as the CI workflows of a submodule) are passed to the generators but add nothing.
    """
    files = [TIMER_CONFIG, OUTPUT_FUNCTIONS]
    for path in configs:
        with open(os.path.join(tree, path), encoding="utf-8", errors="replace") as f:
            if DATA_SECTION.search(f.read()):
                files.append(path)
    for d in scan:
        for name in sorted(os.listdir(os.path.join(tree, d))):
            path = f"{d}/{name}"
            if name.endswith((".c", ".h")) and os.path.isfile(os.path.join(tree, path)):
                with open(os.path.join(tree, path), encoding="utf-8", errors="replace") as f:
                    if "PARAM_DEFINE_" in f.read():
                        files.append(path)
    for top in ("Tools/serial", "Tools/module_config", "src/lib/parameters"):
        for name in sorted(os.listdir(os.path.join(tree, top)) if os.path.isdir(os.path.join(tree, top)) else []):
            if name.endswith((".py", ".jinja")):
                files.append(f"{top}/{name}")
    for name in sorted(os.listdir(os.path.join(tree, "src/lib/parameters/px4params"))):
        if name.endswith(".py"):
            files.append(f"src/lib/parameters/px4params/{name}")
    counts = {"bsd-3-clause": 0, "none": 0}
    other = []
    for path in sorted(p for p in set(files) if os.path.isfile(os.path.join(tree, p))):
        kind = license_of(os.path.join(tree, path))
        if kind == "other":
            other.append(path)
        else:
            counts[kind] += 1
    if other:
        raise ExtractError("files with a license notice that is not BSD-3-Clause:\n  " + "\n  ".join(other))
    return {"files": sum(counts.values()), "bsd_3_clause_notice": counts["bsd-3-clause"], "no_notice": counts["none"]}


def copyright_line(tree: str) -> str:
    """The copyright line of the release's LICENSE, after checking that its text is the one in LICENSE-THIRD-PARTY."""
    with open(os.path.join(tree, "LICENSE"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    expected = LICENSE_PX4.splitlines()
    holder = [line for line in lines if line.lower().startswith("copyright")]
    body = [line for line in lines if not line.lower().startswith("copyright")]
    if len(holder) != 1 or body != [line for line in expected if not line.lower().startswith("copyright")]:
        raise ExtractError("the release's LICENSE is not the BSD-3-Clause text in LICENSE-THIRD-PARTY")
    return holder[0]


def snapshot_of_tree(tree: str, python: str, source: dict) -> dict:
    """The snapshot of a PX4 source tree. ``source`` says where the tree came from."""
    with tempfile.TemporaryDirectory(prefix="paramlineage-") as work:
        gen = Generators(tree, python, work)
        configs, excluded = config_files(tree)
        scan = source_dirs(tree)
        params = by_name(gen.parameters(configs, scan, "all"), source["tag"])
        left_out = []
        for i, path in enumerate(excluded):
            names = by_name(gen.parameters([path], [], f"excluded-{i}"), path)
            reason = next(r for p, r in EXCLUDED if p.search(path))
            left_out.append({
                "config": path,
                "reason": reason,
                "parameters": len(names),
                "not_in_snapshot": sorted(set(names) - set(params)),
            })
        tools = gen.tools()
        steps = gen.steps()
    licenses = check_licenses(tree, configs, scan)
    return {
        "format": FORMAT,
        "source": source,
        "license": {
            "copyright": copyright_line(tree),
            "license": "BSD-3-Clause",
            "text": "LICENSE-THIRD-PARTY",
            "checked": licenses,
        },
        "extraction": {
            "extractor": EXTRACTOR,
            "steps": steps,
            "board": BOARD,
            "excluded_configs": left_out,
            "tools": tools,
        },
        "parameters": params,
    }


def snapshot(repo: str, tag: str, python: str) -> dict:
    """The snapshot of a tag of a PX4 git repository."""
    commit = git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").decode().strip()
    with tempfile.TemporaryDirectory(prefix="paramlineage-src-") as tree:
        unpack(repo, commit, tree)
        return snapshot_of_tree(tree, python, {"repository": REPOSITORY, "tag": tag, "commit": commit})


def dumps(data: dict) -> str:
    """The one way snapshot files are written, so that the same data always gives the same bytes."""
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def compare(old: str, new: str) -> str:
    """How a file on disk compares with a fresh extraction: "same", "same data" or "different".

    "same data" means only the versions of the tools that ran the generators differ.
    """
    if old == new:
        return "same"
    try:
        a, b = json.loads(old), json.loads(new)
    except ValueError:
        return "different"
    if dumps(a) != old:
        return "different"
    for d in (a, b):
        d.get("extraction", {}).pop("tools", None)
    return "same data" if a == b else "different"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paramlineage.extract", description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="a git repository of PX4 that has the tags")
    parser.add_argument("--python", default=sys.executable, help="the python that runs PX4's scripts (needs PyYAML and Jinja2)")
    parser.add_argument("--out", default=os.path.join("data", "snapshots"), help="where the <tag>.json files are (default: %(default)s)")
    parser.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing them")
    parser.add_argument("--all", action="store_true", help="every tracked tag")
    parser.add_argument("tags", nargs="*")
    args = parser.parse_args(argv)
    tags = TRACKED if args.all else args.tags
    if not tags:
        parser.error("give tags or --all")
    failed = 0
    for tag in tags:
        try:
            text = dumps(snapshot(args.repo, tag, args.python))
        except ExtractError as e:
            print(f"{tag}: {e}", file=sys.stderr)
            failed += 1
            continue
        path = os.path.join(args.out, f"{tag}.json")
        if args.check:
            try:
                with open(path, encoding="utf-8") as f:
                    result = compare(f.read(), text)
            except FileNotFoundError:
                result = "missing"
            if result == "same data":
                result += f" (tools now {json.loads(text)['extraction']['tools']})"
            print(f"{tag}: {result}")
            failed += result.startswith(("different", "missing"))
        else:
            os.makedirs(args.out, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"{tag}: {len(json.loads(text)['parameters'])} parameters")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
