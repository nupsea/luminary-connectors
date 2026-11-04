# Confluence

Takes a Confluence page, or a space's overview, and hands Luminary that page and every page under
it as one document. Each page is a section, in the order the space's page tree shows, with its
link as the section's source. Luminary chunks, cites and writes cards for it; this connector only
downloads.

## The wikis it takes

Only wikis whose terms were read are claimed. A wiki is added with what its terms say.

| Wiki | What its terms say |
|---|---|
| `lf-hyperledger.atlassian.net/wiki` | The Linux Foundation's [Terms of Use](https://www.linuxfoundation.org/legal/terms), revised 2020-11-16: "Except as otherwise provided, Content on this site is licensed under a Creative Commons Attribution 3.0 License", and wiki submissions "will be governed by the Creative Commons Attribution 3.0". `robots.txt` allows `/wiki/` with a 1-second crawl delay |

The terms say nothing about automated download or use as model input.

**Not claimed: `cwiki.apache.org`** (Confluence Data Center, which Luminary's spike #348 also
names). Its pages state no licence for their content; the Apache Software Foundation's site
footer licenses apache.org under Apache-2.0 but does not mention the wiki. It stays unclaimed
until that is decided, and so does the Data Center API (REST v1) it would need.

## How it reads a wiki

- **The API:** Confluence Cloud's REST API v2, anonymously, so only public pages. A page that
  answers 401, 403 or 404 stops the import with its link.
- **Order:** the pasted page, then its children depth first. Children are ordered by their
  position in the tree; pages nobody reordered have no position and come alphabetically, as
  Confluence shows them.
- **Text:** each page's rendered body (`view`), under its title. A page with no text of its
  own, such as a redirect, is not a section; its children keep their place.
- **Politeness:** one request a second, as `robots.txt` asks, with a `User-Agent` naming this
  repository. A dropped connection is retried twice. More than 1,000 pages is refused as more
  than one document.

## Tests

`uv run pytest` serves a small wiki from a local server that answers the same v2 routes. It
covers order and nesting, unpositioned pages, a redirect page, a paginated child list, a space
link, a non-public page, the page cap, a dropped connection, and the conformance kit. It never
reaches the network.

`tests/truth/` holds the ground truth for two live subtrees, written by `v1_tree.py` from REST
API v1's child-page listing: another API, and none of this connector's code. To check them:

```
uv run python -m luminary_source_sdk.conformance luminary_confluence:Confluence \
    tests/truth/sigs.json --luminary /path/to/luminary/backend
```
