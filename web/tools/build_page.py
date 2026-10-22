"""Inline the data and the checker into one self-contained HTML file.

usage: build_page.py <data .json> <output .html>
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)  # the license files live at the repository root


def script_safe(text):
    # nothing inside a <script> element may close it
    return text.replace("</", "<\\/")


def main():
    data_path, out_path = sys.argv[1:]
    page = open(os.path.join(ROOT, "src", "page.html")).read()
    analyze = open(os.path.join(ROOT, "src", "analyze.js")).read()
    data = open(data_path).read()
    # the terms travel with the page: both license texts are part of it
    licenses = json.dumps({
        "project": open(os.path.join(REPO, "LICENSE")).read(),
        "px4": open(os.path.join(REPO, "LICENSE-THIRD-PARTY")).read(),
    })
    for marker in ("/*__ANALYZE__*/", "/*__DATA__*/null", "/*__LICENSES__*/null"):
        assert page.count(marker) == 1, marker
    page = page.replace("/*__ANALYZE__*/", script_safe(analyze)).replace("/*__DATA__*/null", script_safe(data))
    page = page.replace("/*__LICENSES__*/null", script_safe(licenses))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(page)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main()
