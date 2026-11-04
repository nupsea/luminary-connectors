"""A book published as HTML pages, for Luminary: each page a section, in reading order.

Pages are found by following each page's "next" link from the one pasted, staying inside the
book's folder, so the result does not depend on one site generator's contents format. The
contents list, when the first page or its `toc*.js` carries one, gives each page its nesting
and the name the book lists it under.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlsplit

from luminary_source_sdk import BundleWriter, Connector, ConnectorError, Description, Report, Terms

from luminary_html_book import page

__version__ = "0.1.0"
NAME = "html-book"

TERMS = Terms(
    statement=(
        "Each book this connector takes is published under a licence that allows copying it. "
        'The Rust project: "the Rust Programming Language and all other official projects, '
        'including this website, are generally dual-licensed" under Apache-2.0 and MIT, and '
        "doc.rust-lang.org's robots.txt allows /book/. The Python documentation: \"This page is "
        'licensed under the Python Software Foundation License Version 2" '
        "(https://docs.python.org/3/copyright.html), and docs.python.org's robots.txt allows "
        "/3/. Neither site's terms say anything about automated download or use as model input."
    ),
    url="https://www.rust-lang.org/policies/licenses",
)
# Only sites whose terms were read are claimed; a new one is added with its terms above.
URL_PREFIXES = ["https://doc.rust-lang.org/", "https://docs.python.org/3/"]

USER_AGENT = f"luminary-html-book/{__version__} (+https://github.com/nupsea/luminary-connectors)"
# One request a second: a whole book (the Rust book's 111 pages) in about two minutes.
DELAY_S = 1.0
# More pages than any book these sites publish; a next-link loop or a whole site stops here.
MAX_PAGES = 1500
_TIMEOUT_S = 30
_TOC_SCRIPT = re.compile(r"(?:^|/)toc[^/]*\.js$")


def _get(url: str) -> tuple[str, str]:
    """(final URL, text) of one page."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.geturl(), resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise ConnectorError("source", f"{url} answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ConnectorError("source", f"could not reach {url}: {exc}") from exc


def book_scope(url: str) -> str:
    """The book's folder: pages outside it belong to the site, not the book."""
    parts = urlsplit(url)
    folder = parts.path if parts.path.endswith("/") else parts.path.rsplit("/", 1)[0] + "/"
    return f"{parts.scheme}://{parts.netloc}{folder}"


def _contents(root: page.Node, url: str, scope: str) -> dict[str, tuple[int, str]]:
    contents = page.contents_list(root, url, scope)
    for node in root.walk():
        src = node.attrs.get("src", "") if node.tag == "script" else ""
        script = urljoin(url, src) if src else ""
        if script.startswith(scope) and _TOC_SCRIPT.search(urlsplit(script).path):
            found = page.contents_list(page.parse(_get(script)[1]), url, scope)
            if len(found) > len(contents):
                contents = found
    return contents


class HtmlBook(Connector):
    def describe(self) -> Description:
        return Description(
            name=NAME, version=__version__, licence="Apache-2.0", terms=TERMS,
            label="HTML book", url_prefixes=URL_PREFIXES,
        )  # fmt: skip

    def fetch(
        self, input: dict[str, Any], credentials: dict[str, Any], bundle: BundleWriter,
        report: Report,
    ) -> None:  # fmt: skip
        start = str(input.get("url", ""))
        if not any(start.startswith(p) for p in URL_PREFIXES):
            raise ConnectorError("input", f"{start} is not a book this connector takes")
        scope = book_scope(start)
        url: str | None = start
        seen: set[str] = set()
        contents: dict[str, tuple[int, str]] | None = None
        book_title = ""
        while url and url not in seen and url.startswith(scope):
            if len(seen) >= MAX_PAGES:
                raise ConnectorError("source", f"stopped at {MAX_PAGES} pages; is {start} a book?")
            if seen:
                time.sleep(DELAY_S)
            seen.add(url)
            final, html = _get(url)
            root = page.parse(html)
            if contents is None:
                contents = _contents(root, final, scope)
                book_title = page.title(root)
            self._add(bundle, root, final, len(seen), contents.get(final))
            report(min(0.99, len(seen) / max(len(contents), len(seen) + 1)), "downloading pages")
            url = page.next_link(root, final)
        bundle.finish(
            connector=(NAME, __version__), title=_book_name(book_title), terms=TERMS,
            source_url=start,
        )  # fmt: skip

    @staticmethod
    def _add(
        bundle: BundleWriter, root: page.Node, url: str, n: int, listed: tuple[int, str] | None
    ) -> None:
        body = page.content(root)
        if body is None:
            raise ConnectorError("source", f"{url} has no <main>, role=main or <article>")
        body = page.without_chrome(body)
        # A page's own <h1>, else the name the contents list it under ("A - Keywords" over an
        # <h2> "Appendix A: Keywords"), else its first heading: mdBook's print.html titles pages so.
        level, name = listed or (1, "")
        named = page.heading(body, ranks=("h1",)) or name or page.heading(body)
        bundle.add_section(
            f"p{n:04d}", named or page.title(root) or url,
            html=page.serialise(body, url), level=level, source_url=url,
        )  # fmt: skip


def _book_name(title: str) -> str:
    """ "The Rust Programming Language - The Rust Programming Language" -> the book's name, and
    "The Python Tutorial — Python 3.15 documentation" -> "The Python Tutorial"."""
    for sep in (" - ", " — ", " | "):
        if sep in title:
            return title.split(sep, maxsplit=1)[0].strip()
    return title.strip() or "HTML book"
