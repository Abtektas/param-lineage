# SPDX-License-Identifier: BSD-3-Clause
"""SITL upgrades: what a PX4 release makes of the parameters an older release stored, on a real
in-place upgrade in software-in-the-loop simulation (docs/DESIGN.md, "Behaviour verification").

The older release stores values; the newer one then starts on the same parameter storage and
imports it, as after a firmware upgrade in place. Both run as px4_sitl_default builds with the SIH
quadrotor (airframe 10040), without a simulator GUI. The values come from the probes of the
newer release's translations, so every result can be compared with what the translations say.

    python -m paramlineage.sitl --old <PX4 tree at from> --new <PX4 tree at to> <from> <to>

Each tree must be checked out at its tag and built with ``make px4_sitl_default``. The runs start
PX4 as instance 0, so no other PX4 SITL may run at the same time.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from . import curated, extract
from .translations import float32, probe_values, short

# The layout of a SITL file. Changes when a field is added, renamed or removed.
FORMAT = 1
TARGET = "px4_sitl_default"
AIRFRAME = "10040_sihsim_quadx"
ENV = {"PX4_SIM_MODEL": "sihsim_quadx", "PX4_SIMULATOR": "sihsim"}
STARTED = "Startup script returned successfully"
# After the startup script, modules still start and may change parameters (calibration, for
# example); the values are read only after this many seconds.
SETTLE = 5.0

NOTES = [
    "One board: px4_sitl_default with the SIH quadrotor. A parameter it does not have cannot be set "
    "in the older release or converted to in the newer one, and a translation that checks whether a "
    "parameter exists finds it missing; such results are not-in-build, not pass or fail.",
    "The values are read after the newer release has started, so anything the firmware does with "
    "them after the import is part of the result.",
    "The import-order runs add stored values to the storage by hand, in a given order, to show what "
    "the real import does when the storage has both a parameter and the one it is converted to.",
]


# --- PX4's parameter storage (BSON with int32 and double elements, as tinybson writes it) ---

INT32, DOUBLE = 0x10, 0x01


def bson_decode(data: bytes) -> list[tuple[str, int | float]]:
    """The elements of a parameter storage file, in file order. Doubles are float32 values."""
    if len(data) < 5 or struct.unpack_from("<i", data)[0] != len(data):
        raise ValueError("not a parameter storage file")
    out, i = [], 4
    while data[i] != 0:
        kind, i = data[i], i + 1
        end = data.index(0, i)
        name, i = data[i:end].decode(), end + 1
        if kind == INT32:
            value, i = struct.unpack_from("<i", data, i)[0], i + 4
        elif kind == DOUBLE:
            value, i = short(struct.unpack_from("<d", data, i)[0]), i + 8
        else:
            raise ValueError(f"{name}: element type {kind:#x}")
        out.append((name, value))
    return out


def bson_encode(elements: list[tuple[str, int | float]]) -> bytes:
    """A parameter storage file with ``elements`` in this order: ints as int32, floats as double."""
    body = b""
    for name, value in elements:
        if isinstance(value, int):
            body += bytes([INT32]) + name.encode() + b"\0" + struct.pack("<i", value)
        else:
            body += bytes([DOUBLE]) + name.encode() + b"\0" + struct.pack("<d", float32(value))
    body += b"\0"
    return struct.pack("<i", len(body) + 4) + body


# --- running PX4 ---


class Px4:
    """One PX4 SITL build: starts it on a working directory and talks to it through px4-param."""

    def __init__(self, tree: str):
        self.tree = tree
        self.build = os.path.join(tree, "build", TARGET)
        self.bin = os.path.join(self.build, "bin")
        if not os.path.isfile(os.path.join(self.bin, "px4")):
            raise SystemExit(f"{tree}: no {TARGET} build; run make {TARGET} there")
        self.process = None

    def commit(self) -> str:
        return subprocess.run(["git", "-C", self.tree, "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()

    def compiler(self) -> str:
        with open(os.path.join(self.build, "CMakeCache.txt"), encoding="utf-8") as f:
            cxx = next(line.split("=", 1)[1].strip() for line in f if line.startswith("CMAKE_CXX_COMPILER:"))
        return subprocess.run([cxx, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]

    def tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([os.path.join(self.bin, "px4-param"), *args], capture_output=True, text=True, timeout=30)

    def start(self, work: str):
        if self.tool("show", "-q", "SYS_AUTOSTART").returncode == 0:
            raise SystemExit("another PX4 SITL is running as instance 0; stop it first")
        env = {k: v for k, v in os.environ.items() if not k.startswith("PX4_")} | ENV
        self.log = os.path.join(work, "px4.log")
        with open(self.log, "w") as log:
            self.process = subprocess.Popen([os.path.join(self.bin, "px4"), "-d", "-w", work, os.path.join(self.build, "etc")],
                                            cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 60
        while STARTED not in open(self.log, errors="replace").read():
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.kill()
                raise SystemExit(f"PX4 did not start; see {self.log}")
            time.sleep(0.2)
        time.sleep(SETTLE)

    def import_log(self) -> list[str]:
        """What the parameter code logged while it imported the storage."""
        with open(self.log, errors="replace") as f:
            return [line.strip() for line in f if line.startswith(("INFO  [parameters]", "WARN  [parameters]", "ERROR [parameters]"))]

    def show(self, name: str) -> int | float | None:
        """The value of a parameter, or None when the build does not have it."""
        out = self.tool("show", "-q", name)
        text = out.stdout.strip()
        if out.returncode != 0 or not text:
            return None
        return short(float(text)) if "." in text else int(text)

    def set_by_name(self, name: str, value: int | float) -> bool:
        """Set a parameter by name; whether the build has it. px4-param exits with 0 either way."""
        out = self.tool("set", name, str(value) if isinstance(value, int) else repr(float(value)))
        if out.returncode != 0:
            raise SystemExit(f"param set {name} {value} failed: {out.stdout}{out.stderr}")
        return "not found" not in out.stdout + out.stderr

    def set(self, name: str, value: int | float):
        if not self.set_by_name(name, value):
            raise SystemExit(f"param set {name}: the build does not have it")

    def stop(self, work: str) -> list[tuple[str, int | float]]:
        """Save the parameters, shut PX4 down, and return what it stored."""
        if self.tool("save").returncode != 0:
            raise SystemExit("param save failed")
        subprocess.run([os.path.join(self.bin, "px4-shutdown")], capture_output=True, timeout=30)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.kill()
            raise SystemExit("PX4 did not shut down")
        with open(os.path.join(work, "parameters.bson"), "rb") as f:
            return bson_decode(f.read())

    def kill(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()


# --- what to store, and what the translations say about it ---


def same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        return float32(a) == float32(b)
    return a == b


def candidates(meta: dict, cases: list[dict]) -> list[list]:
    """For each probe case of a stored value of the older type: the probe values in it that the older
    release accepts (within its range, one of its enum values), smallest first."""
    out = []
    allowed = {v["value"] for v in meta.get("values", [])}
    for c in cases:
        if c["stored"]["type"] != meta["type"]:
            continue
        values = [v for v in c["stored"]["values"] if not isinstance(v, str)
                  and (meta.get("min") is None or v >= meta["min"]) and (meta.get("max") is None or v <= meta["max"])
                  and (not allowed or v in allowed)]
        if values:
            out.append(sorted(values, key=lambda v: (abs(v), v)))
    return out


def find_case(cases: list[dict], kind: str, value) -> dict | None:
    for c in cases:
        if c["stored"]["type"] == kind and any(not isinstance(v, str) and same(v, value) for v in c["stored"]["values"]):
            return c
    return None


def expected(case: dict, value, new_params: dict) -> dict:
    """What the translations say a stored ``value`` becomes: {parameter of the newer release: value}."""
    def resolved(name, v):
        v = value if v == "stored" else v
        return int(v) if new_params[name]["type"] == "Int32" else short(float(v))
    result, out = case["outcome"], {}
    if result["result"] == "stored":
        out[result["name"]] = resolved(result["name"], result["value"])
    for name, v in result.get("also_set", {}).items():
        out[name] = resolved(name, v)
    return out


def uses_stored_values(case: dict) -> bool:
    """Whether the translation reads other parameters, whose values come from the storage in a real import."""
    return any(c["call"] == "param_get" for c in case["calls"])


# --- the runs ---


class Plan:
    """What one pair of releases is tested with."""

    def __init__(self, data_dir: str, old: str, new: str):
        def read(*path):
            with open(os.path.join(data_dir, *path), encoding="utf-8") as f:
                return json.load(f)
        self.old, self.new = old, new
        self.old_snapshot = read("snapshots", f"{old}.json")
        self.new_snapshot = read("snapshots", f"{new}.json")
        self.old_params, self.new_params = self.old_snapshot["parameters"], self.new_snapshot["parameters"]
        self.cases = read("translations", f"{new}.json")["parameters"]
        self.facts = curated.load(os.path.join(data_dir, "curated"), old, new)["removed"]
        changes = read("changes", f"{old}..{new}.json")
        # converted values: the migrated entries, and the parameters whose type changed
        self.converted = sorted([n for n, e in self.facts.items() if e["kind"] == "migrated"]
                                + [n for n, c in changes["changed"].items() if "type" in c])
        self.watched = sorted({s for e in self.facts.values() for s in e.get("successors", [])}
                              | {n for n, c in changes["changed"].items() if "type" in c})

    def branches(self) -> dict[str, list[list]]:
        return {n: candidates(self.old_params[n], self.cases.get(n, [])) for n in self.converted}

    def removed(self) -> dict[str, list]:
        """For each removed parameter that is not converted: its probe values that the older release
        accepts, smallest first. The translations list only the parameters their code touches; the
        others are probed with 0, 1, -1 and the values of their metadata."""
        out = {}
        for name in sorted(self.facts):
            if name in self.converted:
                continue
            meta = self.old_params[name]
            cases = self.cases.get(name) or [{"stored": {"type": meta["type"], "values": probe_values(
                [meta], "f" if meta["type"] == "Float" else "i", set())}}]
            values = {short(v) if isinstance(v, float) else v for vs in candidates(meta, cases) for v in vs}
            if values:
                out[name] = sorted(values, key=lambda v: (abs(v), v))
        return out

    def prediction(self, name: str, value) -> tuple[dict, dict | None]:
        """What the translations say a stored value of ``name`` becomes, and the probe case it is in.
        A parameter they do not list is left alone by the code, so it is imported as stored if the
        newer release has it, and ignored if not."""
        if name not in self.cases:
            return ({name: value} if name in self.new_params else {}), None
        case = find_case(self.cases[name], self.old_params[name]["type"], value)
        if case is None:
            raise SystemExit(f"{name}={value} is not a probe value of the translations of {self.new}")
        return expected(case, value, self.new_params), case

    def craft_value(self, name: str, avoid: list) -> int | float:
        """A value the newer release accepts for a parameter (one of its enum values, or near its
        default within its range) that is neither its default nor any of ``avoid``."""
        meta = self.new_params[name]
        default = meta.get("default", 0)
        if meta.get("values"):
            options = [v["value"] for v in meta["values"]]
        else:
            options = [default + step for step in (1, -1, 2, -2, 3, -3)]
        for v in options:
            v = int(v) if meta["type"] == "Int32" else float(v)
            if (meta.get("min") is None or v >= meta["min"]) and (meta.get("max") is None or v <= meta["max"]) \
                    and not same(v, default) and not any(same(v, a) for a in avoid):
                return v
        raise SystemExit(f"no value for {name}")


def upgrade(old: Px4, new: Px4, work: str, values: dict[str, list], watched: list[str],
            craft=None, by_name: dict | None = None) -> dict:
    """Store values in ``old``, start ``new`` on the same storage, and read what it has.

    ``values`` gives each parameter's candidate values; the first one that differs from the value the
    older release has (its default, or the airframe's) is stored. ``craft``, if given, gets the
    stored elements and returns the storage the newer release starts on, and the elements it moved
    to the end or added there, in order. ``by_name``, if given, is set in the newer release by
    name after it started, one parameter at a time."""
    run = {"set": {}, "not_in_build": []}
    old_dir, new_dir = os.path.join(work, "old"), os.path.join(work, "new")
    os.makedirs(old_dir)
    os.makedirs(new_dir)
    old.start(old_dir)
    try:
        for name, options in values.items():
            current = old.show(name)
            if current is None:
                run["not_in_build"].append(name)
                continue
            value = next((v for v in options if not same(v, current)), None)
            if value is None:
                continue
            old.set(name, value)
            run["set"][name] = value
    finally:
        stored = old.stop(old_dir)
    run["old_saved"] = dict(sorted(stored))
    for name, value in run["set"].items():
        if name not in run["old_saved"] or not same(run["old_saved"][name], value):
            raise SystemExit(f"{name}: set to {value}, but the older release stored {run['old_saved'].get(name)}")
        run["set"][name] = run["old_saved"][name]
    if craft:
        storage, added = craft(stored)
        run["storage"] = [[n, v] for n, v in added]
        with open(os.path.join(new_dir, "parameters.bson"), "wb") as f:
            f.write(bson_encode(storage))
    else:
        shutil.copy(os.path.join(old_dir, "parameters.bson"), new_dir)
    new.start(new_dir)
    try:
        if by_name:
            run["set_by_name"] = {}
            for name, value in sorted(by_name.items()):
                run["set_by_name"][name] = new.set_by_name(name, value)
        names = set(watched) | set(run["set"]) | {n for n, _ in run.get("storage", [])}
        run["after"] = {name: new.show(name) for name in sorted(names)}
        run["import_log"] = new.import_log()
    finally:
        run["new_saved"] = dict(sorted(new.stop(new_dir)))
    run["not_in_build"].sort()
    return run


def run_all(plan: Plan, old: Px4, new: Px4, work: str) -> list[dict]:
    runs = []

    def go(name, purpose, values, craft=None, by_name=None):
        print(f"{name}: {purpose}", file=sys.stderr)
        r = upgrade(old, new, os.path.join(work, name), values, plan.watched, craft, by_name)
        runs.append({"name": name, "purpose": purpose, **r})
        return r

    go("control-1", "Nothing stored: what the newer release has after an upgrade on its own.", {})
    go("control-2", "The same again, to tell values that change from run to run.", {})
    branches = plan.branches()
    for k in range(max((len(b) for b in branches.values()), default=0)):
        values = {n: b[k] for n, b in branches.items() if k < len(b)}
        go(f"converted-{k + 1}", f"Each converted parameter with a value from its probe case {k + 1}.", values)
    go("removed", "Every other removed parameter with a value that is not its default.", plan.removed())

    # The import order: a migrated parameter and a parameter it is converted to, both in the storage,
    # with the values of converted-1.
    first = next(r for r in runs if r["name"] == "converted-1")
    targets = {}
    for name, value in first["set"].items():
        if plan.facts.get(name, {}).get("kind") != "migrated":
            continue
        for target, v in plan.prediction(name, value)[0].items():
            if target != name and first["after"].get(target) is not None:
                targets.setdefault(name, []).append((target, plan.craft_value(target, [v])))

    def crafted(later: bool):
        def craft(stored):
            own = dict(stored)
            added = []
            for name, pairs in sorted(targets.items()):
                added += [(name, own[name]), *pairs] if later else [*pairs, (name, own[name])]
            return [e for e in stored if e[0] not in targets] + added, added
        return craft

    if targets:
        values = {n: [first["set"][n]] for n in targets}
        go("order-target-later", "Each migrated parameter followed in the storage by a parameter it is converted to.",
           values, crafted(True))
        go("order-target-earlier", "The same, with the parameter it is converted to first.", values, crafted(False))
    go("by-name", "Nothing stored; then each migrated parameter set by its old name in the newer release, one at "
       "a time, as loading a parameter file does.", {},
       by_name={n: v for n, v in first["set"].items() if plan.facts.get(n, {}).get("kind") == "migrated"})
    return runs


def unsteady(runs: list[dict]) -> list[str]:
    """Saved parameters whose value differs between the two control runs, in either release."""
    out = set()
    for key in ("old_saved", "new_saved"):
        a, b = runs[0][key], runs[1][key]
        out |= {n for n in set(a) | set(b) if not same(a.get(n), b.get(n))}
    return sorted(out)


def checks(data: dict, plan: Plan) -> list[dict]:
    """Every stored value against the translations: pass, fail, not-in-build, or observed (where the
    result depends on the import order, which the translations do not model)."""
    control = {r["name"]: r for r in data["runs"]}["control-1"]
    out = []
    for run in data["runs"]:
        if run["name"].startswith("control"):
            continue
        storage = run.get("storage")
        later = {}
        if storage:
            for i, (name, _) in enumerate(storage):
                later[name] = {n for n, _ in storage[i + 1:]}
        for name, value in sorted(run["set"].items()):
            want, case = plan.prediction(name, value)
            successors = plan.facts.get(name, {}).get("successors", [])
            for target in sorted(set(want) | set(successors)):
                exp = want.get(target, control["after"].get(target))
                if storage and target in dict(storage):
                    stored_target = dict(storage)[target]
                    if target in later.get(name, set()):
                        exp = stored_target  # imported after the translation, so it overwrites it
                    elif case and uses_stored_values(case):
                        exp = None  # the translation reads the value imported before it
                read = run["after"].get(target)
                if read is None:
                    result = "not-in-build"
                elif exp is None:
                    result = "observed"
                else:
                    result = "pass" if same(read, exp) else "fail"
                out.append({"run": run["name"], "parameter": name, "stored": value, "target": target,
                            "expected": exp, "read": read, "result": result})
    return out


def unexpected(data: dict, plan: Plan) -> dict[str, dict]:
    """Per run, the values the newer release saved that differ from control-1 although nothing
    explains them: neither a stored value and what the translations make of it, nor a value the
    older release changed on its own and the newer one imported as it was."""
    control = data["runs"][0]
    noisy = set(data["unsteady"])
    out = {}
    for run in data["runs"][2:]:
        explained = set(run["set"]) | {n for n, _ in run.get("storage", [])}
        for name, value in run["set"].items():
            explained |= set(plan.prediction(name, value)[0])
        for name, value in run["old_saved"].items():
            if not same(value, control["old_saved"].get(name)) and same(run["new_saved"].get(name), value):
                explained.add(name)
        saved = run["new_saved"]
        changed = {n: saved.get(n) for n in set(saved) | set(control["new_saved"])
                   if n not in noisy and n not in explained and not same(saved.get(n), control["new_saved"].get(n))}
        if changed:
            out[run["name"]] = dict(sorted(changed.items()))
    return out


def summary(results: list[dict]) -> dict[str, dict[str, int]]:
    out = {}
    for c in results:
        out.setdefault(c["parameter"], {}).setdefault(c["result"], 0)
        out[c["parameter"]][c["result"]] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paramlineage.sitl", description=__doc__.split("\n\n")[0])
    parser.add_argument("--old", required=True, help="a PX4 tree checked out at <from>, built with make " + TARGET)
    parser.add_argument("--new", required=True, help="a PX4 tree checked out at <to>, built with make " + TARGET)
    parser.add_argument("--data", default="data", help="the data directory (default: %(default)s)")
    parser.add_argument("--keep", help="keep the working directories of the runs here")
    parser.add_argument("old_tag", metavar="from")
    parser.add_argument("new_tag", metavar="to")
    args = parser.parse_args(argv)
    plan = Plan(args.data, args.old_tag, args.new_tag)
    old, new = Px4(args.old), Px4(args.new)
    for px4, snapshot, tag in ((old, plan.old_snapshot, args.old_tag), (new, plan.new_snapshot, args.new_tag)):
        if px4.commit() != snapshot["source"]["commit"]:
            raise SystemExit(f"{px4.tree} is not at {tag} ({snapshot['source']['commit']})")
    work = args.keep or tempfile.mkdtemp(prefix="paramlineage-sitl-")
    try:
        runs = run_all(plan, old, new, work)
    finally:
        old.kill()
        new.kill()
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    data = {
        "format": FORMAT,
        "from": {"tag": args.old_tag, "commit": plan.old_snapshot["source"]["commit"]},
        "to": {"tag": args.new_tag, "commit": plan.new_snapshot["source"]["commit"]},
        "build": {"target": TARGET, "airframe": AIRFRAME, "compiler": {args.old_tag: old.compiler(), args.new_tag: new.compiler()},
                  "platform": f"{platform.system()} {platform.machine()}"},
        "notes": NOTES,
        "runs": runs,
    }
    data["unsteady"] = unsteady(runs)
    data["checks"] = checks(data, plan)
    data["unexpected"] = unexpected(data, plan)
    path = os.path.join(args.data, "sitl", f"{args.old_tag}..{args.new_tag}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(extract.dumps(data))
    for name, counts in summary(data["checks"]).items():
        print(f"{name}: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    if data["unexpected"]:
        print(f"unexpected changes: {data['unexpected']}")
    print(f"wrote {path}")
    return 1 if data["unexpected"] or any(c["result"] == "fail" for c in data["checks"]) else 0


if __name__ == "__main__":
    sys.exit(main())
