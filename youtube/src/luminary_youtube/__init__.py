"""YouTube for Luminary: a talk's audio, its uploader's captions and its description, as a bundle.

Luminary transcribes and cites it; this connector only downloads.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from luminary_source_sdk import BundleWriter, Connector, ConnectorError, Description, Report, Terms

from luminary_youtube import ytdlp

__version__ = "0.1.0"
NAME = "youtube"

TERMS = Terms(
    statement=(
        "YouTube's Terms of Service say you may not \"access, reproduce, download, distribute, "
        "transmit, broadcast, display, sell, license, alter, modify or otherwise use any part "
        'of the Service or any Content except: (a) as expressly authorized by the Service; '
        '(b) with prior written permission from YouTube and, if applicable, the respective '
        'rights holders", nor "access the Service using any automated means (such as robots, '
        'botnets or scrapers) except (a) in the case of public search engines, in accordance '
        "with YouTube's robots.txt file; or (b) with YouTube's prior written permission\". "
        "Downloading a video with this connector is between you and YouTube."
    ),
    url="https://www.youtube.com/t/terms",
)

URL_PREFIXES = [
    "https://www.youtube.com/watch",
    "https://youtube.com/watch",
    "https://m.youtube.com/watch",
    "https://youtu.be/",
    "http://www.youtube.com/watch",
    "http://youtu.be/",
]
# What the manifest takes; YouTube's own limits are lower except for tags.
_MAX_TAG_CHARS = 100


class YouTube(Connector):
    def describe(self) -> Description:
        return Description(
            name=NAME,
            version=__version__,
            licence="Apache-2.0",
            terms=TERMS,
            label="YouTube",
            url_prefixes=URL_PREFIXES,
            media=["youtube"],
            tools=["ffmpeg"],
        )

    def fetch(
        self, input: dict[str, Any], credentials: dict[str, Any], bundle: BundleWriter,
        report: Report,
    ) -> None:  # fmt: skip
        url = str(input.get("url") or "")
        if not any(url.startswith(p) for p in URL_PREFIXES):
            raise ConnectorError("input", f"{url!r} is not a YouTube video link")
        ffmpeg = (input.get("tools") or {}).get("ffmpeg")
        try:
            meta = ytdlp.fetch_metadata(url)
            with tempfile.TemporaryDirectory(prefix="luminary-youtube-") as scratch:
                media = _download(url, meta, Path(scratch), ffmpeg, bundle, report)
        except ytdlp.YtDlpError as exc:
            raise ConnectorError("source", str(exc)) from exc
        channel = meta.get("uploader") or meta.get("channel")
        bundle.finish(
            connector=(NAME, __version__),
            title=meta.get("title") or "YouTube Video",
            terms=TERMS,
            media=media,
            authors=[channel] if isinstance(channel, str) and channel.strip() else [],
            tags=[t for t in meta.get("tags") or [] if _short_text(t, _MAX_TAG_CHARS)],
            description=meta.get("description") or None,
            chapters=[
                c["title"] for c in meta.get("chapters") or []
                if isinstance(c, dict) and _short_text(c.get("title"), 500)
            ],  # fmt: skip
            source_url=url,
            locator=meta.get("id") or None,
        )


def _download(
    url: str, meta: dict, scratch: Path, ffmpeg: str | None, bundle: BundleWriter, report: Report
) -> dict[str, Any]:
    """Audio, then the uploader's captions when there is a track, moved into the bundle."""
    audio = ytdlp.download_audio(
        url, scratch / "audio", ffmpeg=ffmpeg, on_progress=lambda f: report(f, "downloading")
    )
    media: dict[str, Any] = {
        "kind": "youtube",
        "url": url,
        "audio": bundle.add_asset_file(f"audio{ytdlp.AUDIO_SUFFIX}", audio),
    }
    track = ytdlp.uploader_caption_language(meta)
    vtt = scratch / "captions.vtt"
    if track and ytdlp.download_captions(url, vtt, track):
        media["captions"] = bundle.add_asset_file("captions.vtt", vtt)
    return media


def _short_text(value: object, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit
