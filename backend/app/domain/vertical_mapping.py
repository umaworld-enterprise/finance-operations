"""Vertical master consolidation (5 Nov 2026, client clean-up).

26 categories that had accumulated in the PWA collapse into 12 canonical
verticals. This module is the SINGLE definition of that mapping: migration
0040 applies it, `scripts/preview_vertical_merge.py` dry-runs it, and the
unit tests check it stays coherent.

Client decisions captured here:
  * Names are STORED with the sheet's numbering ("01.Commodity"), reversing
    the 5 Nov decision to keep them clean. See NUMBERED_VERTICALS below.
  * Both spellings of Machinery/Machinary go to Hardware — the sheet sent
    them to different targets, which was a slip.
  * "Forwarder Expense" is retired; anything still pointing at it moves to
    Sundry first so no file is orphaned.
"""

import re

# The 12 that survive, in the client's intended order. These are the *bare*
# names — the merge targets migration 0040 works in. The names actually
# stored are the numbered ones below.
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


# ── Numbering (6 Nov 2026, client reversal) ──────────────────────────────
# The client now wants the sheet's ordinal carried in the stored name —
# "01.Commodity", not "Commodity" — so it shows in every dropdown, export
# and report. It also makes ordering free: the list endpoint sorts on
# LOWER(name), and numbered names sort into the client's intended order.
#
# 0040 still merges into the BARE names and migration 0041 renumbers them
# afterwards. Keeping the two apart leaves 0040's journal — and therefore
# its downgrade — working exactly as written and tested.
NUMBER_SEPARATOR = "."

_NUMBER_PREFIX = re.compile(r"^\s*\d{2}" + re.escape(NUMBER_SEPARATOR) + r"\s*")


def bare_name(name: str) -> str:
    """'01.Commodity' -> 'Commodity'. A name with no prefix is unchanged."""
    return _NUMBER_PREFIX.sub("", (name or "").strip(), count=1)


def numbered_name(name: str) -> str:
    """'Commodity' -> '01.Commodity'. A name outside the canonical 12 — or
    one already numbered — is returned unchanged."""
    key = bare_name(name).casefold()
    for position, canonical in enumerate(CANONICAL_VERTICALS, start=1):
        if canonical.casefold() == key:
            return f"{position:02d}{NUMBER_SEPARATOR}{canonical}"
    return name


# What the `verticals` table actually holds once 0041 has run.
NUMBERED_VERTICALS: list[str] = [numbered_name(v) for v in CANONICAL_VERTICALS]


def canonical_for(name: str) -> str | None:
    """Bare target for an existing vertical name, or None if it is not part
    of the clean-up (unknown verticals are deliberately left alone).

    An already-numbered name resolves to itself, so this stays correct when
    run against a database 0041 has already renamed."""
    key = bare_name(name).casefold()
    for source, target in {**VERTICAL_MERGE_MAP, **RETIRED_VERTICALS}.items():
        if source.casefold() == key:
            return target
    # A canonical name that is nobody's merge source — Hardware, say, which
    # only ever appears as a target — still resolves to itself.
    for canonical in CANONICAL_VERTICALS:
        if canonical.casefold() == key:
            return canonical
    return None
