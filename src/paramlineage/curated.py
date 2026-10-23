# SPDX-License-Identifier: BSD-3-Clause
"""Curated facts: what happened to each parameter a release removed (data/curated/<from>..<to>.json).

The files are written by hand. This module checks them against the snapshots and, given a PX4
repository, against the commits they cite.
"""

from __future__ import annotations

import json
import os
import subprocess

from . import extract


def path(directory: str, old: str, new: str) -> str:
    return os.path.join(directory, f"{old}..{new}.json")


def load(directory: str, old: str, new: str) -> dict:
    with open(path(directory, old, new), encoding="utf-8") as f:
        return json.load(f)


def problems(data: dict, old: dict, new: dict) -> list[str]:
    """What is wrong with a curated file, given the snapshots of its two releases."""
    out = []
    removed = set(old["parameters"]) - set(new["parameters"])
    for name, entry in sorted(data["removed"].items()):
        if name not in old["parameters"]:
            out.append(f"{name}: not a parameter of {data['from']}")
        elif name in new["parameters"]:
            out.append(f"{name}: still a parameter of {data['to']}")
        for successor in entry.get("successors", []):
            if successor not in new["parameters"]:
                out.append(f"{name}: successor {successor} is not a parameter of {data['to']}")
    if data["status"] == "complete":
        out += [f"{name}: removed in {data['to']} but not listed" for name in sorted(removed - set(data["removed"]))]
    elif data["status"] == "not-started" and data["removed"]:
        out.append("status is not-started, but entries are listed")
    return out


def converted_to(cases: list[dict], name: str) -> set[str]:
    """The parameters a translation passes a stored value of ``name`` on to, for any probe."""
    out = set()
    for case in cases:
        outcome = case["outcome"]
        if outcome["result"] == "stored" and outcome["name"] != name:
            out.add(outcome["name"])
        out |= set(outcome.get("also_set", {}))
    return out


def translation_problems(data: dict, translations: dict) -> list[str]:
    """Entries that disagree with the translations of 'to': an entry is migrated exactly when the
    translation code passes the value on, and then only to its successors."""
    out = []
    for name, entry in sorted(data["removed"].items()):
        to = converted_to(translations["parameters"].get(name, []), name)
        successors = set(entry.get("successors", []))
        if entry["kind"] == "migrated" and not to:
            out.append(f"{name}: migrated, but {data['to']} does not convert it")
        elif entry["kind"] != "migrated" and to:
            out.append(f"{name}: {entry['kind']}, but {data['to']} converts it to {', '.join(sorted(to))}")
        elif to - successors:
            out.append(f"{name}: converted to {', '.join(sorted(to - successors))}, which are not its successors")
    return out


def commit_problems(repo: str, data: dict) -> list[str]:
    """Entries whose commit is not in the history between the two releases of a PX4 repository."""
    def ancestor(commit: str, tag: str) -> bool:
        return subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", commit, tag],
                              capture_output=True).returncode == 0

    out = []
    for commit in sorted({e["commit"] for e in data["removed"].values()}):
        try:
            extract.git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
        except extract.ExtractError:
            out.append(f"{commit}: not in the repository")
            continue
        if not ancestor(commit, data["to"]) or ancestor(commit, data["from"]):
            out.append(f"{commit}: not between {data['from']} and {data['to']}")
    return out
