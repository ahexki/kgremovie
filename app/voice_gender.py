"""Male / female voice choice from the ORIGINAL speech (pitch), so each line of the dub can use a male or a female
Burmese voice (Edge TTS: Thiha = male, Nilar = female).

How: the original audio is read as 8 kHz mono; its fundamental frequency (F0, the pitch) is estimated every 20 ms by
autocorrelation; the median F0 of the voiced frames inside a subtitle-sized window decides the speaker's gender:
below ~155 Hz male, above ~180 Hz female (a typical adult man speaks around 85-155 Hz, a woman around 165-255 Hz).
Windows that are too short, too quiet or in between take the label of the nearest confident window.

Honest limits: pitch is only a proxy. Deep-voiced women, high-voiced men, children, singing, heavy music or noise can
be labelled wrongly; two speakers of the same gender cannot be told apart (both get the same voice).
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable

import numpy as np

LogFn = Callable[[str], None]
SR = 8000
MALE_MAX_HZ = 155.0
FEMALE_MIN_HZ = 180.0
MIN_VOICED_FRAMES = 8                 # 8 frames x 20 ms: less than this is not enough to judge a speaker
FRAME_S, HOP_S = 0.04, 0.02
F_MIN, F_MAX = 70.0, 400.0
VOICE_MALE = "my-MM-ThihaNeural"
VOICE_FEMALE = "my-MM-NilarNeural"

VOICE_MODES = {                        # label in the app -> mode
    "Selected voice": "selected",
    "Male voice (Thiha)": "male",
    "Female voice (Nilar)": "female",
    "Auto — by speaker": "auto",
}
VOICE_MODE_LABELS = {mode: label for label, mode in VOICE_MODES.items()}


def normalize_voice_mode(value: Any) -> str:
    text = str(value or "").strip()
    text = VOICE_MODES.get(text, text).lower()
    return text if text in VOICE_MODE_LABELS else "selected"


def voice_for(mode: str, selected_voice: str, gender: str | None = None) -> str:
    mode = normalize_voice_mode(mode)
    if mode == "male":
        return VOICE_MALE
    if mode == "female":
        return VOICE_FEMALE
    if mode == "auto":
        return VOICE_FEMALE if gender == "female" else VOICE_MALE if gender == "male" else selected_voice
    return selected_voice


# ------------------------------------------------------------------------------------------------ pitch
def estimate_f0(samples: np.ndarray, sr: int = SR, *, chunk: int = 3000) -> tuple[np.ndarray, np.ndarray]:
    """F0 in Hz for every 20 ms frame (0 = not voiced) and the frame start times in seconds."""
    x = np.asarray(samples, dtype=np.float32)
    n = int(round(FRAME_S * sr))
    hop = int(round(HOP_S * sr))
    if x.size < n + hop:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    count = 1 + (x.size - n) // hop
    lag_min, lag_max = int(sr / F_MAX), int(sr / F_MIN)
    f0 = np.zeros(count, dtype=np.float32)
    window = np.hanning(n).astype(np.float32)
    nfft = 1 << (2 * n - 1).bit_length()
    energy_all = np.empty(count, dtype=np.float32)
    rho_all = np.zeros(count, dtype=np.float32)
    lag_all = np.zeros(count, dtype=np.int32)
    for a in range(0, count, chunk):
        b = min(count, a + chunk)
        idx = (np.arange(a, b)[:, None] * hop) + np.arange(n)[None, :]
        frames = x[idx]
        frames = frames - frames.mean(axis=1, keepdims=True)
        frames = frames * window
        energy = (frames ** 2).sum(axis=1)
        spec = np.fft.rfft(frames, nfft, axis=1)
        r = np.fft.irfft(spec * np.conj(spec), nfft, axis=1)[:, : lag_max + 3]
        r0 = np.maximum(r[:, 0], 1e-9)
        rn = r / r0[:, None]
        seg = rn[:, lag_min:lag_max + 1]
        best = seg.argmax(axis=1) + lag_min
        peak = rn[np.arange(b - a), best]
        # octave check: a peak at half the lag that is nearly as strong is the real period
        half = best // 2
        ok = half >= lag_min
        for off in (-1, 0, 1):
            h = np.clip(half + off, lag_min, lag_max)
            hv = rn[np.arange(b - a), h]
            use = ok & (hv >= 0.85 * peak)
            best = np.where(use, h, best)
            peak = np.where(use, np.maximum(peak, hv), peak)
        energy_all[a:b], rho_all[a:b], lag_all[a:b] = energy, peak, best
    loud = energy_all > 0.03 * np.percentile(energy_all, 95)
    voiced = loud & (rho_all > 0.5)
    f0[voiced] = sr / lag_all[voiced]
    return f0, np.arange(count, dtype=np.float32) * HOP_S


def window_pitch(f0: np.ndarray, times: np.ndarray, start: float, end: float) -> tuple[float | None, int]:
    """(median F0 of the voiced frames inside [start, end], how many frames)."""
    if f0.size == 0:
        return None, 0
    lo, hi = np.searchsorted(times, start), np.searchsorted(times, end)
    vals = f0[lo:hi]
    vals = vals[vals > 0]
    if vals.size < MIN_VOICED_FRAMES:
        return None, int(vals.size)
    return float(np.median(vals)), int(vals.size)


def label_windows(medians: list[float | None], default: str = "male") -> list[str]:
    """'male' / 'female' for every window. Confident windows are labelled by F0; the others take the nearest confident one."""
    labels: list[str | None] = []
    for m in medians:
        labels.append(None if m is None else "male" if m < MALE_MAX_HZ else "female" if m > FEMALE_MIN_HZ else "?")
    male = [m for m, l in zip(medians, labels) if l == "male"]
    female = [m for m, l in zip(medians, labels) if l == "female"]
    if male and female:                                                   # in-between: the nearer speaker type
        cm, cf = float(np.median(male)), float(np.median(female))
        labels = [("male" if abs(m - cm) <= abs(m - cf) else "female") if l == "?" else l for m, l in zip(medians, labels)]
    else:
        mid = (MALE_MAX_HZ + FEMALE_MIN_HZ) / 2
        labels = [("male" if m < mid else "female") if l == "?" else l for m, l in zip(medians, labels)]
    known = [i for i, l in enumerate(labels) if l]
    if not known:
        return [default] * len(labels)
    out: list[str] = []
    for i, l in enumerate(labels):
        if l:
            out.append(l)
            continue
        nearest = min(known, key=lambda k: (abs(k - i), k > i))           # nearest in time, the earlier one on a tie
        out.append(labels[nearest])                                       # type: ignore[arg-type]
    return out


# ------------------------------------------------------------------------------------------------ audio
def read_audio(ffmpeg: str, source: str, sr: int = SR) -> np.ndarray | None:
    """The first audio stream of `source` as float32 mono at `sr`, or None when there is no audio."""
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sr),
                           "-f", "s16le", "-"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def detect_genders(ffmpeg: str, source: str, windows: list[tuple[float, float]], *, default: str = "male",
                   log: LogFn = lambda _m: None) -> tuple[list[str], list[float | None]]:
    """Gender label and median F0 for every (start, end) window of the ORIGINAL video's audio."""
    samples = read_audio(ffmpeg, source)
    if samples is None or samples.size == 0:
        log("⚠️ Voice detection: the video has no audio to listen to — the selected voice is used for every line")
        return [default] * len(windows), [None] * len(windows)
    f0, times = estimate_f0(samples)
    medians = [window_pitch(f0, times, s, e)[0] for s, e in windows]
    return label_windows(medians, default), medians
