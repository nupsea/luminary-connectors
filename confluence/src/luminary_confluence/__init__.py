"""A Confluence page and the pages under it, for Luminary: each page a section, in tree order.

Reads Confluence Cloud's REST API v2 anonymously: the pasted page (or a space's home page), then
its children by their position, depth first, so a subtree reads as the space's sidebar shows it.
Luminary chunks, cites and writes cards for it; this connector only downloads.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote, urlsplit

from luminary_source_sdk import BundleWriter, ConnectorError, Report, Terms
from luminary_source_sdk.bases import UrlConnector
from luminary_source_sdk.client import PoliteClient
from luminary_source_sdk.progress import Progress

__version__ = "0.1.0"

# robots.txt's Crawl-delay.
DELAY_S = 1.0
# The core takes at most 5,000 sections; a subtree past this is a whole wiki, not a document.
MAX_PAGES = 1000
# A connection that times out is retried: the live wiki dropped one of about fifty requests
# while its ground truth was written. An HTTP answer (404, 403) is never retried.
RETRIES = 2
RETRY_BACKOFF_S = 2.0
_NOT_PUBLIC = "the page is missing or not public"
_PAGE = re.compile(r"/wiki/spaces/[^/]+/pages/(\d+)")
_SPACE = re.compile(r"/wiki/spaces/([^/]+)/?(?:overview)?/?$")


class _Api:
    def __init__(self, base: str, client: PoliteClient) -> None:
        self.base = base
        self.client = client

    def get(self, path: str) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base}{path}"
        try:
            return self.client.get_json(url)
        except ConnectorError as exc:
            # The wikis it reads are anonymous: a 401 is a page that is not public, not a
            # sign-in Luminary could ask for.
            if exc.code == "auth":
                raise ConnectorError("source", exc.message) from exc
            raise

    def children(self, page_id: str) -> list[dict[str, Any]]:
        """A page's child pages in the order the space shows them."""
        found: list[dict[str, Any]] = []
        path: str | None = f"/api/v2/pages/{page_id}/children?limit=250"
        while path:
            data = self.get(path)
            found += data.get("results", [])
            nxt = (data.get("_links") or {}).get("next")
            path = f"{self.base.rsplit('/wiki', 1)[0]}{nxt}" if nxt else None
        # Pages nobody reordered carry no position and show alphabetically, Confluence's
        # default; v2 lists them in neither order ("SIG Archived Proposals").
        return sorted(found, key=_tree_order)


def _tree_order(child: dict[str, Any]) -> tuple[bool, int, str]:
    position = child.get("childPosition")
    return position is None, position or 0, str(child.get("title") or "").casefold()


_TAG = re.compile(r"<[^>]+>")


def has_text(html: str) -> bool:
    """Whether a page says anything: a redirect or an empty page renders only markup."""
    return bool(_TAG.sub("", html).replace("&nbsp;", " ").strip())


def wiki_base(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/wiki"


def root_page(api: _Api, url: str) -> str:
    """The page id a link names: a page's own, or its space's home page."""
    path = urlsplit(url).path
    if m := _PAGE.search(path):
        return m.group(1)
    if m := _SPACE.search(path):
        spaces = api.get(f"/api/v2/spaces?keys={quote(m.group(1))}").get("results") or []
        if spaces and spaces[0].get("homepageId"):
            return str(spaces[0]["homepageId"])
        raise ConnectorError("input", f"no public space {m.group(1)} at {api.base}")
    raise ConnectorError("input", f"{url} is not a Confluence page or space link")


class Confluence(UrlConnector):
    NAME = "confluence"
    VERSION = __version__
    LABEL = "Confluence"
    TERMS = Terms(
        statement=(
            "The Linux Foundation's Terms of Use (revised November 16, 2020), which cover its "
            'project wikis: "Except as otherwise provided, Content on this site is licensed under '
            'a Creative Commons Attribution 3.0 License", and non-code submissions including '
            'wikis "will be governed by the Creative Commons Attribution 3.0". '
            "lf-hyperledger.atlassian.net allows /wiki/ in robots.txt with a crawl delay of 1 "
            "second. The terms say nothing about automated download or use as model input."
        ),
        url="https://www.linuxfoundation.org/legal/terms",
    )
    # Only wikis whose terms were read are claimed; another is added with its terms above.
    URL_PREFIXES = ("https://lf-hyperledger.atlassian.net/wiki/",)

    def fetch(
        self,
        input: dict[str, Any],
        credentials: dict[str, Any],
        bundle: BundleWriter,
        report: Report,
    ) -> None:
        url = self.claimed_url(input)
        client = PoliteClient(
            self.user_agent("https://github.com/nupsea/luminary-connectors"),
            delay_s=DELAY_S,
            retries=RETRIES,
            backoff_s=RETRY_BACKOFF_S,
            messages={401: _NOT_PUBLIC, 403: _NOT_PUBLIC, 404: _NOT_PUBLIC},
        )
        api = _Api(wiki_base(url), client)
        root = root_page(api, url)
        # Depth first, children by position: the order the space's page tree shows.
        stack: list[tuple[str, int]] = [(root, 1)]
        seen: set[str] = set()
        title = ""
        added = False
        progress = Progress(report, "downloading pages")
        while stack:
            page_id, depth = stack.pop()
            if page_id in seen:
                continue
            if len(seen) >= MAX_PAGES:
                raise ConnectorError(
                    "source", f"stopped at {MAX_PAGES} pages; paste a smaller part"
                )
            seen.add(page_id)
            page = api.get(f"/api/v2/pages/{page_id}?body-format=view")
            heading = " ".join(str(page.get("title") or "").split()) or f"Page {page_id}"
            title = title or heading
            body = ((page.get("body") or {}).get("view") or {}).get("value") or ""
            webui = (page.get("_links") or {}).get("webui") or ""
            stack += [(str(c["id"]), depth + 1) for c in reversed(api.children(page_id))]
            if not has_text(body):
                # A section must say something; its children keep their place in the tree.
                continue
            bundle.add_section(
                f"p{len(seen):04d}",
                heading,
                html=f"<h1>{escape(heading, quote=False)}</h1>{body}",
                level=depth,
                source_url=f"{api.base}{webui}" if webui else None,
            )
            added = True
            progress.update(len(seen), len(stack) + 1)
        if not added:
            raise ConnectorError("source", f"no page under {url} has any text")
        self.finish(bundle, title=title, source_url=url)
