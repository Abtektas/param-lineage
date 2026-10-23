# SPDX-License-Identifier: BSD-3-Clause
"""Checking a parameter file saved on one tracked release against a newer one.

The file format and the rules follow the upgrade check page (web/src/analyze.js): '#' lines are
comments, fields are split on tabs, spaces or commas, and a line has five fields (QGroundControl:
vehicle, component, name, value, type) or two (name, value). Only the autopilot's parameters
(component 1) are checked.
"""

from __future__ import annotations

import os
import re

from . import changes, curated, extract, query
from .translations import float32

AUTOPILOT_COMPONENT = 1
# MAVLink parameter types in a QGroundControl file
MAV_TYPES = {6: "Int32", 9: "Float"}
# Written by the firmware, not a setting
INTERNAL = {"_HASH_CHECK"}
LIMITS = [
    "Defaults are the parameter defaults of the release; an airframe's startup script can set others.",
    "Parameters with more instances on a board than in the release's metadata (PWM_MAIN_FUNC9 and up) are listed as instance.",
]


def family(name: str) -> str:
    """The name with instance numbers replaced, so PWM_MAIN_FUNC9 matches PWM_MAIN_FUNC1."""
    return re.sub(r"\d+", "#", name)


def parse(text: str) -> dict:
    header, rows, skipped = {}, [], []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            m = re.match(r"^#\s*(Stack|Vehicle|Version|Git Revision):\s*(.*)$", stripped)
            if m:
                header[m.group(1)] = m.group(2).strip()
            continue
        if not stripped:
            continue
        fields = re.split(r"[\t ,]+", stripped)
        if len(fields) == 5:
            rows.append({"line": number, "component": int(fields[1]), "name": fields[2], "text": fields[3],
                         "type": MAV_TYPES.get(int(fields[4]))})
        elif len(fields) == 2:
            rows.append({"line": number, "component": AUTOPILOT_COMPONENT, "name": fields[0], "text": fields[1], "type": None})
        else:
            skipped.append({"line": number, "text": stripped})
    for row in rows:
        try:
            row["value"] = float(row["text"])
        except ValueError:
            row["value"] = None
    return {"header": header, "rows": rows, "skipped": skipped}


def release_of(header: dict) -> str | None:
    """The tracked release a file's 'Version' header names, if any."""
    m = re.match(r"^(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\d+)?)", header.get("Version", ""))
    return f"v{m.group(1)}" if m and f"v{m.group(1)}" in extract.TRACKED else None


def same(a: float, b: float) -> bool:
    return float32(a) == float32(b)


def outside(value: float, low, high) -> bool:
    return (low is not None and float32(value) < float32(low)) or (high is not None and float32(value) > float32(high))


def notes(directory: str, old: str, new: str) -> dict[str, dict]:
    """The curated entries of the removals between two releases, by name."""
    out = {}
    lo, hi = extract.TRACKED.index(old), extract.TRACKED.index(new)
    for a, b in changes.pairs()[lo:hi]:
        if os.path.exists(curated.path(os.path.join(directory, "curated"), a, b)):
            for name, entry in curated.load(os.path.join(directory, "curated"), a, b)["removed"].items():
                out[name] = {**entry, "in": b}
    return out


def check(text: str, directory: str, old: str, new: str) -> dict:
    parsed = parse(text)
    histories = query.histories(directory)
    removals = query.diff(histories, old, new)["removed"]
    facts = notes(directory, old, new)
    families = {family(n) for n, h in histories.items() if query.state_at(h, new) is not None}
    findings = []
    rows = [r for r in parsed["rows"] if r["component"] == AUTOPILOT_COMPONENT]
    for row in rows:
        name, value = row["name"], row["value"]
        h = histories.get(name)
        a = query.state_at(h, old) if h else None
        b = query.state_at(h, new) if h else None
        finding = {"line": row["line"], "name": name, "value": row["text"]}
        if b is None:
            if name in removals:
                entry = facts.get(name, {})
                finding.update(kind="removed", removal=removals[name])
                if "note" in entry:
                    finding["note"] = entry["note"]
                if a is not None and value is not None and same(value, a["default"]):
                    finding["at_old_default"] = True
            elif name in INTERNAL:
                finding["kind"] = "internal"
            elif family(name) in families:
                finding["kind"] = "instance"
            else:
                finding["kind"] = "unknown"
            findings.append(finding)
            continue
        if value is None:
            findings.append({**finding, "kind": "unreadable"})
            continue
        if row["type"] and row["type"] != b["type"]:
            findings.append({**finding, "kind": "type-changed", "from": row["type"], "to": b["type"]})
        if a is not None and not same(a["default"], b["default"]) and same(value, a["default"]):
            findings.append({**finding, "kind": "reverts-default", "old_default": a["default"], "new_default": b["default"]})
        if outside(value, b.get("min"), b.get("max")) and not (a and outside(value, a.get("min"), a.get("max"))):
            findings.append({**finding, "kind": "out-of-range", "min": b.get("min"), "max": b.get("max")})
    named = release_of(parsed["header"])
    return {
        "from": old,
        "to": new,
        "file_release": named,
        "counts": {"rows": len(parsed["rows"]), "autopilot": len(rows), "skipped": len(parsed["skipped"])},
        "findings": findings,
        "limits": LIMITS,
    }
