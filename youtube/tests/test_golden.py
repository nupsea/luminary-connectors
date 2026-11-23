"""The bundle this connector writes, byte for byte, so a refactor that changes it fails here.
Regenerate only for a change meant to alter it: GOLDEN_UPDATE=1 uv run pytest."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from luminary_source_sdk.testing import run
from test_youtube import ENTRY, FFMPEG, URL, yt  # noqa: F401 -- the fixture

GOLDEN = Path(__file__).parent / "golden"
_TEXT = (".json", ".html", ".md", ".vtt")


def _snapshot(bundle: Path) -> dict:
    """Every file the fetch wrote; binary files by their hash."""
    out: dict = {}
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        rel, data = path.relative_to(bundle).as_posix(), path.read_bytes()
        if rel.endswith(_TEXT):
            # On Windows the fixtures and the bundle carry \r\n; the core reads either.
            out[rel] = data.decode("utf-8").replace("\r", "")
        else:
            out[rel] = "sha256:" + hashlib.sha256(data).hexdigest()
    return out


def _matches_golden(name: str, snapshot: dict) -> None:
    path = GOLDEN / f"{name}.json"
    if os.environ.get("GOLDEN_UPDATE"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == snapshot


def test_the_bundle_is_unchanged(yt, tmp_path):  # noqa: F811
    events = run(ENTRY, "fetch", input={"url": URL, "tools": {"ffmpeg": FFMPEG}}, dest=tmp_path)
    assert events[-1]["event"] == "result", events[-1]
    _matches_golden("talk", _snapshot(tmp_path))
