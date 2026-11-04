"""One page of an HTML book: its next page, its text without the site's chrome, and the
contents list's nesting. Standard library only, so the connector ships no parser to review."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track",
     "wbr"}
)  # fmt: skip
# Closing one of these closes an open <p> or <li> before it, as browsers do.
_AUTO_CLOSE = {"p": {"p"}, "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}}
# Site furniture inside or around the text: never part of a section.
_CHROME_TAGS = frozenset(
    {"nav", "header", "footer", "aside", "script", "style", "noscript", "button", "form",
     "template", "iframe", "svg"}
)  # fmt: skip
# Sphinx's permalink anchors (¶), sidebars and footers. Not mdBook's `a.header`, which holds the heading.
_CHROME_CLASSES = frozenset({"headerlink", "sidebar", "related", "footer", "nav-chapters"})


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for closes in _AUTO_CLOSE.get(tag, ()):
            if self.stack[-1].tag == closes:
                self.stack.pop()
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


def _first(root: Node, match) -> Node | None:
    return next((n for n in root.walk() if match(n)), None)


def next_link(root: Node, base: str) -> str | None:
    """The page after this one, from `<link rel="next">` or `<a rel="next">`."""
    for node in root.walk():
        if node.tag in ("link", "a") and "next" in node.attrs.get("rel", "").split():
            href = node.attrs.get("href", "")
            if href:
                return urldefrag(urljoin(base, href))[0]
    return None


def content(root: Node) -> Node | None:
    """The page's text: `<main>`, Sphinx's `role="main"`, then `<article>`."""
    return (
        _first(root, lambda n: n.tag == "main")
        or _first(root, lambda n: n.attrs.get("role") == "main")
        or _first(root, lambda n: n.tag == "article")
    )


def _is_chrome(node: Node) -> bool:
    return node.tag in _CHROME_TAGS or bool(node.classes() & _CHROME_CLASSES)


def without_chrome(node: Node) -> Node:
    kept: list[Node | str] = []
    for child in node.children:
        if isinstance(child, str):
            kept.append(child)
        elif not _is_chrome(child):
            kept.append(without_chrome(child))
    return Node(node.tag, node.attrs, kept)


_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


def heading(node: Node, ranks: frozenset[str] | tuple[str, ...] = _HEADINGS) -> str:
    """The page's first heading of these ranks: mdBook opens a section's page on an <h2>."""
    first = _first(node, lambda n: n.tag in ranks)
    return " ".join(first.text().split()) if first else ""


def title(root: Node) -> str:
    t = _first(root, lambda n: n.tag == "title")
    return " ".join(t.text().split()) if t else ""


_KEPT_ATTRS = frozenset({"href", "src", "alt", "title", "colspan", "rowspan", "start"})


def serialise(node: Node, base: str) -> str:
    """HTML for the bundle: links and images made absolute, presentation attributes dropped."""
    if node.tag == "#root":
        return "".join(
            serialise(c, base) if isinstance(c, Node) else escape(c) for c in node.children
        )
    attrs = ""
    for key, value in node.attrs.items():
        if key in _KEPT_ATTRS:
            value = urljoin(base, value) if key in ("href", "src") else value
            attrs += f' {key}="{escape(value)}"'
    if node.tag in _VOID:
        return f"<{node.tag}{attrs}>"
    inner = "".join(serialise(c, base) if isinstance(c, Node) else escape(c, quote=False)
                    for c in node.children)  # fmt: skip
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def contents_list(root: Node, base: str, scope: str) -> dict[str, tuple[int, str]]:
    """{page URL: (nesting depth from 1, the name the book lists it under)} from the contents
    list: the list of in-book links holding the most of them, as mdBook's sidebar and Sphinx's
    toctree both are."""
    best: dict[str, tuple[int, str]] = {}
    for node in root.walk():
        if node.tag not in ("ol", "ul"):
            continue
        found: dict[str, tuple[int, str]] = {}
        _collect(node, 1, base, scope, found)
        if len(found) > len(best):
            best = found
    return best


def label(node: Node) -> str:
    """A link's text as it is read aloud: mdBook's aria-hidden numbering ("1.1.") left out."""
    parts = [
        c if isinstance(c, str) else "" if c.attrs.get("aria-hidden") == "true" else label(c)
        for c in node.children
    ]
    return " ".join("".join(parts).split())


def _collect(
    lst: Node, depth: int, base: str, scope: str, out: dict[str, tuple[int, str]]
) -> None:
    for item in lst.children:
        if not isinstance(item, Node):
            continue
        for node in item.walk() if item.tag == "li" else []:
            if node is not item and node.tag in ("ol", "ul"):
                _collect(node, depth + 1, base, scope, out)
                break
            if node.tag == "a" and node.attrs.get("href"):
                url = urldefrag(urljoin(base, node.attrs["href"]))[0]
                if url.startswith(scope):
                    out.setdefault(url, (depth, label(node)))
