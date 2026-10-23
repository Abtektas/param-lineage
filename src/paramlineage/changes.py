# SPDX-License-Identifier: BSD-3-Clause
"""Changes: what differs between the parameters of two consecutive tracked releases.

Made from the snapshots, and from the curated facts where a file exists for the pair
(docs/DESIGN.md, "4. Built views").

    python -m paramlineage.changes --all [--check]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import curated, extract
from .translations import float32

# The layout of a changes file. Changes when a field is added, renamed or removed.
FORMAT = 1
# The fields compared. Descriptions, group, category, decimal places, increment and volatile are not.
FIELDS = ["type", "default", "min", "max", "units", "rebootRequired", "values", "bitmask"]


def same_number(a, b, kind: str) -> bool:
    """Whether two values are the same as PX4 stores them: Float parameters as float32."""
    if a is None or b is None:
        return a is b
    return float32(a) == float32(b) if kind == "Float" else a == b


def labels(items: list[dict], key: str) -> dict:
    return {item[key]: item["description"] for item in items}


def keyed(old: dict, new: dict) -> dict:
    """The difference of two {key: description} maps."""
    out = {}
    added = {k: new[k] for k in sorted(set(new) - set(old))}
    removed = {k: old[k] for k in sorted(set(old) - set(new))}
    changed = {k: {"from": old[k], "to": new[k]} for k in sorted(set(old) & set(new)) if old[k] != new[k]}
    for name, part in (("added", added), ("removed", removed), ("changed", changed)):
        if part:
            out[name] = [{"key": k, **(v if name == "changed" else {"description": v})} for k, v in part.items()]
    return out


def compare(old: dict, new: dict) -> dict:
    """The fields of one parameter that differ between two releases."""
    out = {}
    kind = new["type"] if old["type"] == new["type"] else None
    for field in FIELDS:
        a, b = old.get(field), new.get(field)
        if field == "rebootRequired":
            a, b = bool(a), bool(b)  # a snapshot leaves it out when false
        if field in ("default", "min", "max"):
            if kind and same_number(a, b, kind) or not kind and a == b:
                continue
        elif field == "values":
            diff = keyed(labels(a or [], "value"), labels(b or [], "value"))
            if diff:
                out[field] = diff
            continue
        elif field == "bitmask":
            diff = keyed(labels(a or [], "index"), labels(b or [], "index"))
            if diff:
                out[field] = diff
            continue
        elif a == b:
            continue
        out[field] = {"from": a, "to": b}
    return out


def changes(old: dict, new: dict, facts: dict | None) -> dict:
    """The changes file of two consecutive snapshots, with the curated facts of the pair if any."""
    a, b = old["parameters"], new["parameters"]
    removed = {}
    for name in sorted(set(a) - set(b)):
        entry = (facts or {}).get("removed", {}).get(name)
        removed[name] = {k: entry[k] for k in ("kind", "successors") if k in entry} if entry else {}
    changed = {}
    for name in sorted(set(a) & set(b)):
        diff = compare(a[name], b[name])
        if diff:
            changed[name] = diff
    return {
        "format": FORMAT,
        "from": {"tag": old["source"]["tag"], "commit": old["source"]["commit"]},
        "to": {"tag": new["source"]["tag"], "commit": new["source"]["commit"]},
        "curated": facts["status"] if facts else "none",
        "added": sorted(set(b) - set(a)),
        "removed": removed,
        "changed": changed,
    }


def pairs() -> list[tuple[str, str]]:
    return list(zip(extract.TRACKED, extract.TRACKED[1:]))


def build(snapshots: str, curated_dir: str, old: str, new: str) -> dict:
    def snapshot(tag):
        with open(os.path.join(snapshots, f"{tag}.json"), encoding="utf-8") as f:
            return json.load(f)

    facts = curated.load(curated_dir, old, new) if os.path.exists(curated.path(curated_dir, old, new)) else None
    return changes(snapshot(old), snapshot(new), facts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m paramlineage.changes", description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshots", default=os.path.join("data", "snapshots"), help="where the snapshots are (default: %(default)s)")
    parser.add_argument("--curated", default=os.path.join("data", "curated"), help="where the curated facts are (default: %(default)s)")
    parser.add_argument("--out", default=os.path.join("data", "changes"), help="where the <from>..<to>.json files are (default: %(default)s)")
    parser.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing them")
    parser.add_argument("--all", action="store_true", help="every pair of consecutive tracked releases")
    args = parser.parse_args(argv)
    if not args.all:
        parser.error("give --all")
    failed = 0
    for old, new in pairs():
        text = extract.dumps(build(args.snapshots, args.curated, old, new))
        path = os.path.join(args.out, f"{old}..{new}.json")
        if args.check:
            try:
                with open(path, encoding="utf-8") as f:
                    result = "same" if f.read() == text else "different"
            except FileNotFoundError:
                result = "missing"
            print(f"{old}..{new}: {result}")
            failed += result != "same"
        else:
            os.makedirs(args.out, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            data = json.loads(text)
            print(f"{old}..{new}: {len(data['added'])} added, {len(data['removed'])} removed, {len(data['changed'])} changed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
