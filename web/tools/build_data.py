"""Build the checker's data from this repository's data for two tracked PX4 releases.

usage: build_data.py <PX4 git repository> <from tag> <to tag> <output .json>

It reads the snapshots of both tags, the curated facts and the changes of the pair, and the
page's own rules in tools/hints_<from>_to_<to>.py. The PX4 repository is read only for the
startup scripts of the airframes. The build stops if the facts and the rules do not match
exactly, so a new release cannot silently lose a removed parameter.
"""
import importlib
import json
import math
import os
import re
import struct
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(TOOLS)), "data")
sys.path.insert(0, TOOLS)

TYPES = {"Int32": "i", "Float": "f"}


def read(*path):
    with open(os.path.join(DATA, *path), encoding="utf-8") as f:
        return json.load(f)


def hints(src_tag, dst_tag):
    def short(tag):
        return re.sub(r"^v(\d+)\.(\d+)\..*", r"v\1_\2", tag)
    return importlib.import_module(f"hints_{short(src_tag)}_to_{short(dst_tag)}")


def compact(p):
    out = {"t": TYPES[p["type"]], "d": p.get("default"), "s": p.get("shortDesc", "")}
    for key, short in (("min", "min"), ("max", "max"), ("units", "u")):
        if key in p:
            out[short] = p[key]
    if p.get("rebootRequired"):
        out["r"] = 1
    if p.get("volatile"):
        out["vol"] = 1
    if p.get("values"):
        out["v"] = [[v["value"], v["description"]] for v in p["values"]]
    if p.get("bitmask"):
        out["b"] = [[b["index"], b["description"]] for b in p["bitmask"]]
    return out


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


ROMFS = "ROMFS/px4fmu_common"
MISSING = set()  # scripts an airframe includes that do not exist in that release
SET_DEFAULT = re.compile(r"^param\s+set-default\s+(?:-s\s+)?([A-Z0-9_]+)\s+(\S+)")
INCLUDE = re.compile(r"^\.\s+\$\{R\}etc/init\.d/(\S+)")


def script_defaults(repo, tag, path, out, seen):
    """Apply the unconditional 'param set-default' lines of a startup script, following its
    '. ${R}etc/init.d/...' includes in order. Lines inside if/fi blocks are skipped: they
    depend on the vehicle's state, so they cannot be decided here."""
    if path in seen:
        return
    seen.add(path)
    try:
        text = git(repo, "show", f"{tag}:{path}")
    except subprocess.CalledProcessError:
        MISSING.add(f"{tag}:{path}")
        return
    depth = 0
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if re.match(r"^if\b", line):
            depth += 1
        elif line == "fi":
            depth -= 1
        elif depth == 0 and (m := SET_DEFAULT.match(line)):
            out[m.group(1)] = float(m.group(2))
        elif depth == 0 and (m := INCLUDE.match(line)):
            script_defaults(repo, tag, f"{ROMFS}/init.d/{m.group(1)}", out, seen)


def airframes(repo, tag):
    """{SYS_AUTOSTART: (file name, {param: default set by the startup scripts})}

    Some SITL airframes reuse a hardware airframe's number (4001 is quad_x on hardware and
    gz_x500 in SITL); the hardware one is kept, as saved files come from real vehicles."""
    result = {}
    for directory in ("init.d-posix", "init.d"):
        base = {}
        if directory == "init.d-posix":
            script_defaults(repo, tag, f"{ROMFS}/{directory}/rcS", base, set())
        for name in git(repo, "ls-tree", "--name-only", f"{tag}:{ROMFS}/{directory}/airframes").split():
            m = re.match(r"^(\d+)_", name)
            if not m:
                continue
            defaults = dict(base)
            script_defaults(repo, tag, f"{ROMFS}/{directory}/airframes/{name}", defaults, set())
            result[int(m.group(1))] = (name, defaults)
    return result


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def airframe_changes(repo, src_tag, dst_tag, src, dst):
    """For each airframe, the parameters whose effective default (startup scripts, else
    metadata) differs between the releases."""
    old, new = airframes(repo, src_tag), airframes(repo, dst_tag)
    out = {}
    for autostart, (name, old_defaults) in sorted(old.items()):
        if autostart not in new:
            out[autostart] = {"name": name, "removed": True}
            continue
        new_name, new_defaults = new[autostart]
        changes = {}
        for param in sorted(set(src) & set(dst)):
            a = old_defaults.get(param, src[param].get("default"))
            b = new_defaults.get(param, dst[param].get("default"))
            if a is not None and b is not None and not math.isclose(f32(a), f32(b), rel_tol=0, abs_tol=0):
                changes[param] = [a, b]
        out[autostart] = {"name": new_name, "changes": changes}
    return out


def main():
    repo, src_tag, dst_tag, out_path = sys.argv[1:]
    src_snapshot, dst_snapshot = read("snapshots", f"{src_tag}.json"), read("snapshots", f"{dst_tag}.json")
    src, dst = src_snapshot["parameters"], dst_snapshot["parameters"]
    pair = f"{src_tag}..{dst_tag}.json"
    curated, changes = read("curated", pair), read("changes", pair)
    page = hints(src_tag, dst_tag)

    removed = set(src) - set(dst)
    errors = []
    if curated["status"] != "complete":
        errors.append(f"the curated facts of {pair} are {curated['status']}")
    if set(curated["removed"]) != removed:
        errors.append(f"curated without removal: {sorted(set(curated['removed']) - removed)}")
        errors.append(f"removals without curated facts: {sorted(removed - set(curated['removed']))}")
    errors += [f"rule for {n}, which is not removed" for n in sorted(set(page.RULES) - removed)]
    for name, fact in sorted(curated["removed"].items()):
        rule = page.RULES.get(name)
        converts = rule is not None and rule["type"] in page.CONVERSIONS
        if (fact["kind"] == "migrated") != converts:
            errors.append(f"{name}: kind {fact['kind']} with rule {rule}")
        if rule is None:
            continue
        to = rule.get("to", [])
        targets = (to if isinstance(to, list) else [to]) + [rule[k] for k in ("max", "min") if k in rule] + list(rule.get("also", {}))
        errors += [f"{name}: {t} is not a {dst_tag} parameter" for t in targets if t not in dst]
        if converts and set(targets) != set(fact["successors"]):
            errors.append(f"{name}: the rule writes {sorted(targets)}, the successors are {fact['successors']}")
    type_changed = {n for n, c in changes["changed"].items() if "type" in c}
    if set(page.TYPE_RULES) != type_changed:
        errors.append(f"type rules {sorted(set(page.TYPE_RULES) ^ type_changed)} do not match the type changes")
    if errors:
        sys.exit("\n".join(errors))

    # the curated entry as it is, and the page's rule for it
    notes = {n: {**fact, **({"rule": page.RULES[n]} if n in page.RULES else {})}
             for n, fact in sorted(curated["removed"].items())}
    commits = {}
    for tag, snapshot in ((src_tag, src_snapshot), (dst_tag, dst_snapshot)):
        commit = git(repo, "rev-parse", f"{tag}^{{commit}}").strip()
        if commit != snapshot["source"]["commit"]:
            sys.exit(f"{tag} is {commit} in {repo}, but the snapshot was made from {snapshot['source']['commit']}")
        commits[tag] = commit[:10]
    data = {
        "from": {"tag": src_tag, "commit": commits[src_tag]},
        "to": {"tag": dst_tag, "commit": commits[dst_tag]},
        # [type, default, min, max]: the old range tells a value that only the new range rejects
        "source": {n: [TYPES[p["type"]], p.get("default"), p.get("min"), p.get("max")] for n, p in sorted(src.items())},
        "removedMeta": {n: compact(src[n]) for n in sorted(removed)},
        "target": {n: compact(p) for n, p in sorted(dst.items())},
        "notes": notes,
        "typeRules": page.TYPE_RULES,
        "airframes": airframe_changes(repo, src_tag, dst_tag, src, dst),
    }
    with open(out_path, "w") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)
    for path in sorted(MISSING):
        print(f"note: included script not found, skipped: {path}")
    print(f"{src_tag} {len(src)} -> {dst_tag} {len(dst)}: {len(removed)} removed, "
          f"{len(type_changed)} type changes, wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main()
