#!/usr/bin/env python3
"""Load the original Java Pet Store's 28-item livestock catalog into Postgres."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from petstore.services import inventory
from petstore.services.original_catalog_data import original_catalog_skus, original_catalog_stock


def main() -> None:
    skus = original_catalog_skus()
    stock = original_catalog_stock()
    inventory.seed_catalog(skus, stock)
    print(f"Seeded {len(skus)} livestock SKUs from the original Java Pet Store catalog.")
    for sku in skus:
        print(f"  {sku.sku_id:8s} {sku.name:35s} ${sku.unit_price_cents/100:>7.2f}  ({sku.species})")


if __name__ == "__main__":
    main()
