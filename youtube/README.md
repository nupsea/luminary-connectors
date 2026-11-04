# YouTube

Takes a YouTube video link and hands Luminary its audio, the uploader's own caption track when
there is one in the language the video is spoken in, and its title, channel, tags, description
and chapter titles. Luminary transcribes it (or reads the captions), chunks it and cites it with
timestamps; this connector only downloads.

## YouTube's terms

YouTube's [Terms of Service](https://www.youtube.com/t/terms) say you may not:

> access, reproduce, download, distribute, transmit, broadcast, display, sell, license, alter,
> modify or otherwise use any part of the Service or any Content except: (a) as expressly
> authorized by the Service; (b) with prior written permission from YouTube and, if applicable,
> the respective rights holders

and may not:

> access the Service using any automated means (such as robots, botnets or scrapers) except (a)
> in the case of public search engines, in accordance with YouTube's robots.txt file; or (b) with
> YouTube's prior written permission

Downloading a video with this connector is between you and YouTube. This repository's licence
covers this code and grants nothing under YouTube's terms. Every bundle the connector writes
carries the same statement.

## What it needs

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), installed into the connector's own
  environment.
- ffmpeg, which Luminary finds on the machine and passes to the connector. Luminary refuses a
  link before downloading when ffmpeg or its speech-to-text component is missing, and says which
  to install.

## Install

From a clone of this repository, with Luminary's backend environment:

```sh
python -m app.scripts.install_connector /path/to/luminary-connectors/youtube
```

Luminary builds the connector's environment with `uv sync`. Once installed, a pasted YouTube
link goes to this connector instead of Luminary's built-in download.

## Tests

```sh
uv run pytest
```

yt-dlp is faked at the subprocess boundary, so the tests never reach YouTube. The bundle a fetch
writes is checked against the schema the SDK publishes.
