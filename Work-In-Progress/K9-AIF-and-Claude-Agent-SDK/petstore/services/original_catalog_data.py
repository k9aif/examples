"""
Catalog data adapted from the original Java Pet Store demo application
(Sun Microsystems, 2001), redistributed under its original BSD-style
license (see webui/images/THIRD_PARTY_LICENSE_java_pet_store.txt).
Source: j2ee-petstore/.../WEB-INF/sql/cloudscape.sql -- the `product`,
`item`, and `inventory` INSERT statements, flattened here into this
project's own SKU shape (one row per original `item`, species carried
over from the parent `product`).

Every item here is genuinely livestock (fish, dogs, cats, birds,
reptiles) -- the original app sold live animals in every category; it
had no "supplies" category at all. That's exactly this project's
regulated bucket (project.md §2), so these seed the livestock side of
the catalog. The non-livestock supplies SKUs used in
demo/walk_deterministic_order.py are this project's own invention,
needed to have a non-gated path to demonstrate at all.

No LLM/agent/SDK imports here -- pure data, still subject to
test_deterministic_purity.py like the rest of petstore/services/.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from petstore.services.models import SKU

# (sku_id, species, category, description, variant, price_dollars)
_RAW_ITEMS: List[Tuple[str, str, str, str, str, float]] = [
    ("EST-1",  "Angelfish",            "FISH",     "Salt Water fish from Australia", "Large, Cuddly", 16.50),
    ("EST-2",  "Angelfish",            "FISH",     "Salt Water fish from Australia", "Small", 16.50),
    ("EST-3",  "Tiger Shark",          "FISH",     "Salt Water fish from Australia", "Toothless, Mean", 18.50),
    ("EST-4",  "Koi",                  "FISH",     "Fresh Water fish from Japan", "Spotted", 18.50),
    ("EST-5",  "Koi",                  "FISH",     "Fresh Water fish from Japan", "Spotless", 18.50),
    ("EST-20", "Goldfish",             "FISH",     "Fresh Water fish from China", "Adult Male", 5.50),
    ("EST-21", "Goldfish",             "FISH",     "Fresh Water fish from China", "Adult Female", 5.29),
    ("EST-6",  "Bulldog",              "DOGS",     "Friendly dog from England", "Male Adult", 18.50),
    ("EST-7",  "Bulldog",              "DOGS",     "Friendly dog from England", "Female Puppy", 18.50),
    ("EST-8",  "Poodle",               "DOGS",     "Cute dog from France", "Male Puppy", 18.50),
    ("EST-9",  "Dalmation",            "DOGS",     "Great dog for a Fire Station", "Spotless Male Puppy", 18.50),
    ("EST-10", "Dalmation",            "DOGS",     "Great dog for a Fire Station", "Spotted Adult Female", 18.50),
    ("EST-22", "Labrador Retriever",   "DOGS",     "Great hunting dog", "Adult Male", 135.50),
    ("EST-23", "Labrador Retriever",   "DOGS",     "Great hunting dog", "Adult Female", 145.49),
    ("EST-24", "Labrador Retriever",   "DOGS",     "Great hunting dog", "Male Puppy", 255.50),
    ("EST-25", "Labrador Retriever",   "DOGS",     "Great hunting dog", "Female Puppy", 325.29),
    ("EST-26", "Chihuahua",            "DOGS",     "Great companion dog", "Adult Male", 125.50),
    ("EST-27", "Chihuahua",            "DOGS",     "Great companion dog", "Adult Female", 155.29),
    ("EST-28", "Golden Retriever",     "DOGS",     "Great family dog", "Adult Female", 155.29),
    ("EST-11", "Rattlesnake",          "REPTILES", "Doubles as a watch dog", "Venomless", 18.50),
    ("EST-12", "Rattlesnake",          "REPTILES", "Doubles as a watch dog", "Rattleless", 18.50),
    ("EST-13", "Iguana",               "REPTILES", "Friendly green friend", "Green Adult", 18.50),
    ("EST-14", "Manx",                 "CATS",     "Great for reducing mouse populations", "Tailless", 58.50),
    ("EST-15", "Manx",                 "CATS",     "Great for reducing mouse populations", "With tail", 23.50),
    ("EST-16", "Persian",              "CATS",     "Friendly house cat, doubles as a princess", "Adult Female", 93.50),
    ("EST-17", "Persian",              "CATS",     "Friendly house cat, doubles as a princess", "Adult Male", 93.50),
    ("EST-18", "Amazon Parrot",        "BIRDS",    "Great companion for up to 75 years", "Adult Male", 193.50),
    ("EST-19", "Finch",                "BIRDS",    "Great stress reliever", "Adult Male", 15.50),
]

_DEFAULT_QTY = 10


def original_catalog_skus() -> List[SKU]:
    skus = []
    for sku_id, species, orig_category, desc, variant, price in _RAW_ITEMS:
        skus.append(SKU(
            sku_id=sku_id,
            name=f"{species} ({variant})",
            category="livestock",
            description=desc,
            unit_price_cents=round(price * 100),
            is_livestock=True,
            is_prescription=False,
            species=species,
        ))
    return skus


def original_catalog_stock() -> Dict[str, int]:
    return {sku_id: _DEFAULT_QTY for sku_id, *_ in _RAW_ITEMS}
