"""Speaker-factor removal (Track B).

The crux of the reverse-evaluation idea: the learner and the reference speaker
have different voices (timbre). That speaker factor lives in the SSL embedding
space and would otherwise be mistaken for "wrong pronunciation". We normalise it
away so that two *different* people reading the *same* correct text score high.

Two complementary normalisations:

1. Per-utterance mean/variance normalisation (CMVN-style) — removes the global
   speaker offset and channel/recording-level scale from each sequence
   independently.
2. (Optional) cosine-space comparison downstream — magnitude differences from
   loudness/voice are further suppressed by comparing directions, not lengths.

This module only does (1); the distance metric in ``score_b`` handles (2).
"""
from __future__ import annotations

import numpy as np

EPS = 1e-8


def cmvn(emb: np.ndarray) -> np.ndarray:
    """Per-utterance cepstral-mean-variance-style normalisation.

    Subtracts the per-dimension mean and divides by per-dimension std over the
    time axis. This removes the speaker/channel-constant component of each
    embedding sequence, leaving the time-varying content + prosody structure.
    """
    if emb.shape[0] == 0:
        return emb
    mean = emb.mean(axis=0, keepdims=True)
    std = emb.std(axis=0, keepdims=True)
    return ((emb - mean) / (std + EPS)).astype("float32")


def normalize_pair(
    ref_emb: np.ndarray, learner_emb: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Normalise both sequences independently so the comparison reflects
    content/prosody divergence rather than voice identity."""
    return cmvn(ref_emb), cmvn(learner_emb)
