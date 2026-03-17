from fractions import Fraction

from backend.music.notation_policy import (
    EIGHTH,
    HALF,
    QUARTER,
    SIXTEENTH,
    V1_NOTATION_POLICY,
    tied_duration_names,
)


def test_v1_defaults_match_issue_policy():
    policy = V1_NOTATION_POLICY

    assert policy.max_subdivision == SIXTEENTH
    assert policy.allowed_durations == (Fraction(1, 1), HALF, QUARTER, EIGHTH, SIXTEENTH)
    assert policy.split_cross_bar_notes is True
    assert policy.default_clef == "treble"
    assert policy.default_time_signature == "4/4"


def test_duration_quantization_uses_sixteenth_resolution():
    policy = V1_NOTATION_POLICY

    assert policy.quantize_duration(0.20) == Fraction(3, 16)
    assert policy.quantize_duration(0.49) == Fraction(1, 2)


def test_duration_ties_for_non_basic_lengths():
    policy = V1_NOTATION_POLICY

    assert policy.duration_to_tied_values(Fraction(3, 4)) == (HALF, QUARTER)
    assert tuple(tied_duration_names(policy, Fraction(3, 8))) == ("quarter", "eighth")


def test_split_cross_bar_notes_creates_tie_parts():
    policy = V1_NOTATION_POLICY

    parts = policy.split_duration_at_barlines(
        start_in_measure=Fraction(3, 4),
        duration=Fraction(1, 2),
        measure_length=Fraction(1, 1),
    )

    assert parts == (QUARTER, QUARTER)


def test_small_gap_merge_rule():
    policy = V1_NOTATION_POLICY

    assert policy.should_merge_gap(0.01)
    assert not policy.should_merge_gap(0.05)
