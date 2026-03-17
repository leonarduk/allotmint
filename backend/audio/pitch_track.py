"""Offline pitch tracking utilities for monophonic audio recordings."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PitchFrame:
    """A single time-aligned pitch estimate."""

    time: float
    frequency: float
    confidence: float


def _frame_signal(signal: np.ndarray, frame_size: int, hop_size: int) -> tuple[np.ndarray, np.ndarray]:
    if signal.size == 0:
        return np.empty((0, frame_size), dtype=np.float64), np.empty((0,), dtype=np.float64)

    num_frames = int(np.ceil(max(signal.size - frame_size, 0) / hop_size)) + 1
    padded_size = (num_frames - 1) * hop_size + frame_size
    padded = np.zeros((padded_size,), dtype=np.float64)
    padded[: signal.size] = signal

    frames = np.lib.stride_tricks.sliding_window_view(padded, frame_size)[::hop_size]
    return frames, padded


def _normalized_autocorrelation(frame: np.ndarray, min_lag: int, max_lag: int) -> tuple[np.ndarray, np.ndarray]:
    centered = frame - np.mean(frame)
    energy = np.sum(centered * centered)
    if energy <= 1e-12:
        return np.array([], dtype=np.float64), np.array([], dtype=np.int64)

    correlation = np.correlate(centered, centered, mode="full")
    autocorr = correlation[correlation.size // 2 :]

    max_lag = min(max_lag, autocorr.size - 1)
    if min_lag > max_lag:
        return np.array([], dtype=np.float64), np.array([], dtype=np.int64)

    lags = np.arange(min_lag, max_lag + 1)
    values = autocorr[min_lag : max_lag + 1] / energy
    return values, lags


def _refine_lag(lags: np.ndarray, values: np.ndarray, peak_index: int) -> float:
    if peak_index <= 0 or peak_index >= len(values) - 1:
        return float(lags[peak_index])

    y0, y1, y2 = values[peak_index - 1], values[peak_index], values[peak_index + 1]
    denom = y0 - 2 * y1 + y2
    if abs(denom) < 1e-12:
        return float(lags[peak_index])

    offset = 0.5 * (y0 - y2) / denom
    return float(lags[peak_index] + offset)


def extract_pitch_frames(
    samples: np.ndarray,
    sample_rate: int,
    *,
    frame_duration: float = 0.04,
    hop_duration: float = 0.01,
    min_frequency: float = 80.0,
    max_frequency: float = 1000.0,
    energy_threshold: float = 1e-3,
    confidence_threshold: float = 0.6,
) -> list[PitchFrame]:
    """Extract time-aligned pitch estimates and confidence values.

    Unvoiced frames are emitted with ``frequency=0.0`` and ``confidence=0.0``.
    """

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if min_frequency <= 0 or max_frequency <= min_frequency:
        raise ValueError("Invalid frequency range")

    signal = np.asarray(samples, dtype=np.float64).flatten()
    frame_size = max(int(round(frame_duration * sample_rate)), 1)
    hop_size = max(int(round(hop_duration * sample_rate)), 1)
    min_lag = int(sample_rate / max_frequency)
    max_lag = int(sample_rate / min_frequency)

    frames, _ = _frame_signal(signal, frame_size, hop_size)
    if frames.size == 0:
        return []

    window = np.hanning(frame_size)
    rms_values = np.sqrt(np.mean(np.square(frames), axis=1))
    max_rms = float(np.max(rms_values)) if rms_values.size else 0.0

    output: list[PitchFrame] = []
    for idx, frame in enumerate(frames):
        time_sec = (idx * hop_size + frame_size / 2) / sample_rate
        rms = float(rms_values[idx])

        if max_rms <= 1e-12 or rms < max(energy_threshold, max_rms * 0.03):
            output.append(PitchFrame(time=time_sec, frequency=0.0, confidence=0.0))
            continue

        values, lags = _normalized_autocorrelation(frame * window, min_lag, max_lag)
        if values.size == 0:
            output.append(PitchFrame(time=time_sec, frequency=0.0, confidence=0.0))
            continue

        peak_index = int(np.argmax(values))
        peak_value = float(values[peak_index])
        if peak_value < confidence_threshold:
            output.append(PitchFrame(time=time_sec, frequency=0.0, confidence=0.0))
            continue

        refined_lag = _refine_lag(lags, values, peak_index)
        frequency = float(sample_rate / refined_lag)

        energy_ratio = min(rms / max(max_rms, 1e-12), 1.0)
        confidence = float(np.clip(peak_value * (0.5 + 0.5 * energy_ratio), 0.0, 1.0))
        output.append(PitchFrame(time=time_sec, frequency=frequency, confidence=confidence))

    return output
