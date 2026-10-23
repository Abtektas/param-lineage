# SPDX-License-Identifier: BSD-3-Clause
"""Reading the data: the parameter histories, the curated facts and the translations, as installed
with the package or from a checkout of this repository."""

from __future__ import annotations

import json
import os

from . import changes, extract

HERE = os.path.dirname(os.path.abspath(__file__))
# Installed: the wheel carries the data inside the package. From a checkout: the repository's data/.
CANDIDATES = [os.path.join(HERE, "data"), os.path.join(os.path.dirname(os.path.dirname(HERE)), "data")]


class DataError(Exception):
    pass


def data_dir(given: str | None = None) -> str:
    for directory in [given] if given else CANDIDATES:
        if directory and os.path.isfile(os.path.join(directory, "params.json")):
            return directory
    raise DataError(f"no data found in {given or ' or '.join(CANDIDATES)}")


def tag(name: str) -> str:
    if name not in extract.TRACKED:
        raise DataError(f"{name} is not a tracked release; the tracked releases are {', '.join(extract.TRACKED)}")
    return name


def histories(directory: str) -> dict[str, dict]:
    with open(os.path.join(directory, "params.json"), encoding="utf-8") as f:
        return json.load(f)["parameters"]


def history(directory: str, name: str) -> dict:
    try:
        return {"name": name, **histories(directory)[name]}
    except KeyError:
        raise DataError(f"{name} is not a parameter of any tracked release") from None


def state_at(h: dict, at: str) -> dict | None:
    """The state of a parameter in a tracked release, or None if the release does not have it."""
    i = extract.TRACKED.index(at)
    for s in h["states"]:
        if extract.TRACKED.index(s["from"]) <= i <= extract.TRACKED.index(s["to"]):
            return {k: v for k, v in s.items() if k not in ("from", "to")}
    return None


def successors_at(all_histories: dict[str, dict], name: str, old: str, new: str) -> list[str]:
    """The parameters of ``new`` that take over from ``name`` after ``old``, following the curated
    successors through releases in between, in the order the curated facts give them."""
    lo, hi = extract.TRACKED.index(old), extract.TRACKED.index(new)
    out: list[str] = []
    seen = set()

    def follow(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        for removal in all_histories[current]["removed"]:
            if lo < extract.TRACKED.index(removal["in"]) <= hi:
                for s in removal.get("successors", []):
                    if state_at(all_histories[s], new) is None:
                        follow(s)
                    elif s not in out:
                        out.append(s)

    follow(name)
    return out


def diff(all_histories: dict[str, dict], old: str, new: str) -> dict:
    """What differs between two tracked releases, in the layout of the changes files."""
    if extract.TRACKED.index(old) >= extract.TRACKED.index(new):
        raise DataError(f"{old} is not older than {new}")
    lo, hi = extract.TRACKED.index(old), extract.TRACKED.index(new)
    added, removed, changed = [], {}, {}
    for name in sorted(all_histories):
        h = all_histories[name]
        a, b = state_at(h, old), state_at(h, new)
        if a is None and b is not None:
            added.append(name)
        elif a is not None and b is None:
            steps = [r for r in h["removed"] if lo < extract.TRACKED.index(r["in"]) <= hi]
            entry = {k: steps[-1][k] for k in ("kind",) if k in steps[-1]}
            successors = successors_at(all_histories, name, old, new)
            if successors:
                entry["successors"] = successors
            removed[name] = entry
        elif a is not None:
            d = changes.compare(a, b)
            if d:
                changed[name] = d
    return {"from": old, "to": new, "added": added, "removed": removed, "changed": changed}
