# Your first connector

A connector downloads one source into a source bundle. Luminary does everything after that, so a
connector never decides what a citation points at. [protocol.md](protocol.md) is the contract;
this page is the path through it.

## 1. Read the source's terms

Before any code: find what the source's terms say about automated download and about use as
input to a model. If they forbid it, stop. No catalogue lists a connector that breaks its
source's terms, or one that gets past a site's bot defence.

## 2. Start a project

```
uvx --from "luminary-source-sdk @ git+https://github.com/nupsea/luminary#subdirectory=packages/luminary-source-sdk" \
    luminary-connector new my-source
cd my-source
uv run pytest
```

`new` writes a connector that takes one web page, a test that serves a local copy of it, and a
`pyproject.toml` with the entry point Luminary installs from. Until the SDK is on PyPI, pin the
SDK to the commit this repository uses (every connector here shares one, `scripts/check_contract.py`).

## 3. Make it your source's

The class subclasses `UrlConnector`, so `describe` comes from its attributes:

| Attribute | What it is |
|---|---|
| `NAME` | Lower-case letters, digits and `-`; equal to the entry point's name |
| `VERSION`, `LABEL` | Shown before install; `LABEL` is what the user calls the source |
| `TERMS` | `Terms(statement, url)`: the source's own words, quoted, and where. Install refuses the placeholder |
| `URL_PREFIXES` | The links it takes: scheme, host and path, as narrow as the source |

In `fetch`: `self.claimed_url(input)` for the link, `PoliteClient` to read pages (a named user
agent, a delay, retries on a dropped connection), one `bundle.add_section` per table-of-contents
entry in reading order, and `self.finish(bundle, title=...)`. Strip the site's navigation and
footers yourself. Raise `ConnectorError("input" | "auth" | "source", message)` with what the
user can do about it.

## 4. Check it

```
uv run luminary-connector run my_source:MySource fetch --url https://... --dest out/
uv run luminary-connector validate out/
uv run python -m luminary_source_sdk.conformance my_source:MySource truth.json
```

`validate` refuses what Luminary's importer refuses. The conformance kit checks the fetch against a
table of contents you wrote down by reading the real source: never take the truth from your
connector's own output. Add `--luminary <backend>` to import the bundle through Luminary itself.

Test the way the connectors here do: serve a small local copy of the source with
`luminary_source_sdk.testing.serve_pages`, and record the bundle byte for byte
(`tests/test_golden.py`), so a later change that alters it fails.

## 5. Publish it

Keep it in your own repository, or open a pull request here (CONTRIBUTING.md). Luminary's
catalogue lists a connector by archive and hash, with its licence and its source's terms shown
before anyone installs it.
