# SPDX-License-Identifier: BSD-3-Clause
"""Translations: what a PX4 release does to stored parameter values when it imports them.

A release's src/lib/parameters/param_translation.cpp is compiled unchanged, with the release's own
headers and the harness in harness/, and run on probe values (docs/DESIGN.md, "2. Translations").
The source comes from ``git archive <tag>``; the compiled program is deleted after the run.
Of PX4's code, only three lines of harness/platform.h are copied, marked there (LICENSE-THIRD-PARTY).

    python -m paramlineage.translations --repo <PX4 git repository> --all

Needs a C++17 compiler (--cxx) and the snapshots in data/snapshots.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

from . import extract
from .extract import ExtractError

# The layout of a translations file. Changes when a field is added, renamed or removed.
FORMAT = 1
# Changes when the same release would give a different file, so old files can be told apart.
EXTRACTOR = 1

TRANSLATION = "src/lib/parameters/param_translation.cpp"
ARCHIVE_PATHS = [
    "LICENSE", "src/lib/parameters", "src/lib/tinybson", "src/lib/drivers/device", "src/lib/mathlib",
    "src/lib/matrix", "src/drivers/drv_sensor.h",
]
INCLUDE_DIRS = ["src/lib/parameters", "src/lib", "src/lib/matrix", "src"]
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harness")
FLAGS = ["-std=c++17", "-O0", "-w", "-ffp-contract=off"]
# nuttx defines __PX4_NUTTX for the code of param_translation.cpp, as a NuttX build does.
PLATFORMS = {"nuttx": ["-DPL_NUTTX"], "posix": []}
# PX4's platform headers the code includes; each is written at build time and includes harness/platform.h.
PLATFORM_HEADERS = ["defines.h", "log.h", "posix.h", "px4_config.h"]

# How the release imports a stored value after the translation, from param_import_callback() in
# src/lib/parameters/parameters.cpp and src/lib/parameters/flashparams/flashparams.cpp. Read for
# every tracked tag: up to v1.14 the return value is ignored, from v1.15 PARAM_SKIP_IMPORT stops
# the import of that value; then a name the firmware does not have, or a value of the other
# type, is ignored, and anything else is stored. The extractor stops when a release's import code
# is not one of these (whitespace aside), so that a change is read before it counts.
IMPORT_CODE = {
    "c633cea5a205521c": "return ignored",  # parameters.cpp, v1.12.0 to v1.12.3
    "3905e605f97b2c29": "return ignored",  # flashparams.cpp, v1.12.0 to v1.12.3
    "3a17a035242f7802": "return ignored",  # parameters.cpp, v1.13.0 to v1.14.4
    "b7a9f56a2674244c": "return ignored",  # flashparams.cpp, v1.13.0 to v1.14.4
    "587bb5a9b2fcc587": "PARAM_SKIP_IMPORT skips",  # parameters.cpp, v1.15.0 to v1.18.0-rc1
    "6dae47c63f4c26ef": "PARAM_SKIP_IMPORT skips",  # flashparams.cpp, v1.15.0 to v1.18.0-rc1
}
IMPORT_FILES = ["src/lib/parameters/parameters.cpp", "src/lib/parameters/flashparams/flashparams.cpp"]

NOTES = [
    "PX4 runs this code only when it imports the stored parameters of a vehicle, as after a firmware "
    "upgrade in place. Loading a parameter file by name does not run it.",
    "Each probe is one stored value imported on its own. param_find knows the parameters of this "
    "release's snapshot, and param_get returns their defaults; during a real import, param_get "
    "returns values imported earlier from the same storage, and a value set here can be "
    "overwritten by a stored value imported later.",
    "A firmware built without some modules has fewer parameters, so code that checks whether a "
    "parameter exists can behave differently there.",
    "What the firmware does with the values after the import (for example replacing -1 with a "
    "default) is not part of this data.",
]

NAME = re.compile(r"[A-Z][A-Z0-9_]*")
CALL = re.compile(
    r"\b(strcmp|strncmp|strstr|strcpy|strncpy|strcat|snprintf|param_find|param_set_no_notification|"
    r"param_set|param_get|PX4_INFO|PX4_WARN|PX4_ERR|PX4_PANIC)\s*\("
)
LOG = {"PX4_INFO", "PX4_WARN", "PX4_ERR", "PX4_PANIC"}
COMPARISONS = {"strcmp", "strncmp", "strstr"}
NUMBER = re.compile(r"(?<![\w.#])(0[xX][0-9a-fA-F]+|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)[uUlLfF]*(?![\w.])")
PREFIX = re.compile(r"\bstrncmp\s*\(\s*\"#(\d+)\"")
TYPES = {"i": "Int32", "f": "Float"}
INT32 = (-(2**31), 2**31 - 1)


def float32(x: float) -> float:
    """``x`` rounded to the nearest float32, as PX4 stores a float parameter."""
    return struct.unpack("f", struct.pack("f", x))[0]


def short(x: float) -> float:
    """The shortest decimal that is the same float32 as ``x``, so 1.79999995 is written 1.8."""
    if x == 0:
        return 0.0
    for digits in range(1, 10):
        s = float(f"{x:.{digits}g}")
        if float32(s) == float32(x):
            return s
    return x


class Source:
    """param_translation.cpp, read as far as the extraction needs: where the calls the harness
    records are, and the string and number literals. Comments are left out."""

    def __init__(self, text: str):
        self.text = text
        self.literals: list[tuple[int, str]] = []
        self.code = self._strip(text)
        self.calls = self._calls()

    def line_at(self, pos: int) -> int:
        return self.code.count("\n", 0, pos) + 1

    def _strip(self, text: str) -> str:
        """The code with comments removed and every string literal replaced by "#<index>"."""
        out, i, n = [], 0, len(text)
        while i < n:
            if text.startswith("//", i):
                end = text.find("\n", i)
                i = n if end < 0 else end
            elif text.startswith("/*", i):
                end = text.find("*/", i + 2)
                if end < 0:
                    raise ExtractError(f"{TRANSLATION}: unterminated comment")
                out.append(" " + "\n" * text.count("\n", i, end))
                i = end + 2
            elif text[i] in "\"'":
                quote, j, chars = text[i], i + 1, []
                while j < n and text[j] != quote:
                    if text[j] == "\n" or text.startswith("\\\n", j):
                        raise ExtractError(f"{TRANSLATION}: line break in a literal")
                    chars.append(text[j:j + 2] if text[j] == "\\" else text[j])
                    j += 2 if text[j] == "\\" else 1
                if quote == '"':
                    self.literals.append((text.count("\n", 0, i) + 1, "".join(chars)))
                    out.append(f'"#{len(self.literals) - 1}"')
                else:
                    out.append("' '")
                i = j + 1
            else:
                out.append(text[i])
                i += 1
        return "".join(out)

    def _calls(self) -> list[dict]:
        """Every call the harness records: the function, and the first and last line of the call."""
        calls = []
        for m in CALL.finditer(self.code):
            depth, pos = 0, m.end() - 1
            while True:
                if pos >= len(self.code):
                    raise ExtractError(f"{TRANSLATION}: unbalanced parentheses")
                depth += {"(": 1, ")": -1}.get(self.code[pos], 0)
                if depth == 0:
                    break
                pos += 1
            name = m.group(1)
            calls.append({"call": "log" if name in LOG else name, "line": self.line_at(m.start()), "last": self.line_at(pos)})
        return calls

    def site(self, call: str, line: int) -> int:
        """The first line of the call of ``call`` that the harness reported at ``line``.

        Compilers differ in which line of a call that spans lines __LINE__ gives, so every line of
        the call counts as the call."""
        starts = {c["line"] for c in self.calls if c["call"] == call and c["line"] <= line <= c["last"]}
        if len(starts) != 1:
            raise ExtractError(f"{TRANSLATION}: the harness reported {call} at line {line}, which is "
                               f"{'no' if not starts else 'more than one'} call in the source")
        return starts.pop()

    def includes(self) -> list[str]:
        return [line for line in self.text.splitlines() if re.match(r"\s*#\s*include\b", line)]

    def names(self) -> dict[str, dict]:
        """The string literals that are parameter names, with their lines; "prefix" when the code
        compares only the start of a name with it (strncmp)."""
        prefixes = {int(i) for i in PREFIX.findall(self.code)}
        names: dict[str, dict] = {}
        for index, (line, value) in enumerate(self.literals):
            if NAME.fullmatch(value) and len(value) <= 16:
                entry = names.setdefault(value, {"lines": set(), "prefix": False})
                entry["lines"].add(line)
                entry["prefix"] |= index in prefixes
        return names

    def numbers(self) -> set:
        """The numbers in the code, and their negatives."""
        found = set()
        for line in self.code.splitlines():
            if line.lstrip().startswith("#"):
                continue
            for text in NUMBER.findall(line):
                if text.lower().startswith("0x"):
                    value = int(text, 16)
                elif re.fullmatch(r"\d+", text):
                    value = int(text)
                else:
                    value = float(text)
                found.update((value, -value))
        return found


def import_model(tree: str, import_code: dict) -> str:
    """How the release imports a translated value: one of the values of ``import_code``."""
    models = set()
    for path in IMPORT_FILES:
        full = os.path.join(tree, path)
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            m = re.search(r"^param_import_callback\(.*?^}", f.read(), re.M | re.S)
        if not m:
            raise ExtractError(f"{path}: param_import_callback() not found; read the import code")
        digest = hashlib.sha256(" ".join(m.group(0).split()).encode()).hexdigest()[:16]
        if digest not in import_code:
            raise ExtractError(f"{path}: the import code ({digest}) is not one this extractor knows; "
                               "read it and add it to IMPORT_CODE")
        models.add(import_code[digest])
    if len(models) != 1:
        raise ExtractError(f"the import code differs between {', '.join(IMPORT_FILES)}: {sorted(models)}")
    return models.pop()


def probe_values(meta: list[dict], kind: str, numbers: set) -> list:
    """The values to probe a parameter with: 0, 1, -1, the numbers of the code, and from each
    snapshot that has the parameter, its default, min, max, enum values and bitmask bits."""
    values = {0, 1, -1, *numbers}
    for p in meta:
        values.update(p[k] for k in ("default", "min", "max") if k in p)
        values.update(v["value"] for v in p.get("values", []))
        values.update(1 << b["index"] for b in p.get("bitmask", []) if 0 <= b["index"] < 31)
        values.update(-(2**31) for b in p.get("bitmask", []) if b["index"] == 31)
    if kind == "i":
        return sorted({int(v) for v in values if float(v).is_integer() and INT32[0] <= v <= INT32[1]})
    out = set()
    for v in values:
        try:
            f = float32(float(v))
        except OverflowError:
            continue
        out.add(f + 0.0)  # no -0.0
    return sorted(out)


def probes(snapshots: list[tuple[str, dict]], source: Source) -> dict[tuple[str, str], list]:
    """(name, kind) -> values. Names: every parameter of the snapshots, and every name the code
    compares with; kinds: the types the snapshots give it, or both for names only the code has."""
    meta: dict[str, list] = {}
    kinds: dict[str, set] = {}
    for _, snapshot in snapshots:
        for name, p in snapshot["parameters"].items():
            meta.setdefault(name, []).append(p)
            kinds.setdefault(name, set()).add("f" if p["type"] == "Float" else "i")
    for name, entry in source.names().items():
        if not entry["prefix"] and name not in kinds:
            kinds[name] = {"i", "f"}
    numbers = source.numbers()
    return {(name, kind): probe_values(meta.get(name, []), kind, numbers)
            for name in sorted(kinds) for kind in sorted(kinds[name])}


def value_text(kind: str, value) -> str:
    return str(int(value)) if kind == "i" else repr(float(value))


def number(value):
    """A value as the harness printed it, as it goes into the data."""
    if isinstance(value, str):
        return value  # "inf", "-inf" or "nan"
    return value if isinstance(value, int) else short(value)


def run(binary: str, params: str, lines: list[str]) -> tuple[list[dict], dict]:
    result = subprocess.run([binary, params], input="".join(lines), capture_output=True, text=True)
    if result.returncode:
        raise ExtractError(f"the harness failed: {result.stderr.strip()}")
    out = [json.loads(line) for line in result.stdout.splitlines()]
    if not out or "reached" not in out[-1]:
        raise ExtractError("the harness stopped early")
    return out[:-1], out[-1]


def build(tree: str, work: str, cxx: str, source: Source) -> tuple[dict, set]:
    """Compile the harness for each platform; returns the programs and the files of the tree they include."""
    include = os.path.join(work, "include")
    os.makedirs(os.path.join(include, "px4_platform_common"))
    for header in PLATFORM_HEADERS:
        with open(os.path.join(include, "px4_platform_common", header), "w", encoding="utf-8") as f:
            f.write(f'#include "{os.path.join(HARNESS, "platform.h")}"\n')
    with open(os.path.join(include, "translation_includes.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(source.includes()) + "\n")
    binaries, used = {}, set()
    for platform, defines in PLATFORMS.items():
        binary, deps = os.path.join(work, f"harness-{platform}"), os.path.join(work, f"harness-{platform}.d")
        command = [cxx, *FLAGS, *defines, "-I", include, *[f"-I{os.path.join(tree, d)}" for d in INCLUDE_DIRS],
                   "-MD", "-MF", deps, os.path.join(HARNESS, "harness.cpp"), "-o", binary]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            output = (result.stdout + result.stderr).strip().splitlines()[:20]
            raise ExtractError(f"the harness does not compile ({platform}):\n  " + "\n  ".join(output))
        with open(deps, encoding="utf-8") as f:
            files = f.read().replace("\\\n", " ").split(":", 1)[1].split()
        root = os.path.realpath(tree) + os.sep
        used.update(os.path.relpath(os.path.realpath(p), root).replace(os.sep, "/")
                    for p in files if os.path.realpath(p).startswith(root))
        binaries[platform] = binary
    return binaries, used


def run_harness(tree: str, cxx: str, source: Source, params: dict, lines: list[str]) -> tuple[dict, set]:
    """Build the harness and run the probe ``lines`` on each platform; ``params`` are the
    parameters param_find knows. Returns platform -> (records, summary), and the files compiled."""
    with tempfile.TemporaryDirectory(prefix="paramlineage-harness-") as work:
        binaries, used = build(tree, work, cxx, source)
        table = os.path.join(work, "parameters.txt")
        with open(table, "w", encoding="utf-8") as f:
            for name in sorted(params):
                kind = "f" if params[name]["type"] == "Float" else "i"
                f.write(f"{name} {kind} {value_text(kind, params[name]['default'])}\n")
        return {platform: run(binary, table, lines) for platform, binary in binaries.items()}, used


def run_probes(repo: str, tag: str, cxx: str, params: dict, probes: list[tuple[str, str, object]]) -> dict:
    """Run chosen probes (name, "i" or "f", value) on a tag's translation code; platform -> records.
    For values the generic probes do not reach, such as the device IDs of v1.12."""
    commit = extract.git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").decode().strip()
    with tempfile.TemporaryDirectory(prefix="paramlineage-src-") as tree:
        extract.unpack(repo, commit, tree, ARCHIVE_PATHS)
        with open(os.path.join(tree, TRANSLATION), encoding="utf-8") as f:
            source = Source(f.read())
        lines = [f"{name} {kind} {value_text(kind, value)}\n" for name, kind, value in probes]
        results, _ = run_harness(tree, cxx, source, params, lines)
    return {platform: records for platform, (records, _) in results.items()}


def check_licenses(tree: str, files: set) -> dict:
    """Every file of the release that was compiled has a BSD-3-Clause notice or none."""
    counts = {"bsd-3-clause": 0, "none": 0}
    other = []
    for path in sorted(files):
        kind = extract.license_of(os.path.join(tree, path))
        if kind == "other":
            other.append(path)
        else:
            counts[kind] += 1
    if other:
        raise ExtractError("compiled files with a license notice that is not BSD-3-Clause:\n  " + "\n  ".join(other))
    return {"files": sum(counts.values()), "bsd_3_clause_notice": counts["bsd-3-clause"], "no_notice": counts["none"]}


def compiler_version(cxx: str) -> str:
    result = subprocess.run([cxx, "--version"], capture_output=True, text=True)
    if result.returncode or not result.stdout.strip():
        raise ExtractError(f"cannot run the C++ compiler {cxx!r}")
    return result.stdout.strip().splitlines()[0]


def outcome(node: dict, returned, model: str, params: dict, calls: list[dict]) -> dict:
    """What the import does with the node after the translation (see IMPORT_CODE)."""
    if model == "PARAM_SKIP_IMPORT skips" and returned == "PARAM_SKIP_IMPORT":
        result = {"result": "skipped"}
    elif node["name"] not in params:
        result = {"result": "ignored-unknown-name", "name": node["name"]}
    elif node["type"] != params[node["name"]]["type"]:
        result = {"result": "ignored-type", "name": node["name"]}
    elif node["type"] == "Int32":
        result = {"result": "stored", "name": node["name"], "value": (node["value"] + 2**31) % 2**32 - 2**31}
    else:
        result = {"result": "stored", "name": node["name"], "value": node["value"]}
    also = {}
    for c in calls:
        if c["call"].startswith("param_set") and c["result"] == 0:
            also[c["param"]] = c["value"]
    if also:
        result["also_set"] = also
    return result


def case(record: dict, model: str, params: dict, source: Source) -> dict:
    """One probe's result, in data form, with lines given as the first line of each call."""
    node = dict(record["node"])
    node["type"] = TYPES.get(node["type"], node["type"])
    if "value" in node:
        node["value"] = number(node["value"])
    calls = []
    for c in record["calls"]:
        c = dict(c)
        c["line"] = source.site(c["call"], c["line"])
        if "value" in c:
            c["value"] = number(c["value"])
        calls.append(c)
    out = {
        "touched": True,
        "return": record["return"],
        "node": node,
        "matched": sorted({source.site(k, line) for k, line in record["matched"]}),
        "calls": calls,
        "outcome": outcome(node, record["return"], model, params, calls),
    }
    if record["depends_on"]:
        out["depends_on"] = record["depends_on"]
    return out


def untouched_case(name: str, kind: str, value, returned, model: str, params: dict) -> dict:
    """The result of a probe the code left alone."""
    node = {"name": name, "type": TYPES[kind], "value": number(value)}
    return {"touched": False, "return": returned, "node": node, "matched": [], "calls": [],
            "outcome": outcome(node, returned, model, params, [])}


def value_fields(c: dict, params: dict):
    """The values of a case that can be the stored value: (field, value, type of the parameter)."""
    if "value" in c["node"]:
        yield ("node",), c["node"]["value"], c["node"]["type"]
    for i, call in enumerate(c["calls"]):
        if "value" in call and call.get("param") in params:
            yield ("call", i, call["line"], call["param"]), call["value"], params[call["param"]]["type"]
    result = c["outcome"]
    if "value" in result:
        yield ("outcome",), result["value"], params[result["name"]]["type"]
    for name, value in result.get("also_set", {}).items():
        yield ("also_set", name), value, params[name]["type"]


def copies(c: dict, stored, kind: str, params: dict) -> set:
    """The fields of a case that hold the stored value itself (same type, same value)."""
    return {field for field, value, type_ in value_fields(c, params)
            if type_ == TYPES[kind] and not isinstance(value, str) and value == number(stored)}


def with_stored(c: dict, fields: set) -> dict:
    """``c`` with the values of ``fields`` written "stored"."""
    c = json.loads(json.dumps(c))
    for field in fields:
        if field[0] == "node":
            c["node"]["value"] = "stored"
        elif field[0] == "call":
            c["calls"][field[1]]["value"] = "stored"
        elif field[0] == "outcome":
            c["outcome"]["value"] = "stored"
        else:
            c["outcome"]["also_set"][field[1]] = "stored"
    return c


def translations_of_tree(tree: str, cxx: str, source_info: dict, snapshots: list[tuple[str, dict]],
                         import_code: dict = IMPORT_CODE) -> dict:
    """The translations file of a PX4 source tree. ``snapshots`` are the snapshots of every tracked
    release up to this one, oldest first; the last is this release's."""
    with open(os.path.join(tree, TRANSLATION), encoding="utf-8") as f:
        source = Source(f.read())
    model = import_model(tree, import_code)
    params = snapshots[-1][1]["parameters"]
    probed = probes(snapshots, source)
    lines = [f"{name} {kind} {value_text(kind, v)}\n" for (name, kind), values in probed.items() for v in values]

    results, used = run_harness(tree, cxx, source, params, lines)
    untouched_return = {summary["untouched_return"] for _, summary in results.values()}
    if len(untouched_return) != 1:
        raise ExtractError("the platforms disagree on the return value of an untouched probe")
    untouched_return = untouched_return.pop()
    if (model == "return ignored") != isinstance(untouched_return, bool):
        raise ExtractError(f"param_modify_on_import() returns {untouched_return!r}, but the import code is '{model}'")

    # probe -> platform -> its case
    cases: dict[tuple, dict] = {}
    for platform, (records, _) in results.items():
        for r in records:
            key = (r["name"], r["type"], float(r["value"]) if r["type"] == "f" else int(r["value"]))
            cases.setdefault(key, {})[platform] = case(r, model, params, source)

    touched_names = sorted({name for name, _, _ in cases})
    parameters = {}
    for name in touched_names:
        entries = []  # (kind, value, platform or None, case)
        for kind in ("i", "f"):
            for value in probed.get((name, kind), []):
                by_platform = cases.get((name, kind, value), {})
                if not by_platform:
                    entries.append((kind, value, None, untouched_case(name, kind, value, untouched_return, model, params)))
                elif len(by_platform) == len(PLATFORMS) and len({json.dumps(c, sort_keys=True) for c in by_platform.values()}) == 1:
                    entries.append((kind, value, None, next(iter(by_platform.values()))))
                else:
                    for platform in PLATFORMS:
                        c = by_platform.get(platform) or untouched_case(name, kind, value, untouched_return, model, params)
                        entries.append((kind, value, platform, c))
        # A field is written "stored" where it holds the stored value for two or more stored
        # values, so that probes that behave alike read alike. A constant that equals the stored
        # value of a single probe keeps its number, so it is not read as a copy.
        held: dict[tuple, set] = {}
        for kind, value, _, c in entries:
            for field in copies(c, value, kind, params):
                held.setdefault((kind, field), set()).add(value)
        groups: dict[str, dict] = {}
        for kind, value, platform, c in entries:
            fields = {f for f in copies(c, value, kind, params) if len(held[(kind, f)]) >= 2}
            c = dict(with_stored(c, fields), stored={"type": TYPES[kind]})
            if platform:
                c["platform"] = platform
            groups.setdefault(json.dumps(c, sort_keys=True), c).setdefault("values", []).append(number(value))
        out = []
        for c in groups.values():
            c["stored"]["values"] = c.pop("values")
            out.append(c)
        parameters[name] = out

    # coverage
    reached: dict[tuple[str, int], set] = {}
    for platform, (_, summary) in results.items():
        for call, line in summary["reached"]:
            reached.setdefault((call, source.site(call, line)), set()).add(platform)
    calls = [{"line": line, "call": call, "reached": sorted(reached.get((call, line), set()))}
             for line, call in sorted({(c["line"], c["call"]) for c in source.calls})]
    known = {name for _, s in snapshots for name in s["parameters"]}
    used_names, matched_lines = set(), set()
    for platform, (records, _) in results.items():
        for r in records:
            if r["matched"]:
                used_names.add(r["name"])
            if r["node"]["name"] != r["name"]:
                used_names.add(r["node"]["name"])
            used_names.update(c["name"] for c in r["calls"] if c["call"] == "param_find")
            matched_lines.update(source.site(k, line) for k, line in r["matched"] if k == "strncmp")
    names = []
    for name, entry in sorted(source.names().items()):
        item = {"name": name, "lines": sorted(entry["lines"]), "tracked": name in known}
        if entry["prefix"]:
            item["prefix"] = True
            strncmp_lines = {c["line"] for c in source.calls if c["call"] == "strncmp"}
            item["reached"] = bool(entry["lines"] & strncmp_lines & matched_lines)
        else:
            item["reached"] = name in used_names
        names.append(item)

    total = len(lines)
    listed = sum(len(probed.get((name, kind), [])) for name in touched_names for kind in ("i", "f"))
    return {
        "format": FORMAT,
        "source": dict(source_info, file=TRANSLATION),
        "license": {
            "copyright": extract.copyright_line(tree),
            "license": "BSD-3-Clause",
            "text": "LICENSE-THIRD-PARTY",
            "checked": check_licenses(tree, used),
        },
        "extraction": {
            "extractor": EXTRACTOR,
            "compiler": compiler_version(cxx),
            "flags": FLAGS,
            "platforms": sorted(PLATFORMS),
            "import": model,
            "snapshots": [tag for tag, _ in snapshots],
            "probes": {"names": len({n for n, _ in probed}), "values": total, "listed": listed,
                       "untouched_not_listed": total - listed},
        },
        "notes": NOTES,
        "parameters": parameters,
        "coverage": {"calls": calls, "names": names},
    }


def load_snapshots(directory: str, tag: str) -> list[tuple[str, dict]]:
    """The snapshots of the tracked releases up to and including ``tag``, oldest first."""
    if tag not in extract.TRACKED:
        raise ExtractError(f"{tag} is not a tracked release")
    out = []
    for t in extract.TRACKED[: extract.TRACKED.index(tag) + 1]:
        with open(os.path.join(directory, f"{t}.json"), encoding="utf-8") as f:
            out.append((t, json.load(f)))
    return out


def translations(repo: str, tag: str, cxx: str, snapshots: list[tuple[str, dict]],
                 import_code: dict = IMPORT_CODE) -> dict:
    """The translations file of a tag of a PX4 git repository."""
    commit = extract.git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").decode().strip()
    if snapshots[-1][1]["source"]["commit"] != commit:
        raise ExtractError(f"{tag}: the snapshot was made from another commit; extract it again")
    with tempfile.TemporaryDirectory(prefix="paramlineage-src-") as tree:
        extract.unpack(repo, commit, tree, ARCHIVE_PATHS)
        return translations_of_tree(tree, cxx, {"repository": extract.REPOSITORY, "tag": tag, "commit": commit},
                                    snapshots, import_code)


def dumps(data: dict) -> str:
    """The one way translations files are written, so that the same data always gives the same bytes."""
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def compare(old: str, new: str) -> str:
    """How a file on disk compares with a fresh extraction: "same", "same data" or "different".

    "same data" means only the compiler differs.
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
        d.get("extraction", {}).pop("compiler", None)
    return "same data" if a == b else "different"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paramlineage.translations", description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="a git repository of PX4 that has the tags")
    parser.add_argument("--cxx", default=os.environ.get("CXX", "c++"), help="the C++17 compiler (default: $CXX or c++)")
    parser.add_argument("--snapshots", default=os.path.join("data", "snapshots"), help="where the snapshots are (default: %(default)s)")
    parser.add_argument("--out", default=os.path.join("data", "translations"), help="where the <tag>.json files are (default: %(default)s)")
    parser.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing them")
    parser.add_argument("--all", action="store_true", help="every tracked tag")
    parser.add_argument("tags", nargs="*")
    args = parser.parse_args(argv)
    tags = extract.TRACKED if args.all else args.tags
    if not tags:
        parser.error("give tags or --all")
    failed = 0
    for tag in tags:
        try:
            text = dumps(translations(args.repo, tag, args.cxx, load_snapshots(args.snapshots, tag)))
        except (ExtractError, OSError) as e:
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
                result += f" (compiler now {json.loads(text)['extraction']['compiler']})"
            print(f"{tag}: {result}")
            failed += result.startswith(("different", "missing"))
        else:
            os.makedirs(args.out, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            data = json.loads(text)
            print(f"{tag}: {len(data['parameters'])} parameters touched")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
