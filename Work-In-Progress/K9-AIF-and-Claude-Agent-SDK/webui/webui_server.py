#!/usr/bin/env python3
"""
Minimal category-browsing server for the storefront.

Not the Router/Storefront API (that's Phase 2, still ahead) -- this is
a small, honest step up from a pure static mockup: one dynamic route,
/category?category_id=FISH (matching the original app's exact
splash.jsp URL scheme), reading real rows from the live petstore
Postgres schema. Everything else (Account/Cart/Sign In/Search) stays a
"#" placeholder -- this only makes category browsing real.
"""

from __future__ import annotations

import html
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from petstore.services import inventory  # noqa: E402
from petstore.services.original_catalog_data import raw_items, species_by_category  # noqa: E402

# category_id -> species names, derived from the original catalog's own
# product/category grouping (WEB-INF/sql/cloudscape.sql) -- not stored
# as its own DB column; petstore.sku only has the coarse
# supplies/livestock/veterinary category, so this mapping lives here in
# the presentation layer instead of a schema migration for one demo page.
_SPECIES_BY_CATEGORY = species_by_category()
_RAW_ITEMS = raw_items()

_CATEGORY_TITLES = {
    "FISH": "Fish", "DOGS": "Dogs", "CATS": "Cats",
    "BIRDS": "Birds", "REPTILES": "Reptiles",
}

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pet Store Agentic — {title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Verdana, Arial, Helvetica, sans-serif; font-size: 13px; color: #000; }}
  .topbar {{ background: #163832 url('images/bkg-topbar.gif') repeat-x; color: #fff; padding: 8px 14px; }}
  .topbar a {{ color: #fff; text-decoration: none; }}
  .content {{ padding: 24px; max-width: 700px; margin: 0 auto; }}
  h1 {{ color: #163832; font-family: Georgia, serif; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; font-size: 12px; }}
  th {{ background: #eef3f8; color: #163832; }}
  .back {{ display: inline-block; margin-top: 20px; color: #163832; }}
  .empty {{ color: #777; font-style: italic; margin-top: 16px; }}
</style>
</head>
<body>
  <div class="topbar"><a href="index.html">&larr; Pet Store Agentic</a></div>
  <div class="content">
    <h1>{title}</h1>
    {rows_html}
    <a class="back" href="index.html">&larr; Back to storefront</a>
  </div>
</body>
</html>
"""


def _render_category(category_id: str) -> bytes:
    category_id = (category_id or "").upper()
    title = _CATEGORY_TITLES.get(category_id, category_id or "Unknown category")
    species_set = _SPECIES_BY_CATEGORY.get(category_id, set())

    rows = []
    if species_set:
        for sku_id, species, orig_cat, desc, variant, _price in _RAW_ITEMS:
            if orig_cat != category_id:
                continue
            sku = inventory.get_sku(sku_id)
            if sku is None:
                continue
            rows.append(sku)

    if rows:
        body = ["<table><tr><th>SKU</th><th>Name</th><th>Description</th><th>Price</th></tr>"]
        for sku in rows:
            body.append(
                f"<tr><td>{html.escape(sku.sku_id)}</td>"
                f"<td>{html.escape(sku.name)}</td>"
                f"<td>{html.escape(sku.description)}</td>"
                f"<td>${sku.unit_price_cents/100:.2f}</td></tr>"
            )
        body.append("</table>")
        rows_html = "".join(body)
    else:
        rows_html = '<p class="empty">No items found for this category (or the catalog hasn\'t been seeded yet -- run demo/seed_original_catalog.py).</p>'

    return _PAGE_TEMPLATE.format(title=html.escape(title), rows_html=rows_html).encode("utf-8")


class Handler(SimpleHTTPRequestHandler):

    def do_GET(self) -> None:  # noqa: N802 (stdlib override)
        parsed = urlparse(self.path)
        if parsed.path == "/category":
            query = parse_qs(parsed.query)
            category_id = query.get("category_id", [""])[0]
            body = _render_category(category_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main() -> None:
    port = int(os.environ.get("PETSTORE_WEBUI_PORT", "8500"))
    os.chdir(Path(__file__).resolve().parent)
    server = HTTPServer(("", port), Handler)
    print(f"Serving storefront (with real /category browsing) on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
