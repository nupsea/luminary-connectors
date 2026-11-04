"""The ground-truth table of contents of an mdBook: the `<h1>` headings of its `print.html`, the
book's single-page print view, in order. The connector never reads `print.html`.

usage: python print_toc.py print.html > rust-book.json
"""

import json
import sys
from html.parser import HTMLParser


class _Headings(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = self.in_h1 = False
        self.headings: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
        elif tag == "h1" and self.in_main:
            self.in_h1 = True
            self.headings.append("")

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_h1 = False
        elif tag == "main":
            self.in_main = False

    def handle_data(self, data):
        if self.in_h1:
            self.headings[-1] += data


parser = _Headings()
parser.feed(open(sys.argv[1], encoding="utf-8").read())
toc = [" ".join(h.split()) for h in parser.headings]
truth = {
    "input": {"url": "https://doc.rust-lang.org/book/"},
    "toc": toc,
    "chrome": [
        "Keyboard shortcuts",
        "Press ← or → to navigate between chapters",
        "Press S or / to search in the book",
    ],
}
print(json.dumps(truth, indent=1, ensure_ascii=False))
