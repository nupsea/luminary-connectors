"""The HTML book connector against two small sites shaped like the generators it meets: mdBook
(contents in `toc.js`, `<main>`) and Sphinx (`<link rel="next">`, `role="main"`, a toctree)."""

from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from luminary_source_sdk import conformance
from luminary_source_sdk.testing import run

import luminary_html_book as html_book

ENTRY = "luminary_html_book:HtmlBook"
BODY = "Ownership is a set of rules that govern how a program manages memory. " * 3
CHROME = "Edit this page on GitHub"

MDBOOK_TOC = [("index.html", "Introduction", 1), ("ch01.html", "Getting Started", 1),
              ("ch01-01.html", "Installation", 2), ("ch02.html", "Ownership", 1)]  # fmt: skip
# Pages whose own heading is not what the contents call them. As in the Rust book, an <h1> is
# the page's name ("Object-Oriented ..." listed as "Object Oriented ..."); an <h2> page is named
# by the contents ("A - Keywords" over "Appendix A: Keywords").
OWN_HEADINGS = {"ch02.html": "Chapter Two: Ownership", "ch01-01.html": "Installing the Tools"}


def _named(f, h, level):
    return OWN_HEADINGS.get(f, h) if level == 1 else h
SPHINX_TOC = [("index.html", "The Tutorial", 1), ("appetite.html", "1. Whetting Your Appetite", 1),
              ("interpreter.html", "2. Using the Interpreter", 1)]  # fmt: skip


def _mdbook(folder: Path) -> None:
    def item(f, h, inner=""):
        number = f'<strong aria-hidden="true">{MDBOOK_TOC.index((f, h, 1 if "-" not in f else 2)) + 1}.</strong> '
        return f'<li class="chapter-item"><span><a href="{f}">{number}{h}</a></span>{inner}</li>'

    # As mdBook writes it: a chapter's sections in an <ol> inside the chapter's own <li>.
    (intro, start, install, own) = MDBOOK_TOC
    items = (item(*intro[:2]) + item(*start[:2], f'<ol class="section">{item(*install[:2])}</ol>')
             + item(*own[:2]))  # fmt: skip
    (folder / "toc-1a2b.js").write_text(
        "class Sidebar extends HTMLElement { connectedCallback() { this.innerHTML = "
        f"'<ol class=\"chapter\">{items}</ol>'; }} }}"
    )
    for n, (f, h, level) in enumerate(MDBOOK_TOC):
        tag = "h1" if level == 1 else "h2"  # a section page opens on an <h2>, as mdBook writes it
        nxt = MDBOOK_TOC[n + 1][0] if n + 1 < len(MDBOOK_TOC) else "../std/index.html"
        (folder / f).write_text(f"""<html><head><title>{h} - The Book</title>
<script src="toc-1a2b.js"></script></head><body>
<nav id="mdbook-sidebar" class="sidebar">Table of contents</nav>
<div id="menu-bar"><a href="https://github.com/x/edit">{CHROME}</a></div>
<main><{tag} id="a"><a class="header" href="#a">{OWN_HEADINGS.get(f, h)}</a></{tag}><p>{BODY}</p>
<pre><code>fn main() {{ println!("hi"); }}</code></pre></main>
<nav class="nav-wrapper"><a rel="next prefetch" href="{nxt}">Next</a></nav>
</body></html>""")


def _sphinx(folder: Path) -> None:
    toctree = "".join(
        f'<li class="toctree-l1"><a href="{f}">{h}</a></li>' for f, h, _ in SPHINX_TOC[1:]
    )
    for n, (f, h, _) in enumerate(SPHINX_TOC):
        nxt = SPHINX_TOC[n + 1][0] if n + 1 < len(SPHINX_TOC) else "../library/index.html"
        tree = f'<div class="toctree-wrapper"><ul>{toctree}</ul></div>' if n == 0 else ""
        (folder / f).write_text(f"""<html><head><title>{h} &#8212; Docs</title>
<link rel="next" title="next" href="{nxt}" /></head><body>
<div class="related"><ul><li><a href="index.html">index</a></li></ul></div>
<div class="body" role="main"><section><h1>{h}<a class="headerlink" href="#x">¶</a></h1>
<p>{BODY}</p>{tree}</section></div>
<div class="footer">{CHROME}</div></body></html>""")


@pytest.fixture
def site(tmp_path, monkeypatch):
    for name, build in (("book", _mdbook), ("tutorial", _sphinx)):
        (tmp_path / name).mkdir()
        build(tmp_path / name)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    monkeypatch.setattr(html_book, "URL_PREFIXES", [base])
    monkeypatch.setattr(html_book, "DELAY_S", 0)
    yield base
    server.shutdown()


def _fetch(url, dest):
    events = run(ENTRY, "fetch", input={"url": url}, dest=dest)
    assert events[-1]["event"] == "result", events[-1]
    return json.loads((dest / "manifest.json").read_text())


def test_an_mdbook_is_read_in_order_with_its_nesting(site, tmp_path):
    manifest = _fetch(site + "book/index.html", tmp_path / "b")

    assert [(s["heading"], s["level"]) for s in manifest["sections"]] == [
        (_named(f, h, level), level) for f, h, level in MDBOOK_TOC
    ]
    assert manifest["title"] == "Introduction"
    assert manifest["sections"][2]["source_url"] == site + "book/ch01-01.html"


def test_a_sphinx_book_is_read_in_order(site, tmp_path):
    manifest = _fetch(site + "tutorial/index.html", tmp_path / "b")

    assert [s["heading"] for s in manifest["sections"]] == [h for _, h, _ in SPHINX_TOC]


@pytest.mark.parametrize("book", ["book", "tutorial"])
def test_chrome_stays_out_and_the_text_stays_in(site, tmp_path, book):
    manifest = _fetch(f"{site}{book}/index.html", tmp_path / "b")
    texts = [(tmp_path / "b" / s["file"]).read_text() for s in manifest["sections"]]

    assert all(BODY.strip() in conformance.visible_text(t, ".html") for t in texts)
    assert not any(CHROME in t or "¶" in t or "Table of contents" in t for t in texts)


def test_a_next_link_loop_stops_at_the_first_repeat(site, tmp_path):
    served = tmp_path / "loop"
    served.mkdir()
    for f, nxt in (("a.html", "b.html"), ("b.html", "a.html")):
        (served / f).write_text(
            f'<main><h1>{f}</h1><p>{BODY}</p></main><a rel="next" href="{nxt}">n</a>'
        )
    # The site fixture serves tmp_path itself.
    manifest = _fetch(site + "loop/a.html", tmp_path / "b")

    assert [s["heading"] for s in manifest["sections"]] == ["a.html", "b.html"]


def test_a_site_past_the_page_cap_is_refused(site, tmp_path, monkeypatch):
    monkeypatch.setattr(html_book, "MAX_PAGES", 2)
    events = run(ENTRY, "fetch", input={"url": site + "book/index.html"}, dest=tmp_path / "b")

    assert (events[-1]["event"], events[-1]["code"]) == ("error", "source")
    assert "stopped at 2 pages" in events[-1]["message"]


def test_a_link_it_does_not_claim_is_refused(site, tmp_path):
    events = run(ENTRY, "fetch", input={"url": "https://example.org/book/"}, dest=tmp_path / "b")

    assert (events[-1]["event"], events[-1]["code"]) == ("error", "input")


def test_a_missing_page_names_itself(site, tmp_path):
    (Path(tmp_path) / "book" / "ch02.html").unlink()
    events = run(ENTRY, "fetch", input={"url": site + "book/index.html"}, dest=tmp_path / "b")

    assert events[-1]["code"] == "source"
    assert "ch02.html answered 404" in events[-1]["message"]


@pytest.mark.parametrize(("book", "toc"), [("book", MDBOOK_TOC), ("tutorial", SPHINX_TOC)])
def test_it_passes_the_conformance_kit(site, tmp_path, book, toc):
    truth = conformance.Truth({"url": f"{site}{book}/index.html"}, [_named(f, h, level) for f, h, level in toc],
                              chrome=[CHROME, "¶"])  # fmt: skip
    failed = [f for f in conformance.conform(ENTRY, truth, tmp_path / "b") if not f.passed]

    assert failed == []
