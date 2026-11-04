# Connector template

A working connector to start from: it takes one web page and hands Luminary its `<main>` as
one section. Copy this folder into your own repository and make it your source's.

The contract is
[`docs/connectors.md`](https://github.com/nupsea/luminary/blob/master/docs/connectors.md), and the
SDK's [README](https://github.com/nupsea/luminary/tree/master/packages/luminary-source-sdk) is
the author's guide.

## Make it yours

1. **Read your source's terms first.** Find what they say about automated download, and about
   use as input to a model. If they forbid it, stop here: no catalogue lists a connector that
   breaks its source's terms, or one that gets past a site's bot defence.
2. **Rename.** Change the project name in `pyproject.toml`, the package under `src/`, `NAME`,
   the class, and the entry point. The entry point's name must equal `NAME`.
3. **Quote the terms** in `TERMS`, with the page's URL. The template ships
   `PLACEHOLDER_TERMS`, which install and the conformance kit both refuse.
4. **Claim your links** in `URL_PREFIXES`: scheme, host and path, as narrow as the source.
5. **Write `fetch`.** Add one section per table-of-contents entry, in reading order, and strip
   the site's navigation and footers yourself. Luminary keeps everything in a section after its
   first heading. Raise `ConnectorError("input" | "auth" | "source", message)` with what the
   user can do about it.
6. **Test it the way `tests/test_example.py` does:** serve a small local copy of your source,
   and run the conformance kit against a table of contents you wrote down by reading the real
   source. Never take the truth from your connector's own output.

## Check it

```
uv run pytest
uv run python -m luminary_source_sdk.conformance my_package:MySource truth.json \
    --luminary /path/to/luminary/backend
```

`--luminary` imports the bundle through Luminary's own importer and needs a Luminary checkout.

## List it

Open an issue on [`nupsea/luminary`](https://github.com/nupsea/luminary/issues) linking your
repository, a conformance run with `--luminary`, and your ground truth. It is reviewed against
the checklist in `docs/connectors.md`.
