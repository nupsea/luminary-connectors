"""Every connector builds on one SDK commit, and docs/protocol.md is the contract at that commit.

Standard library only; CI runs it with `python scripts/check_contract.py`. A connector pinned to
another commit, or a protocol.md that drifted from the core's docs/connectors.md, fails here.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PIN = re.compile(r"github\.com/nupsea/luminary/archive/([0-9a-f]{40})\.tar\.gz")


def pins() -> dict[str, str]:
    found = {}
    for pyproject in sorted(ROOT.glob("*/pyproject.toml")):
        match = _PIN.search(pyproject.read_text(encoding="utf-8"))
        if match:
            found[pyproject.parent.name] = match.group(1)
    return found


def main() -> int:
    found = pins()
    commits = set(found.values())
    if len(commits) != 1:
        print(f"FAIL connectors pin different SDK commits: {found}")
        return 1
    (sha,) = commits
    url = f"https://raw.githubusercontent.com/nupsea/luminary/{sha}/docs/connectors.md"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 -- a fixed https host
        upstream = resp.read().decode("utf-8")
    local = (ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
    if local != upstream:
        print(f"FAIL docs/protocol.md differs from docs/connectors.md at {sha}; copy it again")
        return 1
    print(f"contract ok: {len(found)} connectors on SDK commit {sha[:12]}, protocol.md matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
