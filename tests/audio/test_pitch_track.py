import numpy as np

from backend.audio.pitch_track import extract_pitch_frames


def _tone(frequency: float, sample_rate: int, duration: float, amplitude: float = 0.8) -> np.ndarray:
    t = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    return amplitude * np.sin(2 * np.pi * frequency * t)


def test_extract_pitch_frames_tracks_sustained_note_with_good_stability():
    sample_rate = 16000
    samples = _tone(220.0, sample_rate, 1.0)

    frames = extract_pitch_frames(samples, sample_rate)
    voiced_freqs = np.array([f.frequency for f in frames if f.frequency > 0], dtype=np.float64)

    assert len(voiced_freqs) > 10
    assert abs(float(np.median(voiced_freqs)) - 220.0) < 4.0
    assert float(np.std(voiced_freqs)) < 5.0


def test_extract_pitch_frames_marks_silence_as_unvoiced():
    sample_rate = 16000
    samples = np.zeros(sample_rate, dtype=np.float64)

    frames = extract_pitch_frames(samples, sample_rate)

    assert len(frames) > 0
    assert all(frame.frequency == 0.0 and frame.confidence == 0.0 for frame in frames)


def test_extract_pitch_frames_reduces_octave_errors_on_higher_note():
    sample_rate = 16000
    samples = _tone(440.0, sample_rate, 1.0, amplitude=0.9)

    frames = extract_pitch_frames(samples, sample_rate, min_frequency=80.0, max_frequency=1000.0)
    voiced_freqs = np.array([f.frequency for f in frames if f.frequency > 0], dtype=np.float64)

    assert len(voiced_freqs) > 10
    median_freq = float(np.median(voiced_freqs))
    assert abs(median_freq - 440.0) < 8.0
    assert abs(median_freq - 220.0) > 80.0
