"""The vertical consolidation map must stay coherent (5 Nov 2026).

Migration 0040 rewrites live request and projection rows from this table, so
a typo here is a data defect. These checks are cheap insurance.
"""

from app.domain.vertical_mapping import (
    CANONICAL_VERTICALS,
    RETIRED_VERTICALS,
    VERTICAL_MERGE_MAP,
    canonical_for,
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


def test_canonical_names_carry_no_numeric_prefix():
    """Client chose clean names over the sheet's 01./02. numbering."""
    assert all(not v[:2].isdigit() for v in CANONICAL_VERTICALS)
