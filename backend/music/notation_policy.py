from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable

DurationName = str

WHOLE = Fraction(1, 1)
HALF = Fraction(1, 2)
QUARTER = Fraction(1, 4)
EIGHTH = Fraction(1, 8)
SIXTEENTH = Fraction(1, 16)


@dataclass(frozen=True)
class NotationPolicy:
    """Central policy describing how transcription events become notation for v1."""

    max_subdivision: Fraction = SIXTEENTH
    allowed_durations: tuple[Fraction, ...] = (WHOLE, HALF, QUARTER, EIGHTH, SIXTEENTH)
    split_cross_bar_notes: bool = True
    merge_small_gaps_below_seconds: float = 0.05
    default_clef: str = "treble"
    default_time_signature: str = "4/4"
    prefer_dotted_durations: bool = False
    duration_names: dict[Fraction, DurationName] = field(
        default_factory=lambda: {
            WHOLE: "whole",
            HALF: "half",
            QUARTER: "quarter",
            EIGHTH: "eighth",
            SIXTEENTH: "sixteenth",
        }
    )

    def quantize_duration(self, duration: float | Fraction) -> Fraction:
        """Quantize a duration value to the nearest supported subdivision."""
        value = self._to_fraction(duration)
        steps = value / self.max_subdivision
        rounded_steps = int(steps + Fraction(1, 2))
        return rounded_steps * self.max_subdivision

    def duration_to_tied_values(self, duration: float | Fraction) -> tuple[Fraction, ...]:
        """Break a duration into allowed note values (ties when multiple entries)."""
        quantized = self.quantize_duration(duration)
        if quantized <= 0:
            return tuple()

        remaining = quantized
        result: list[Fraction] = []
        for value in sorted(self.allowed_durations, reverse=True):
            while remaining >= value:
                result.append(value)
                remaining -= value

        if remaining != 0:
            raise ValueError(f"Could not represent quantized duration {quantized} with allowed durations")

        return tuple(result)

    def split_duration_at_barlines(
        self,
        start_in_measure: float | Fraction,
        duration: float | Fraction,
        measure_length: float | Fraction,
    ) -> tuple[Fraction, ...]:
        """Split a note duration at barlines to support tie creation."""
        start = self.quantize_duration(start_in_measure)
        remaining = self.quantize_duration(duration)
        bar_length = self.quantize_duration(measure_length)

        if not self.split_cross_bar_notes:
            return (remaining,)

        if remaining <= 0:
            return tuple()

        parts: list[Fraction] = []
        offset = start % bar_length

        while remaining > 0:
            room = bar_length - offset if offset else bar_length
            chunk = min(room, remaining)
            parts.append(chunk)
            remaining -= chunk
            offset = Fraction(0)

        return tuple(parts)

    def should_merge_gap(self, gap_seconds: float) -> bool:
        """Return True when a tiny silence should be merged into nearby note events."""
        return gap_seconds < self.merge_small_gaps_below_seconds

    def duration_name(self, duration: float | Fraction) -> DurationName:
        """Map a duration to a MusicXML-ish name when directly supported."""
        quantized = self.quantize_duration(duration)
        if quantized not in self.duration_names:
            raise KeyError(f"Unsupported named duration: {quantized}")
        return self.duration_names[quantized]

    @staticmethod
    def _to_fraction(value: float | Fraction) -> Fraction:
        if isinstance(value, Fraction):
            return value
        return Fraction(value).limit_denominator(1024)


V1_NOTATION_POLICY = NotationPolicy()


def tied_duration_names(policy: NotationPolicy, duration: float | Fraction) -> Iterable[DurationName]:
    """Convenience helper for turning a duration into tied notation token names."""
    return [policy.duration_name(value) for value in policy.duration_to_tied_values(duration)]
