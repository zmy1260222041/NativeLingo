"""Empirical layer-selection experiment for the SSL encoder (v0.2).

For each candidate layer configuration we measure, over synthetic `say` audio:

* cost_same      — same voice, same text read twice       (want: low)
* cost_cross     — different voice, same text             (want: low; speaker invariance)
* cost_wrong     — different voice, different/wrong text  (want: high; error sensitivity)

and report the two margins that matter for the product:

* invariance gap = cost_cross - cost_same      (small => timbre removed)
* separability   = cost_wrong - cost_cross     (large => errors detected)

Usage: .venv/bin/python -m scripts.layer_comparison
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

from backend.core.audio_io import load_audio, trim_silence
from backend.core.ssl_encoder import SSLEncoder
from backend.core.speaker_norm import normalize_pair
from backend.core.align import dtw_align

SAY = shutil.which("say")

TEXTS = [
    "The quick brown fox jumps over the lazy dog.",
    "She sells sea shells by the sea shore.",
    "I would like a cup of coffee with milk and sugar.",
    "Learning a new language takes time and daily practice.",
]
WRONG_TEXTS = [
    "The slow purple cat sleeps under the busy table.",
    "He buys fresh bread at the market every Sunday.",
    "They drove the car into the big red garage.",
    "Reading many books improves your vocabulary quickly.",
]
VOICES = ["Samantha", "Daniel", "Karen", "Moira"]

CONFIGS: dict[str, tuple[int, ...] | None] = {
    "last (v0.1 default)": None,
    "layer 5": (5,),
    "mean 4-8": (4, 5, 6, 7, 8),
    "mean 3-10": (3, 4, 5, 6, 7, 8, 9, 10),
    "mean 6-9": (6, 7, 8, 9),
}


def synth(text: str, voice: str, out_dir: str) -> np.ndarray:
    path = os.path.join(out_dir, f"{abs(hash((text, voice)))}.aiff")
    if not os.path.exists(path):
        subprocess.run(
            [SAY, "-v", voice, "-o", path, text],
            check=True,
            capture_output=True,
        )
    return trim_silence(load_audio(path))


def path_cost(encoder: SSLEncoder, a: np.ndarray, b: np.ndarray) -> float:
    ea, eb = encoder.encode(a), encoder.encode(b)
    ea, eb = normalize_pair(ea, eb)
    return dtw_align(ea, eb).normalized_cost


def main() -> None:
    assert SAY, "macOS `say` required"
    tmp = tempfile.mkdtemp(prefix="nl_layers_")
    audio = {
        (t, v): synth(t, v, tmp) for t in TEXTS + WRONG_TEXTS for v in VOICES
    }

    print(f"{'config':<22}{'same':>8}{'cross':>8}{'wrong':>8}"
          f"{'inv_gap':>9}{'separab':>9}")
    for name, layers in CONFIGS.items():
        enc = SSLEncoder(layers=layers)
        same, cross, wrong = [], [], []
        for i, t in enumerate(TEXTS):
            v0, v1 = VOICES[0], VOICES[(i % (len(VOICES) - 1)) + 1]
            same.append(path_cost(enc, audio[(t, v0)], audio[(t, v0)]))
            cross.append(path_cost(enc, audio[(t, v0)], audio[(t, v1)]))
            wrong.append(path_cost(enc, audio[(t, v0)], audio[(WRONG_TEXTS[i], v1)]))
        cs, cc, cw = float(np.mean(same)), float(np.mean(cross)), float(np.mean(wrong))
        print(f"{name:<22}{cs:>8.3f}{cc:>8.3f}{cw:>8.3f}"
              f"{cc - cs:>9.3f}{cw - cc:>9.3f}")


if __name__ == "__main__":
    main()
