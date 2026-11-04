# Luminary connectors

A connector fetches content from one source and writes it as a Luminary **source bundle**: a
directory with `manifest.json`, `sections/` and `assets/`. [Luminary](https://github.com/nupsea/luminary)
does everything after that (parsing, chunking, search, citations, cards), so a connector cannot
change what a citation points at. Luminary installs a connector only when its user chooses to.

## Connectors

| Connector | Takes | Needs on the machine |
|---|---|---|
| [youtube](youtube/) | YouTube video links | ffmpeg, and Luminary's speech-to-text |

Each is a project of its own. Luminary installs one from its folder
(`python -m app.scripts.install_connector <folder>`), builds its environment with `uv sync`, and
runs it as a separate process per request. A connector is written against
[`luminary-source-sdk`](https://github.com/nupsea/luminary/tree/master/packages/luminary-source-sdk),
whose README is the author's guide; the bundle's schema is
`packages/luminary-source-sdk/schema/source-bundle.schema.json`.

## Terms

Each connector's README quotes what its source's own terms say about downloading and automated
access, and links to them. A bundle's manifest carries the same statement. This repository's
licence covers the connectors' code. It grants nothing under a source's terms: using a connector
is between you and that source, so read its terms before you install it.

## Licence

Apache-2.0, see [LICENSE](LICENSE). Luminary itself is licensed separately.
