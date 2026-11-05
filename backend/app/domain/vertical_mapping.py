"""Vertical master consolidation (5 Nov 2026, client clean-up).

26 categories that had accumulated in the PWA collapse into 12 canonical
verticals. This module is the SINGLE definition of that mapping: migration
0040 applies it, `scripts/preview_vertical_merge.py` dry-runs it, and the
unit tests check it stays coherent.

Client decisions captured here:
  * Names are stored CLEAN ("Commodity"), not with the sheet's 01./02.
    numbering.
  * Both spellings of Machinery/Machinary go to Hardware — the sheet sent
    them to different targets, which was a slip.
  * "Forwarder Expense" is retired; anything still pointing at it moves to
    Sundry first so no file is orphaned.
"""

# The 12 that survive, in the client's intended order.
CANONICAL_VERTICALS: list[str] = [
    "Commodity",
    "Food",
    "Sundry",
    "Textile",
    "Agriculture",
    "Automobile",
    "Frippery",
    "Frozen",
    "Medicine",
    "Hardware",
    "Electronic Goods",
    "Personal/Project",
]

# Existing name (as it appears today) -> canonical name.
# Matching is case-insensitive and whitespace-trimmed when applied.
VERTICAL_MERGE_MAP: dict[str, str] = {
    "Agriculture": "Agriculture",
    "Automobile": "Automobile",
    "COMESTIC ITEMS": "Sundry",
    "Commodities": "Commodity",
    "CONSTRUCTION EQUIPMENT": "Hardware",
    "Food": "Food",
    "Frozen": "Frozen",
    "Furniture (Personal)": "Personal/Project",
    "Garments": "Textile",
    "Hardware - Building Material": "Hardware",
    "Hardware - Engine & Generator": "Hardware",
    "Hardware - Raw Material": "Hardware",
    "HOUSEHOLD": "Sundry",
    "HOUSEHOLD CHEMICALS": "Sundry",
    "HYGEINE & PERSONAL CARE": "Sundry",
    "KITCHENWARE": "Electronic Goods",
    "Machinary": "Hardware",
    "Machinery": "Hardware",
    "Material": "Sundry",
    "Medicine": "Medicine",
    "OFFICE SUPPLY": "Sundry",
    "Panoramic Padel Court": "Sundry",
    "Sundry": "Sundry",
    "Textile": "Textile",
    "White Goods": "Electronic Goods",
}

# Retired outright. Anything still attached is moved here first, so the row
# can be removed without orphaning a file.
RETIRED_VERTICALS: dict[str, str] = {
    "Forwarder Expense": "Sundry",
}


def canonical_for(name: str) -> str | None:
    """Target for an existing vertical name, or None if it is not part of
    the clean-up (unknown verticals are deliberately left alone)."""
    key = (name or "").strip().casefold()
    for source, target in {**VERTICAL_MERGE_MAP, **RETIRED_VERTICALS}.items():
        if source.casefold() == key:
            return target
    return None
