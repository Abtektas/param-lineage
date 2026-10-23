# SPDX-License-Identifier: BSD-3-Clause
"""Histories: the states of every parameter across the tracked releases (data/params.json).

Made from the snapshots and the curated facts (docs/DESIGN.md, "4. Built views"). A new state
starts exactly where data/changes reports a change of the parameter. One file for all parameters,
so that no file is named after a parameter (some PX4 parameter names contain "PX4").

    python -m paramlineage.history --all [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import changes, curated, extract

# The layout of a history file. Changes when a field is added, renamed or removed.
FORMAT = 1


def state(param: dict) -> dict:
    """The fields of a snapshot entry that make up a state: those the changes compare."""
    out = {field: param[field] for field in changes.FIELDS if field in param}
    out["rebootRequired"] = bool(param.get("rebootRequired"))
    return out


def histories(snapshots: list[tuple[str, dict]], facts: dict[tuple[str, str], dict]) -> dict[str, dict]:
    """Every parameter's history, from the snapshots (oldest first) and the curated facts by (from, to)."""
    out: dict[str, dict] = {}
    previous: tuple[str, dict] | None = None
    for tag, snapshot in snapshots:
        for name, param in snapshot["parameters"].items():
            h = out.setdefault(name, {"states": [], "removed": [], "predecessors": []})
            last = h["states"][-1] if h["states"] else None
            continuing = previous is not None and name in previous[1]["parameters"]
            if continuing and last and not changes.compare(previous[1]["parameters"][name], param):
                last["to"] = tag
            else:
                h["states"].append({"from": tag, "to": tag, **state(param)})
        if previous is not None:
            old_tag, old = previous
            entries = facts.get((old_tag, tag), {}).get("removed", {})
            for name in sorted(set(old["parameters"]) - set(snapshot["parameters"])):
                entry = entries.get(name, {})
                out[name]["removed"].append({"in": tag, **{k: entry[k] for k in ("kind", "successors") if k in entry}})
                for successor in entry.get("successors", []):
                    out[successor]["predecessors"].append({"name": name, "in": tag, "kind": entry["kind"]})
        previous = (tag, snapshot)
    return out


def build(snapshots_dir: str, curated_dir: str) -> dict[str, dict]:
    snapshots = []
    for tag in extract.TRACKED:
        with open(os.path.join(snapshots_dir, f"{tag}.json"), encoding="utf-8") as f:
            snapshots.append((tag, json.load(f)))
    facts = {}
    for old, new in changes.pairs():
        if os.path.exists(curated.path(curated_dir, old, new)):
            facts[(old, new)] = curated.load(curated_dir, old, new)
    return histories(snapshots, facts)


def document(all_histories: dict[str, dict]) -> dict:
    return {"format": FORMAT, "parameters": dict(sorted(all_histories.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paramlineage.history", description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshots", default=os.path.join("data", "snapshots"), help="where the snapshots are (default: %(default)s)")
    parser.add_argument("--curated", default=os.path.join("data", "curated"), help="where the curated facts are (default: %(default)s)")
    parser.add_argument("--out", default=os.path.join("data", "params.json"), help="the file to write (default: %(default)s)")
    parser.add_argument("--check", action="store_true", help="compare with --out instead of writing it")
    parser.add_argument("--all", action="store_true", help="every parameter of the tracked releases")
    args = parser.parse_args(argv)
    if not args.all:
        parser.error("give --all")
    text = extract.dumps(document(build(args.snapshots, args.curated)))
    if args.check:
        try:
            with open(args.out, encoding="utf-8") as f:
                result = "same" if f.read() == text else "different"
        except FileNotFoundError:
            result = "missing"
        print(f"{args.out}: {result}")
        return 0 if result == "same" else 1
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"{args.out}: {len(json.loads(text)['parameters'])} parameters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
