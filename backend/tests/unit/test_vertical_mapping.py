"""The vertical consolidation map must stay coherent (5 Nov 2026).

Migration 0040 rewrites live request and projection rows from this table, so
a typo here is a data defect. These checks are cheap insurance.
"""

from app.domain.vertical_mapping import (
    CANONICAL_VERTICALS,
    NUMBERED_VERTICALS,
    RETIRED_VERTICALS,
    VERTICAL_MERGE_MAP,
    bare_name,
    canonical_for,
    numbered_name,
)


def test_every_target_is_a_canonical_vertical():
    for source, target in {**VERTICAL_MERGE_MAP, **RETIRED_VERTICALS}.items():
        assert target in CANONICAL_VERTICALS, f"{source} -> unknown target {target}"


def test_twelve_canonical_verticals_all_distinct():
    assert len(CANONICAL_VERTICALS) == 12
    lowered = [v.casefold() for v in CANONICAL_VERTICALS]
    assert len(set(lowered)) == 12, "canonical names must be case-insensitively unique"


def test_sources_are_case_insensitively_unique():
    """The DB has a UNIQUE index on LOWER(name) — two sources differing only
    by case would mean the same row listed twice."""
    keys = [k.casefold() for k in {**VERTICAL_MERGE_MAP, **RETIRED_VERTICALS}]
    assert len(set(keys)) == len(keys)


def test_both_machinery_spellings_go_to_hardware():
    """Client decision: the sheet sent them to different targets by mistake."""
    assert VERTICAL_MERGE_MAP["Machinary"] == "Hardware"
    assert VERTICAL_MERGE_MAP["Machinery"] == "Hardware"


def test_retired_vertical_has_somewhere_to_send_stragglers():
    assert RETIRED_VERTICALS["Forwarder Expense"] == "Sundry"


def test_lookup_is_case_and_space_insensitive():
    assert canonical_for("  sundry ") == "Sundry"
    assert canonical_for("WHITE GOODS") == "Electronic Goods"
    assert canonical_for("forwarder expense") == "Sundry"
    # Unknown verticals are left alone rather than guessed at.
    assert canonical_for("Something New") is None


def test_stored_names_carry_the_sheet_numbering():
    """6 Nov 2026: the client reversed the 5 Nov decision — the ordinal is
    part of the stored name, so it shows in every dropdown and export."""
    assert NUMBERED_VERTICALS[0] == "01.Commodity"
    assert NUMBERED_VERTICALS[-1] == "12.Personal/Project"
    assert NUMBERED_VERTICALS == [
        f"{i:02d}.{v}" for i, v in enumerate(CANONICAL_VERTICALS, start=1)
    ]


def test_numbered_names_sort_into_the_clients_order():
    """The list endpoint orders on LOWER(name) only; the numbering is what
    keeps Commodity first and Personal/Project last."""
    assert sorted(NUMBERED_VERTICALS, key=str.casefold) == NUMBERED_VERTICALS


def test_numbering_round_trips():
    for bare, numbered in zip(CANONICAL_VERTICALS, NUMBERED_VERTICALS):
        assert numbered_name(bare) == numbered
        assert bare_name(numbered) == bare
        # Idempotent — applying it twice must not stack prefixes.
        assert numbered_name(numbered) == numbered


def test_numbering_leaves_everything_else_alone():
    assert numbered_name("Something New") == "Something New"
    assert bare_name("Something New") == "Something New"
    # A name that merely starts with digits is not a prefix.
    assert bare_name("3M Supplies") == "3M Supplies"


def test_lookup_accepts_an_already_numbered_name():
    """So the dry run and the mapping stay correct against a database
    migration 0041 has already renamed."""
    assert canonical_for("01.Commodity") == "Commodity"
    assert canonical_for("11.Electronic Goods") == "Electronic Goods"
