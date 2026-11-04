"""The template's own checks: it reads a page served from this test, and passes the
conformance kit once its terms are a real quotation. Keep this shape for your source: a small
local copy of what it serves, and a ground truth you wrote by reading the real one."""

from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from luminary_source_sdk import Terms, conformance

import luminary_example

ENTRY = "luminary_example:Example"
BODY = "A log is an append-only sequence of records stored on disk. " * 3
PAGE = f"""<html><head><title>Logs</title></head><body>
<header>Site menu</header><main><h1>Logs</h1><p>{BODY}</p><img src="log.png" alt="a log"></main>
<footer>Site footer</footer></body></html>"""


@pytest.fixture
def site(tmp_path, monkeypatch):
    (tmp_path / "logs.html").write_text(PAGE)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/"
    monkeypatch.setattr(luminary_example, "URL_PREFIXES", [base])
    yield base
    server.shutdown()


def _failed(site, tmp_path):
    truth = conformance.Truth(
        {"url": site + "logs.html"}, ["Logs"], chrome=["Site menu", "Site footer"]
    )
    return [f.check for f in conformance.conform(ENTRY, truth, tmp_path / "bundle") if not f.passed]


def test_the_template_fails_only_on_its_placeholder_terms(site, tmp_path):
    assert _failed(site, tmp_path) == ["describe"]


def test_with_real_terms_it_passes_the_conformance_kit(site, tmp_path, monkeypatch):
    monkeypatch.setattr(
        luminary_example,
        "TERMS",
        Terms("Pages on this test server may be downloaded.", "https://example.com/terms"),
    )

    assert _failed(site, tmp_path) == []
