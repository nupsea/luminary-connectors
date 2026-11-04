# HTML book

Takes the first page of a book published as HTML pages and hands Luminary one document: each
page a section, in reading order, with its link as the section's source. Luminary chunks, cites
and writes cards for it as for an EPUB; this connector only downloads.

## The sites it takes

Only sites whose terms were read are claimed. A site is added with what its terms say.

| Site | What its terms say |
|---|---|
| `doc.rust-lang.org` | The [Rust project](https://www.rust-lang.org/policies/licenses): "the Rust Programming Language and all other official projects, including this website, are generally dual-licensed" under Apache-2.0 and MIT. `robots.txt` allows `/book/` |
| `docs.python.org/3/` | The [copyright page](https://docs.python.org/3/copyright.html): "This page is licensed under the Python Software Foundation License Version 2". `robots.txt` allows `/3/` |

Neither site's terms say anything about automated download or use as model input.

## How it reads a book

- **Pages:** from the pasted page, each page's `rel="next"` link, as long as it stays inside the
  book's folder. mdBook and Sphinx both write one. A link that loops back stops the walk. More
  than 1,500 pages is refused as not one book. It never reads a print view or sitemap as a
  shortcut.
- **Nesting:** from the contents list, when the first page or a `toc*.js` beside it carries
  one. That is the nested list of in-book links holding the most entries, as mdBook's sidebar
  and Sphinx's toctree are.
- **Text:** `<main>`, else `role="main"`, else `<article>`. Navigation, headers, footers,
  sidebars, forms, scripts and permalink anchors are removed. A page's heading is its first
  heading of any rank.
- **Politeness:** one request a second, with a `User-Agent` naming this repository.

## Tests

`uv run pytest` serves two small books shaped like mdBook and Sphinx output from a local
server, and runs the conformance kit on each. It never reaches the network.

`tests/truth/` holds the ground truth for the real books, written from each book's own
table of contents:
- `rust-book.json` comes from the `<h1>` headings of the book's `print.html`
  (`print_toc.py`), which the connector never reads.
- `python-tutorial.json` comes from the tutorial index's toctree.

To check a real book:

```
uv run python -m luminary_source_sdk.conformance luminary_html_book:HtmlBook \
    tests/truth/rust-book.json --luminary /path/to/luminary/backend
```
