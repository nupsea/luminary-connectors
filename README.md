# Luminary connectors

A connector fetches content from one source and writes it as a Luminary **source bundle**: a
directory with `manifest.json`, `sections/` and `assets/`. [Luminary](https://github.com/nupsea/luminary)
does everything after that (parsing, chunking, search, citations, cards), so a connector cannot
change what a citation points at. Luminary installs a connector only when its user chooses to.

## Status

This repository is empty for now. Connectors arrive once Luminary publishes its connector SDK and
process protocol (nupsea/luminary#435, nupsea/luminary#438). The first is YouTube. The bundle's
manifest schema is published in Luminary at
`packages/luminary-source-sdk/schema/source-bundle.schema.json`.

## Terms

Each connector's README quotes what its source's own terms say about downloading and automated
access, and links to them. A bundle's manifest carries the same statement. This repository's
licence covers the connectors' code. It grants nothing under a source's terms: using a connector
is between you and that source, so read its terms before you install it.

## Licence

Apache-2.0, see [LICENSE](LICENSE). Luminary itself is licensed separately.
