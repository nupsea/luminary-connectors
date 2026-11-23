"""A starting point for a Luminary connector: one web page, as one section.

Rename the package, `NAME`, the class and the entry point in `pyproject.toml`; then replace
`TERMS`, `URL_PREFIXES` and `fetch` with your source's. `docs/protocol.md` is the contract.
`luminary-connector new <name>` writes the same project for you.
"""

from __future__ import annotations

from typing import Any

from luminary_source_sdk import PLACEHOLDER_TERMS, BundleWriter, ConnectorError, Report, Terms
from luminary_source_sdk.bases import UrlConnector
from luminary_source_sdk.client import PoliteClient
from luminary_source_sdk.pages import main_html

__version__ = "0.1.0"


class Example(UrlConnector):
    NAME = "example"
    VERSION = __version__
    LABEL = "Example"
    # Replace with a quotation of what your source's own terms say about downloading and
    # automated use, and the page it comes from. Install and the conformance kit refuse the
    # placeholder.
    TERMS = Terms(statement=PLACEHOLDER_TERMS, url="https://example.com/terms")
    # The links this connector takes, by prefix: scheme, host and a path.
    URL_PREFIXES = ("https://example.com/",)

    def fetch(
        self,
        input: dict[str, Any],
        credentials: dict[str, Any],
        bundle: BundleWriter,
        report: Report,
    ) -> None:
        url = self.claimed_url(input)
        _, page = PoliteClient(self.user_agent()).get_text(url)
        report(0.5, "reading the page")
        title, main = main_html(page)
        if not main:
            raise ConnectorError("source", f"{url} has no <main>")
        title = title or url
        bundle.add_section("page", title, html=main, source_url=url)
        self.finish(bundle, title=title, source_url=url)
