"""Pytest fixtures: synthesize speech test audio using macOS `say`.

We generate controlled samples so we can assert that Track B behaves correctly:
same text/same voice scores high, same text/different voice still scores high
(speaker-invariance — the crux of the reverse-evaluation idea), wrong words get
flagged, and inserted pauses hurt fluency.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import numpy as np
import pytest

from backend.core.audio_io import load_audio, trim_silence

SAY = shutil.which("say")
requires_say = pytest.mark.skipif(SAY is None, reason="macOS `say` not available")


def _synth(text: str, voice: str, rate: int, out_aiff: str) -> str:
    subprocess.run(
        [SAY, "-v", voice, "-r", str(rate), "-o", out_aiff, text],
        check=True,
        capture_output=True,
    )
    return out_aiff


@pytest.fixture(scope="session")
def synth(tmp_path_factory):
    """Returns a function (text, voice, rate) -> 16kHz mono waveform array,
    caching by argument tuple within the session."""
    if SAY is None:
        pytest.skip("macOS `say` not available")
    d = tmp_path_factory.mktemp("audio")
    cache: dict[tuple, np.ndarray] = {}

    def make(text: str, voice: str = "Samantha", rate: int = 170) -> np.ndarray:
        key = (text, voice, rate)
        if key in cache:
            return cache[key]
        fname = f"{abs(hash(key))}.aiff"
        path = os.path.join(str(d), fname)
        _synth(text, voice, rate, path)
        wav = trim_silence(load_audio(path))
        cache[key] = wav
        return wav

    return make


SENTENCE = "The quick brown fox jumps over the lazy dog."
