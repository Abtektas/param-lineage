# SPDX-License-Identifier: BSD-3-Clause
"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys

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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "license":
        print(legal.license_text())
        return 0
    if args.command in ("history", "diff"):
        try:
            directory = query.data_dir(args.data)
            if args.command == "history":
                result = query.history(directory, args.name)
                lines = history_text(result)
            else:
                result = query.diff(query.histories(directory), query.tag(args.old), query.tag(args.new))
                lines = diff_text(result)
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
