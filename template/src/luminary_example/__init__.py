"""A starting point for a Luminary connector: one web page, as one section.

Rename the package, `NAME`, the class and the entry point in `pyproject.toml`; then replace
`TERMS`, `URL_PREFIXES` and `fetch` with your source's. `docs/connectors.md` in the Luminary
repository is the contract.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any

from luminary_source_sdk import (
    PLACEHOLDER_TERMS,
    BundleWriter,
    Connector,
    ConnectorError,
    Description,
    Report,
    Terms,
)

__version__ = "0.1.0"
NAME = "example"

# Replace with a quotation of what your source's own terms say about downloading and automated
# use, and the page it comes from. Install and the conformance kit refuse the placeholder.
TERMS = Terms(statement=PLACEHOLDER_TERMS, url="https://example.com/terms")
# The links this connector takes, by prefix: scheme, host and a path.
URL_PREFIXES = ["https://example.com/"]
USER_AGENT = f"luminary-{NAME}/{__version__}"


_VOID = frozenset({"area", "br", "col", "embed", "hr", "img", "input", "source", "track", "wbr"})


class _Page(HTMLParser):
    """The page's <title>, and its <main> as HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.title = ""
        self.main: list[str] = []
        self._in_title = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        self._in_title = tag == "title"
        if self._depth and tag in _VOID:
            self.main.append(self.get_starttag_text() or "")
        elif tag == "main" or self._depth:
            self._depth += 1
            if self._depth > 1:
                self.main.append(self.get_starttag_text() or "")

    def handle_startendtag(self, tag, attrs):
        if self._depth:
            self.main.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        self._in_title = False
        if self._depth:
            self._depth -= 1
            if self._depth:
                self.main.append(f"</{tag}>")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._depth:
            self.main.append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


class Example(Connector):
    def describe(self) -> Description:
        return Description(
            name=NAME,
            version=__version__,
            licence="Apache-2.0",
            terms=TERMS,
            label="Example",
            url_prefixes=URL_PREFIXES,
        )

    def fetch(
        self,
        input: dict[str, Any],
        credentials: dict[str, Any],
        bundle: BundleWriter,
        report: Report,
    ) -> None:
        url = str(input.get("url", ""))
        if not any(url.startswith(p) for p in URL_PREFIXES):
            raise ConnectorError("input", f"{url} is not a page this connector takes")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode(resp.headers.get_content_charset() or "utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ConnectorError("source", f"could not read {url}: {exc}") from exc
        report(0.5, "reading the page")
        page = _Page()
        page.feed(html)
        if not page.main:
            raise ConnectorError("source", f"{url} has no <main>")
        title = " ".join(page.title.split()) or url
        bundle.add_section("page", title, html="".join(page.main), source_url=url)
        bundle.finish(connector=(NAME, __version__), title=title, terms=TERMS, source_url=url)
