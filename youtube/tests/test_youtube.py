"""The YouTube connector: what it asks yt-dlp for, and the bundle it hands Luminary.

yt-dlp is faked at the subprocess boundary, so no test reaches YouTube.
"""

from __future__ import annotations

import io
import json
import subprocess
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest
from luminary_source_sdk.testing import run

from luminary_youtube import URL_PREFIXES, ytdlp

ENTRY = "luminary_youtube:YouTube"
URL = "https://www.youtube.com/watch?v=t1"
FFMPEG = str(Path("/opt/homebrew/bin") / "ffmpeg")
META = {
    "id": "t1",
    "title": "Building RAG pipelines on your laptop",
    "uploader": "DataEngBytes",
    "tags": ["vector search", "LanceDB", "x" * 101],
    "chapters": [{"title": "Intro"}, {"title": ""}, {"title": "Why Kimi K3 changes the cost"}],
    "description": "Recorded at DataEngBytes 2025.",
    "language": "en",
    "subtitles": {"en": [], "live_chat": []},
}
VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nWe store vectors in LanceDB\n"


class _Popen:
    """yt-dlp's download: progress lines on stdout, the audio file written, then exit."""

    def __init__(self, argv, stdout, stderr, *, lines=b"", returncode=0, error=b""):
        self.argv = argv
        self.stdout = io.BytesIO(lines)
        self._returncode = returncode
        self.returncode = None
        stderr.write(error)
        if returncode == 0:
            stem = argv[argv.index("-o") + 1].removesuffix(".%(ext)s")
            Path(stem + ".flac").write_bytes(b"fLaC audio")

    def wait(self):
        self.returncode = self._returncode
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        pass


@pytest.fixture
def yt(monkeypatch):
    """Answers metadata and caption requests; records every argv."""
    calls: list[list[str]] = []
    state = {"meta": META, "popen": {}, "captions": True}

    def _run(argv, **kwargs):
        calls.append(argv)
        if "--dump-json" in argv:
            return subprocess.CompletedProcess(argv, 0, json.dumps(state["meta"]).encode(), b"")
        stem = argv[argv.index("-o") + 1].removesuffix(".%(ext)s")
        track = next(a.split("=", 1)[1] for a in argv if a.startswith("--sub-langs="))
        if state["captions"]:
            Path(f"{stem}.{track}.vtt").write_text(VTT, encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    def _popen(argv, stdout, stderr):
        calls.append(argv)
        return _Popen(argv, stdout, stderr, **state["popen"])

    monkeypatch.setattr(ytdlp.subprocess, "run", _run)
    monkeypatch.setattr(ytdlp.subprocess, "Popen", _popen)
    state["calls"] = calls
    return state


def _download_argv(calls):
    return next(c for c in calls if "-x" in c)


def test_describe_declares_what_luminary_checks_before_fetching():
    (event,) = run(ENTRY, "describe")
    data = event["data"]
    assert (data["name"], data["label"], data["media"], data["tools"]) == (
        "youtube", "YouTube", ["youtube"], ["ffmpeg"],
    )  # fmt: skip
    assert data["terms"]["url"] == "https://www.youtube.com/t/terms"
    assert "expressly authorized by the Service" in data["terms"]["statement"]
    assert "any automated means" in data["terms"]["statement"]


@pytest.mark.parametrize(
    ("url", "claimed"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://youtu.be/dQw4w9WgXcQ", True),
        ("https://vimeo.com/123456", False),
        ("https://example.com/youtube.com/watch", False),
    ],
)
def test_links_are_claimed_by_prefix(url, claimed):
    assert any(url.startswith(p) for p in URL_PREFIXES) is claimed


def test_a_fetch_writes_a_bundle_the_published_schema_accepts(yt, tmp_path):
    events = run(ENTRY, "fetch", input={"url": URL, "tools": {"ffmpeg": FFMPEG}}, dest=tmp_path)

    assert events[-1]["event"] == "result", events[-1]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((files("luminary_source_sdk") / "source-bundle.schema.json").read_text())
    jsonschema.validate(manifest, schema)
    assert manifest["media"] == {
        "kind": "youtube", "url": URL, "audio": "assets/audio.flac", "captions": "assets/captions.vtt",
    }  # fmt: skip
    assert (manifest["title"], manifest["authors"], manifest["locator"]) == (
        META["title"], ["DataEngBytes"], "t1",
    )  # fmt: skip
    # A tag or chapter the manifest would refuse is dropped, not the whole bundle.
    assert manifest["tags"] == ["vector search", "LanceDB"]
    assert manifest["chapters"] == ["Intro", "Why Kimi K3 changes the cost"]
    assert manifest["description"] == META["description"]
    assert (tmp_path / "assets" / "captions.vtt").read_text(encoding="utf-8") == VTT
    assert sorted(p.name for p in tmp_path.iterdir()) == ["assets", "manifest.json"]


def test_the_download_passes_the_ffmpeg_luminary_found(yt, tmp_path):
    """yt-dlp looks on its own PATH, not where Luminary found ffmpeg; the directory is passed
    because postprocessing needs the ffprobe beside it."""
    run(ENTRY, "fetch", input={"url": URL, "tools": {"ffmpeg": FFMPEG}}, dest=tmp_path)
    argv = _download_argv(yt["calls"])
    assert argv[argv.index("--ffmpeg-location") + 1] == str(Path(FFMPEG).parent)


def test_without_ffmpeg_the_flag_is_omitted(yt, tmp_path):
    """An empty --ffmpeg-location is worse than none: yt-dlp would take it."""
    run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    assert "--ffmpeg-location" not in _download_argv(yt["calls"])


def test_the_download_keeps_16_bit_flac(yt, tmp_path):
    """FLAC is lossless against the WAV it replaces only at 16 bits: ffmpeg's default for
    decoded Opus is 24-bit, whose samples differ."""
    run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    argv = _download_argv(yt["calls"])
    assert argv[argv.index("--audio-format") + 1] == "flac"
    assert argv[argv.index("--postprocessor-args") + 1] == "ExtractAudio:-sample_fmt s16"


def test_every_yt_dlp_call_ends_option_parsing_before_the_url(yt, tmp_path):
    run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    assert len(yt["calls"]) == 3
    assert all(argv[-2:] == ["--", URL] for argv in yt["calls"])


def test_download_reports_progress(yt, tmp_path):
    yt["popen"] = {"lines": (
        b"luminary-progress 250 1000 NA\n"
        b"luminary-progress 500 NA 2000\n"  # no total yet: the estimate stands in
        b"luminary-progress 700 NA NA\n"  # neither: nothing to report
        b"[ExtractAudio] Destination: out.flac\n"
        b"luminary-progress 1000 1000 NA\n"
    )}  # fmt: skip
    events = run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    progress = [e["fraction"] for e in events if e["event"] == "progress"]
    assert progress == [0.25, 0.25, 1.0]


def test_a_failed_download_names_yt_dlps_reason(yt, tmp_path):
    yt["popen"] = {"returncode": 1, "error": b"ERROR: [youtube] t1: Video unavailable\n"}
    events = run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    assert events[-1] == {
        "event": "error", "code": "source",
        "message": "yt-dlp download failed (exit 1): [youtube] t1: Video unavailable",
    }  # fmt: skip
    assert not (tmp_path / "manifest.json").exists()


def test_a_metadata_failure_names_yt_dlps_reason(monkeypatch, tmp_path):
    def _run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, b"", (
            b"WARNING: [youtube] x: HTTP Error 429: Too Many Requests\n"
            b"ERROR: [youtube] x: Sign in to confirm you\xe2\x80\x99re not a bot. Use --cookies\n"
        ))  # fmt: skip

    monkeypatch.setattr(ytdlp.subprocess, "run", _run)
    events = run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    assert events[-1]["message"] == (
        "YouTube could not be read: [youtube] x: Sign in to confirm you’re not a bot"
    )


@pytest.mark.parametrize("arrives", [False, None], ids=["track-download-fails", "no-track"])
def test_without_captions_the_audio_alone_is_bundled(yt, tmp_path, arrives):
    if arrives is None:
        yt["meta"] = {**META, "subtitles": {}}
    else:
        yt["captions"] = arrives
    events = run(ENTRY, "fetch", input={"url": URL}, dest=tmp_path)
    assert events[-1]["event"] == "result", events[-1]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "captions" not in manifest["media"]
    assert [p.name for p in (tmp_path / "assets").iterdir()] == ["audio.flac"]
    assert len(yt["calls"]) == (2 if arrives is None else 3)


def test_only_an_uploaded_track_in_the_spoken_language_is_used():
    meta = {
        "language": "en",
        "subtitles": {"live_chat": [], "fr": [], "en-GB": []},
        "automatic_captions": {"en": []},
    }
    pick = ytdlp.uploader_caption_language
    assert pick(meta) == "en-GB"
    assert pick({**meta, "subtitles": {"en": [], "en-GB": []}}) == "en"
    # YouTube's own recognition, a translation, or an undeclared language: Whisper instead.
    assert pick({**meta, "subtitles": {}}) is None
    assert pick({**meta, "subtitles": {"fr": []}}) is None
    assert pick({**meta, "language": None}) is None
    assert pick({**meta, "subtitles": {"-x": []}, "language": "-x"}) is None


def test_a_link_that_is_not_a_video_is_refused_before_yt_dlp_runs(yt, tmp_path):
    events = run(ENTRY, "fetch", input={"url": "-o/etc/passwd"}, dest=tmp_path)
    assert events[-1]["code"] == "input"
    assert yt["calls"] == []


def test_preview_offers_the_uploaded_tracks_and_speech_recognition(yt):
    yt["meta"] = {**META, "subtitles": {"en": [], "fr": [], "live_chat": []},
                  "automatic_captions": {"de": []}}  # fmt: skip
    data = run(ENTRY, "preview", input={"url": URL})[-1]["data"]
    (choice,) = data["choices"]
    assert (data["title"], data["detail"]) == (META["title"], "DataEngBytes")
    assert [o["value"] for o in choice["options"]] == ["en", "fr", "transcribe"]
    assert (choice["field"], choice["multiple"], choice["default"]) == ("captions", False, ["en"])
    yt["meta"] = {**META, "subtitles": {}}
    assert run(ENTRY, "preview", input={"url": URL})[-1]["data"]["choices"][0]["default"] == [
        "transcribe"
    ]


@pytest.mark.parametrize(
    ("chosen", "captions_file"),
    [("transcribe", None), (["fr"], "fr"), (None, "en")],
    ids=["speech-chosen", "other-track-chosen", "no-choice"],
)
def test_the_chosen_transcript_is_the_one_fetched(yt, tmp_path, chosen, captions_file):
    yt["meta"] = {**META, "subtitles": {"en": [], "fr": []}}
    inp = {"url": URL} | ({"captions": chosen} if chosen is not None else {})
    assert run(ENTRY, "fetch", input=inp, dest=tmp_path)[-1]["event"] == "result"
    asked = [a.split("=", 1)[1] for c in yt["calls"] for a in c if a.startswith("--sub-langs=")]
    assert asked == ([captions_file] if captions_file else [])
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert ("captions" in manifest["media"]) is bool(captions_file)


def test_a_track_the_video_lacks_is_refused_before_downloading(yt, tmp_path):
    events = run(ENTRY, "fetch", input={"url": URL, "captions": "xx"}, dest=tmp_path)
    assert (events[-1]["code"], len(yt["calls"])) == ("input", 1), "metadata only"
