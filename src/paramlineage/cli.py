# SPDX-License-Identifier: BSD-3-Clause
"""Command line entry point."""

from __future__ import annotations

import argparse
import sys

from . import legal


class _Version(argparse.Action):
    """Like argparse's version action, but the lines stay as they are."""

    def __call__(self, parser, namespace, values, option_string=None):
        print(legal.version_text())
        parser.exit()


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
    # The data commands (history, diff, check) arrive with the data; see docs/DESIGN.md.
    commands.add_parser("license", help="print the full license texts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "license":
        print(legal.license_text())
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
