"""The ground-truth page tree of a Confluence subtree, from REST API v1's child-page listing:
another API from the connector's v2 walk, and none of its code. A page whose rendered body has
no text (a redirect) is no section, so it is not listed; its children are.

usage: python v1_tree.py <wiki base> <page id> <page url> > truth.json
"""

import json
import re
import sys
import time
import urllib.request

BASE, ROOT, URL = sys.argv[1], sys.argv[2], sys.argv[3]


def get(path):
    time.sleep(1.0)  # robots.txt's Crawl-delay
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "luminary-truth/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def says_something(page):
    html = page.get("body", {}).get("view", {}).get("value", "")
    return bool(re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").strip())


def walk(page, out):
    if says_something(page):
        out.append(" ".join(page["title"].split()))
    start = 0
    while True:
        data = get(f"/rest/api/content/{page['id']}/child/page?limit=100&start={start}&expand=body.view")
        for child in data["results"]:
            walk(child, out)
        if data.get("size", 0) < data.get("limit", 100):
            return
        start += data["limit"]


toc: list[str] = []
walk(get(f"/rest/api/content/{ROOT}?expand=body.view"), toc)
# The REST body carries no site navigation, so there is no chrome to name.
print(json.dumps({"input": {"url": URL}, "toc": toc, "chrome": []}, indent=1, ensure_ascii=False))
