"""Audio loading and preprocessing.

All downstream analysis assumes 16 kHz mono float32 in [-1, 1].
"""
from __future__ import annotations

import numpy as np
import soundfile as sf
import librosa

TARGET_SR = 16000


def load_audio(path: str, target_sr: int = TARGET_SR) -> np.ndarray:
    """Load an audio file as mono float32 at ``target_sr``.

    Handles arbitrary input sample rates and channel counts. Returns a 1-D
    numpy array normalised to roughly [-1, 1].
    """
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.ndim > 1:
        # mix down to mono
        wav = wav.mean(axis=1)
    if sr != target_sr:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=target_sr)
    return _normalize(wav)


def load_audio_from_array(
    wav: np.ndarray, sr: int, target_sr: int = TARGET_SR
) -> np.ndarray:
    """Same as :func:`load_audio` but for an in-memory array (e.g. decoded
    upload). Useful for the API layer which receives raw bytes."""
    wav = np.asarray(wav, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != target_sr:
        wav = librosa.resample(wav, orig_sr=sr, target_sr=target_sr)
    return _normalize(wav)


def _normalize(wav: np.ndarray) -> np.ndarray:
    """Peak-normalise to avoid clipping while keeping silence at zero."""
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak > 1e-6:
        wav = wav / peak
    return wav.astype("float32")


def trim_silence(wav: np.ndarray, top_db: float = 30.0) -> np.ndarray:
    """Trim leading/trailing silence so alignment isn't thrown off by
    differing record-button latencies between reference and learner."""
    if wav.size == 0:
        return wav
    trimmed, _ = librosa.effects.trim(wav, top_db=top_db)
    return trimmed if trimmed.size else wav


def trim_silence_with_offset(
    wav: np.ndarray, top_db: float = 30.0, sr: int = TARGET_SR
) -> tuple[np.ndarray, float]:
    """Like :func:`trim_silence` but also return the leading-silence offset in
    seconds that was removed from the front. Callers that later want to map
    trimmed-audio timestamps back onto the original (untrimmed) recording — e.g.
    to replay a sentence-sized slice of the learner's own upload — add this
    offset to their trimmed-relative times."""
    if wav.size == 0:
        return wav, 0.0
    trimmed, index = librosa.effects.trim(wav, top_db=top_db)
    if trimmed.size == 0:
        return wav, 0.0
    return trimmed, float(index[0]) / float(sr)
