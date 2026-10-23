# SPDX-License-Identifier: BSD-3-Clause
"""Write the parameter list of an official PX4 firmware build, for test_snapshots.py.

    python3 make_list.py <file.px4 or parameters.xml> <URL it was downloaded from> <out.txt>

A .px4 file embeds the parameters.xml of its build together with the git commit it was built
from. A parameters.xml alone does not say which commit it was built from; the list says so.
"""

import base64
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zlib


def main(path: str, url: str, out: str) -> None:
    with open(path, "rb") as f:
        raw = f.read()
    if path.endswith(".px4"):
        firmware = json.loads(raw)
        xml = zlib.decompress(base64.b64decode(firmware["parameter_xml"]))
        built_from = f"{firmware['git_identity']} {firmware['git_hash']}"
    else:
        xml = raw
        built_from = "not recorded in the file"
    lines = [
        f"# url: {url}",
        f"# sha256: {hashlib.sha256(raw).hexdigest()}",
        f"# built from: {built_from}",
        "# Parameter data of PX4, BSD-3-Clause, see LICENSE-THIRD-PARTY.",
        "# name type default",
    ]
    params = sorted((p.get("name"), p.get("type"), p.get("default")) for p in ET.fromstring(xml).iter("parameter"))
    lines += [" ".join(p) for p in params]
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
