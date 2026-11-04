"""The Confluence connector against a local server answering Confluence Cloud's REST v2 routes."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from luminary_source_sdk import conformance
from luminary_source_sdk.testing import run

import luminary_confluence as confluence

ENTRY = "luminary_confluence:Confluence"
BODY = "<p>A Special Interest Group gathers people working on one problem across projects.</p>"
CHROME = "Edit this page"

# id: (title, parent, childPosition). Positions are served out of order on purpose.
PAGES = {
    "1": ("Special Interest Groups", None, 0),
    "2": ("SIG Services", "1", 7),
    "3": ("Inactive Groups", "1", 0),
    "4": ("Identity SIG", "3", 2),
    "5": ("Climate SIG", "3", 1),
    "6": ("SIG Process", "1", 4),
    # Never reordered: no position, shown alphabetically; served here in neither order.
    "7": ("Archived Proposals", "1", 9),
    "8": ("Telecom SIG", "7", None),
    "9": ("Capital Markets SIG", "7", None),
    "10": ("Media SIG", "7", None),
    # A redirect: no text of its own, so no section, but its child keeps its place.
    "11": ("Task Force", "1", 5),
    "12": ("Task Force Notes", "11", 0),
}
REDIRECT = '<p><img class="wysiwyg-unknown-macro" src="/placeholder?name=redirect" /></p>'
EMPTY = {"11"}
TREE = [("Special Interest Groups", 1), ("Inactive Groups", 2), ("Climate SIG", 3),
        ("Identity SIG", 3), ("SIG Process", 2), ("Task Force Notes", 3), ("SIG Services", 2),
        ("Archived Proposals", 2), ("Capital Markets SIG", 3), ("Media SIG", 3),
        ("Telecom SIG", 3)]  # fmt: skip


def _handler(pages, hidden):
    class Wiki(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            q = parse_qs(url.query)
            parts = url.path.strip("/").split("/")
            if parts[:3] == ["wiki", "api", "v2"] and parts[3] == "spaces":
                return self._send(200, {"results": [{"key": "SIG", "homepageId": "1"}]})
            if parts[:4] == ["wiki", "api", "v2", "pages"]:
                pid = parts[4]
                if pid not in pages or pid in hidden:
                    return self._send(404, {"message": "not found"})
                if len(parts) == 6 and parts[5] == "children":
                    kids = [{"id": k, "title": v[0], "childPosition": v[2]}
                            for k, v in pages.items() if v[1] == pid]  # fmt: skip
                    if "cursor" in q:
                        return self._send(200, {"results": kids[1:], "_links": {}})
                    nxt = f"/wiki/api/v2/pages/{pid}/children?cursor=x" if len(kids) > 1 else None
                    return self._send(
                        200, {"results": kids[:1], "_links": {"next": nxt} if nxt else {}}
                    )
                title = pages[pid][0]
                return self._send(200, {
                    "id": pid, "title": title,
                    "body": {"view": {"value": REDIRECT if pid in EMPTY else BODY}},
                    "_links": {"webui": f"/spaces/SIG/pages/{pid}/{title.replace(' ', '+')}"},
                })  # fmt: skip
            self._send(404, {})

    return Wiki


@pytest.fixture
def wiki(monkeypatch):
    hidden: set[str] = set()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(PAGES, hidden))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/wiki/"
    monkeypatch.setattr(confluence, "URL_PREFIXES", [base])
    monkeypatch.setattr(confluence, "DELAY_S", 0)
    yield base, hidden
    server.shutdown()


def _fetch(url, dest):
    events = run(ENTRY, "fetch", input={"url": url}, dest=dest)
    assert events[-1]["event"] == "result", events[-1]
    return json.loads((dest / "manifest.json").read_text())


def test_a_subtree_reads_depth_first_by_position(wiki, tmp_path):
    base, _ = wiki
    manifest = _fetch(base + "spaces/SIG/pages/1/Special+Interest+Groups", tmp_path / "b")

    assert [(s["heading"], s["level"]) for s in manifest["sections"]] == TREE
    assert manifest["title"] == "Special Interest Groups"
    assert manifest["sections"][1]["source_url"] == base + "spaces/SIG/pages/3/Inactive+Groups"


def test_a_space_link_starts_at_its_home_page(wiki, tmp_path):
    base, _ = wiki
    manifest = _fetch(base + "spaces/SIG/overview", tmp_path / "b")

    assert manifest["sections"][0]["heading"] == "Special Interest Groups"
    assert len(manifest["sections"]) == len(TREE)


def test_a_page_that_is_not_public_names_itself(wiki, tmp_path):
    base, hidden = wiki
    hidden.add("5")
    events = run(ENTRY, "fetch", input={"url": base + "spaces/SIG/pages/1/x"}, dest=tmp_path / "b")

    assert events[-1]["code"] == "source"
    assert "pages/5" in events[-1]["message"] and "not public" in events[-1]["message"]


def test_a_tree_past_the_page_cap_is_refused(wiki, tmp_path, monkeypatch):
    base, _ = wiki
    monkeypatch.setattr(confluence, "MAX_PAGES", 3)
    events = run(ENTRY, "fetch", input={"url": base + "spaces/SIG/pages/1/x"}, dest=tmp_path / "b")

    assert "stopped at 3 pages" in events[-1]["message"]


def test_a_link_it_does_not_claim_is_refused(wiki, tmp_path):
    url = "https://example.atlassian.net/wiki/spaces/X/pages/1/y"
    events = run(ENTRY, "fetch", input={"url": url}, dest=tmp_path / "b")

    assert (events[-1]["event"], events[-1]["code"]) == ("error", "input")


def test_it_passes_the_conformance_kit(wiki, tmp_path):
    base, _ = wiki
    truth = conformance.Truth({"url": base + "spaces/SIG/pages/1/x"}, [h for h, _ in TREE],
                              chrome=[CHROME])  # fmt: skip
    failed = [f for f in conformance.conform(ENTRY, truth, tmp_path / "b") if not f.passed]

    assert failed == []


def test_a_dropped_connection_is_retried_and_a_dead_one_reported(wiki, tmp_path, monkeypatch):
    import urllib.error

    base, _ = wiki
    monkeypatch.setattr(confluence, "RETRY_BACKOFF_S", 0)
    real = confluence._Api._get_once
    drops = {"left": 1}

    def flaky(self, url):
        if drops["left"]:
            drops["left"] -= 1
            raise urllib.error.URLError(TimeoutError("timed out"))
        return real(self, url)

    monkeypatch.setattr(confluence._Api, "_get_once", flaky)
    manifest = _fetch(base + "spaces/SIG/pages/1/x", tmp_path / "ok")
    assert len(manifest["sections"]) == len(TREE)

    def dead(self, url):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(confluence._Api, "_get_once", dead)
    events = run(ENTRY, "fetch", input={"url": base + "spaces/SIG/pages/1/x"}, dest=tmp_path / "no")
    assert (events[-1]["code"], "could not read" in events[-1]["message"]) == ("source", True)


def test_a_tree_with_no_text_is_refused(wiki, tmp_path):
    base, _ = wiki
    saved = set(EMPTY)
    EMPTY.update(PAGES)
    try:
        events = run(
            ENTRY, "fetch", input={"url": base + "spaces/SIG/pages/1/x"}, dest=tmp_path / "b"
        )
    finally:
        EMPTY.clear()
        EMPTY.update(saved)

    assert (events[-1]["code"], "has any text" in events[-1]["message"]) == ("source", True)
