# SPDX-License-Identifier: BSD-3-Clause
"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys

from . import check as check_module
from . import legal, query


class _Version(argparse.Action):
    """Like argparse's version action, but the lines stay as they are."""

    def __call__(self, parser, namespace, values, option_string=None):
        print(legal.version_text())
        parser.exit()


# Every command that shows data ends with these, in text and in JSON.
TERMS = [legal.NO_WARRANTY, legal.INFORMATION_ONLY, legal.PX4_DATA]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="param-lineage",
        description="Parameter history for PX4: how parameters change between releases.",
        epilog=legal.INFORMATION_ONLY,
    )
    parser.add_argument(
        "--version", action=_Version, nargs=0, help="show the version and the terms in short, and exit"
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    commands.add_parser("license", help="print the full license texts")
    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--data", help="the data directory (default: the data installed with the program)")
    data.add_argument("--json", action="store_true", help="print JSON instead of text")
    history = commands.add_parser("history", parents=[data], help="how one parameter changed across the tracked releases")
    history.add_argument("name", help="a parameter name, such as MPC_HOLD_DZ")
    diff = commands.add_parser("diff", parents=[data], help="what changed between two tracked releases")
    diff.add_argument("old", help="the older release, such as v1.16.2")
    diff.add_argument("new", help="the newer release, such as v1.18.0-rc1")
    check = commands.add_parser("check", parents=[data], help="check a parameter file saved on one release against a newer one")
    check.add_argument("file", help="a .params file saved by QGroundControl")
    check.add_argument("--from", dest="old", help="the release the file was saved on (default: from the file's Version line)")
    check.add_argument("--to", dest="new", required=True, help="the release it will be loaded on")
    return parser


def value(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def removal_text(entry: dict) -> str:
    kind = entry.get("kind", "not curated")
    if entry.get("successors"):
        return f"{kind}: {', '.join(entry['successors'])}"
    return kind


def history_text(h: dict) -> list[str]:
    lines = [h["name"]]
    for s in h["states"]:
        span = s["from"] if s["from"] == s["to"] else f"{s['from']} to {s['to']}"
        fields = [s["type"], f"default {value(s['default'])}"]
        fields += [f"{k} {value(s[k])}" for k in ("min", "max", "units") if k in s]
        if s["rebootRequired"]:
            fields.append("reboot required")
        lines.append(f"  {span}: {', '.join(fields)}")
        for key, label in (("values", "value"), ("bitmask", "index")):
            for item in s.get(key, []):
                lines.append(f"      {item[label]}: {item['description']}")
    for r in h["removed"]:
        lines.append(f"  removed in {r['in']} ({removal_text(r)})")
    for p in h["predecessors"]:
        lines.append(f"  takes over from {p['name']} in {p['in']} ({p['kind']})")
    return lines


def diff_text(d: dict) -> list[str]:
    lines = [f"{d['from']} to {d['to']}: {len(d['added'])} added, {len(d['removed'])} removed, {len(d['changed'])} changed"]
    if d["removed"]:
        lines.append("Removed:")
        lines += [f"  {name} ({removal_text(e)})" for name, e in d["removed"].items()]
    if d["changed"]:
        lines.append("Changed:")
        for name, fields in d["changed"].items():
            parts = []
            for field, change in fields.items():
                if "from" in change:
                    parts.append(f"{field} {value(change['from'])} -> {value(change['to'])}")
                else:
                    parts.append(f"{field} " + ", ".join(f"{k} {len(v)}" for k, v in change.items()))
            lines.append(f"  {name}: {'; '.join(parts)}")
    if d["added"]:
        lines.append("Added:")
        lines += [f"  {name}" for name in d["added"]]
    return lines


MIGRATED = "PX4 converts it when it upgrades the stored parameters in place; loading this file does not."
CHECK_KINDS = [
    ("removed", "Not a parameter of {to}"),
    ("type-changed", "Type changed"),
    ("out-of-range", "Outside the range of {to}"),
    ("reverts-default", "Keeps the default of {from}, which {to} changed"),
    ("unreadable", "Value is not a number"),
    ("instance", "More instances than the metadata of {to} lists"),
    ("internal", "Written by the firmware"),
    ("unknown", "In neither release"),
]


def check_text(r: dict) -> list[str]:
    c = r["counts"]
    lines = [f"Checked {c['autopilot']} autopilot parameters saved on {r['from']} against {r['to']} "
             f"({c['rows'] - c['autopilot']} of other components, {c['skipped']} lines not read)."]
    if r["file_release"] and r["file_release"] != r["from"]:
        lines.append(f"The file says it was saved on {r['file_release']}, not {r['from']}.")
    for kind, title in CHECK_KINDS:
        found = [f for f in r["findings"] if f["kind"] == kind]
        if not found:
            continue
        lines.append(f"{title.format(**{'from': r['from'], 'to': r['to']})} ({len(found)}):")
        for f in found:
            detail = ""
            if kind == "removed":
                detail = removal_text(f["removal"]) + (", at the old default" if f.get("at_old_default") else "")
            elif kind == "type-changed":
                detail = f"{f['from']} -> {f['to']}"
            elif kind == "out-of-range":
                detail = f"min {value(f['min'])}, max {value(f['max'])}"
            elif kind == "reverts-default":
                detail = f"{value(f['old_default'])} -> {value(f['new_default'])}"
            lines.append(f"  {f['name']} = {f['value']}" + (f" ({detail})" if detail else ""))
            if kind == "removed" and f["removal"].get("kind") == "migrated":
                lines.append(f"      {MIGRATED}")
            if f.get("note"):
                lines.append(f"      {f['note']}")
    if not r["findings"]:
        lines.append("Nothing found.")
    lines += [""] + r["limits"]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "license":
        print(legal.license_text())
        return 0
    if args.command in ("history", "diff", "check"):
        try:
            directory = query.data_dir(args.data)
            if args.command == "history":
                result = query.history(directory, args.name)
                lines = history_text(result)
            elif args.command == "diff":
                result = query.diff(query.histories(directory), query.tag(args.old), query.tag(args.new))
                lines = diff_text(result)
            else:
                try:
                    with open(args.file, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError as e:
                    raise query.DataError(f"cannot read {args.file}: {e.strerror}") from None
                old = args.old or check_module.release_of(check_module.parse(text)["header"])
                if not old:
                    raise query.DataError("the file does not name a tracked release; give --from")
                result = check_module.check(text, directory, query.tag(old), query.tag(args.new))
                lines = check_text(result)
        except query.DataError as e:
            print(f"param-lineage: {e}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({**result, "terms": TERMS}, indent=1, ensure_ascii=False))
        else:
            print("\n".join(lines + [""] + TERMS))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
