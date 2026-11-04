"""yt-dlp, run as a module of this connector's own interpreter, one subprocess per step."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

# Lossless and 16-bit, so Whisper decodes the samples a WAV would hold at about a sixth of the
# size. ffmpeg's FLAC encoder would otherwise pick 24-bit for decoded Opus, which decodes
# differently.
AUDIO_SUFFIX = ".flac"
_PROGRESS_PREFIX = "luminary-progress"
_TRACK_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class YtDlpError(RuntimeError):
    """yt-dlp failed; the message is its own reason, which the user can act on."""


def _argv() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _reason(stderr: bytes, returncode: int) -> str:
    """yt-dlp's last ERROR line ("Sign in to confirm you're not a bot"), first sentence only:
    the rest is its command-line advice. The exit code alone gives the user nothing."""
    errors = [
        line.removeprefix("ERROR:").strip()
        for line in stderr.decode("utf-8", "replace").splitlines()
        if line.startswith("ERROR:")
    ]
    return errors[-1].split(". ")[0][:300] if errors else f"exit {returncode}"


def fetch_metadata(url: str) -> dict:
    # `--` ends option parsing, so a URL can never be read as a flag.
    proc = subprocess.run(  # noqa: S603 -- fixed argv, the URL after `--`
        [*_argv(), "--dump-json", "--no-download", "--", url],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise YtDlpError(f"YouTube could not be read: {_reason(proc.stderr, proc.returncode)}")
    return json.loads(proc.stdout.decode("utf-8"))


def download_fraction(line: str) -> float | None:
    """Bytes downloaded over the total, from a `--progress-template` line; None when yt-dlp
    knows neither the total nor an estimate."""
    parts = line.split()
    if len(parts) != 4 or parts[0] != _PROGRESS_PREFIX:
        return None
    done, total, estimate = parts[1:]
    size = total if total.isdigit() else estimate
    if not done.isdigit() or not size.isdigit() or int(size) == 0:
        return None
    return int(done) / int(size)


def download_audio(
    url: str,
    dest_stem: Path,
    *,
    ffmpeg: str | None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """The audio track as `dest_stem` + AUDIO_SUFFIX. `ffmpeg` is the binary Luminary found.

    yt-dlp looks for ffmpeg on its own PATH, which in the bundled app is not where Luminary
    found it, so the location is passed: the directory, because postprocessing needs the
    ffprobe beside it too.
    """
    location = ["--ffmpeg-location", str(Path(ffmpeg).parent)] if ffmpeg else []
    argv = [
        *_argv(),
        "--quiet", "--progress", "--newline",
        "--progress-template",
        f"download:{_PROGRESS_PREFIX} %(progress.downloaded_bytes)s "
        "%(progress.total_bytes)s %(progress.total_bytes_estimate)s",
        "-x", "--audio-format", AUDIO_SUFFIX.lstrip("."),
        "--postprocessor-args", "ExtractAudio:-sample_fmt s16",
        *location,
        "-o", f"{dest_stem}.%(ext)s",
        "--", url,
    ]  # fmt: skip
    # stderr to a file: a pipe nobody reads fills and stalls yt-dlp mid-download.
    with tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=stderr)  # noqa: S603
        try:
            for raw in proc.stdout:
                fraction = download_fraction(raw.decode("utf-8", "replace"))
                if fraction is not None and on_progress is not None:
                    on_progress(fraction)
            returncode = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        stderr.seek(0)
        if returncode != 0:
            raise YtDlpError(
                f"yt-dlp download failed (exit {returncode}): {_reason(stderr.read(), returncode)}"
            )
    audio = dest_stem.with_suffix(AUDIO_SUFFIX)
    if not audio.is_file():
        raise YtDlpError("yt-dlp reported success but wrote no audio file")
    return audio


def uploader_caption_language(meta: dict) -> str | None:
    """The key of the uploader's caption track in the language the video is spoken in.

    `subtitles` holds tracks a person uploaded; YouTube's own speech recognition is in
    `automatic_captions` and mishears the same words Whisper does. A track in another language
    is a translation, not what was said, so a video that declares no language gets no track.
    """
    spoken = meta.get("language")
    if not isinstance(spoken, str) or not spoken:
        return None
    primary = spoken.split("-")[0].casefold()
    tracks = [
        k
        for k in meta.get("subtitles") or {}
        if isinstance(k, str) and _TRACK_KEY.fullmatch(k) and k != "live_chat"
    ]
    matching = [k for k in tracks if k.split("-")[0].casefold() == primary]
    if not matching:
        return None
    return spoken if spoken in matching else sorted(matching)[0]


def download_captions(url: str, dest: Path, track: str) -> bool:
    """Write the uploader's `track` as WebVTT to `dest`. False when none arrived: never fatal,
    since without captions Luminary transcribes the audio."""
    stem = dest.parent / f"{dest.name}.part"
    proc = subprocess.run(  # noqa: S603 -- fixed argv, the URL after `--`
        [
            *_argv(), "--skip-download", "--write-subs", "--no-write-auto-subs",
            f"--sub-langs={track}", "--sub-format=vtt", "-o", f"{stem}.%(ext)s", "--", url,
        ],  # fmt: skip
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    written = stem.with_name(f"{stem.name}.{track}.vtt")
    if proc.returncode != 0 or not written.is_file():
        print(f"caption track {track} not downloaded: {_reason(proc.stderr, proc.returncode)}",
              file=sys.stderr)  # fmt: skip
        written.unlink(missing_ok=True)
        return False
    written.replace(dest)
    return True
