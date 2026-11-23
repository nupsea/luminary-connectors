"""The bundles this connector writes, byte for byte, so a refactor that changes one fails here.
Regenerate only for a change meant to alter them: GOLDEN_UPDATE=1 uv run pytest."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from luminary_source_sdk.testing import run
from test_confluence import ENTRY, wiki  # noqa: F401 -- the fixture

GOLDEN = Path(__file__).parent / "golden"
_TEXT = (".json", ".html", ".md", ".vtt")


def _snapshot(bundle: Path, base: str) -> dict:
    """Every file the fetch wrote; text with the test server's address made stable."""
    out: dict = {}
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        rel, data = path.relative_to(bundle).as_posix(), path.read_bytes()
        if rel.endswith(_TEXT):
            out[rel] = data.decode("utf-8").replace(base, "BASE/")
        else:
            out[rel] = "sha256:" + hashlib.sha256(data).hexdigest()
    return out


def _matches_golden(name: str, snapshot: dict) -> None:
    path = GOLDEN / f"{name}.json"
    if os.environ.get("GOLDEN_UPDATE"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == snapshot


def test_the_bundle_is_unchanged(wiki, tmp_path):  # noqa: F811
    base, _ = wiki
    url = base + "spaces/SIG/pages/1/Special+Interest+Groups"
    events = run(ENTRY, "fetch", input={"url": url}, dest=tmp_path / "b")
    assert events[-1]["event"] == "result", events[-1]
    root = base.removesuffix("wiki/")
    _matches_golden("subtree", _snapshot(tmp_path / "b", root))
