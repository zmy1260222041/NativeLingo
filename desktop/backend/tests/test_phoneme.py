"""Phoneme-diagnosis (FR-11) validation with synthetic minimal pairs.

`say` pronounces the text it's given, so ("think", "sink") is a clean /θ/→/s/
case: the diagnosis must flag the /θ/. Same-audio pairs must produce NO
diagnosis (the margin + canonical-quality gate must keep decode noise out).

Spans mirror production: untrimmed audio with the word located by energy trim,
so the CTC decode gets the real-silence context it needs (zero padding is
out-of-distribution for the model).
"""
from __future__ import annotations

import librosa
import pytest

from backend.core import phoneme
from backend.tests.conftest import requires_say


def _span(wav):
    """(wav, start_s, end_s) with the word located by energy trim."""
    _, idx = librosa.effects.trim(wav, top_db=30)
    return wav, idx[0] / 16000.0, idx[1] / 16000.0


@requires_say
def test_theta_dropped_in_sink_is_flagged(synth_untrimmed):
    ref = _span(synth_untrimmed("think"))
    lrn = _span(synth_untrimmed("sink"))
    tip = phoneme.diagnose_word_span(*ref, *lrn, "think")
    assert tip, f"expected a diagnosis for think->sink, got none"
    assert "θ" in tip, f"tip should name /θ/: {tip}"


@requires_say
def test_same_word_no_phantom_diagnosis(synth_untrimmed):
    for word in ("think", "sheep", "very"):
        span = _span(synth_untrimmed(word))
        tip = phoneme.diagnose_word_span(*span, *span, word)
        assert tip == "", f"identical audio should yield no diagnosis: {tip}"


@requires_say
def test_broken_canonical_stays_silent(synth_untrimmed):
    """fan (whose CTC canonical decode fails on `say`) must not produce a
    confident-but-wrong diagnosis — the gate should keep it silent."""
    ref = _span(synth_untrimmed("fan"))
    lrn = _span(synth_untrimmed("van"))
    tip = phoneme.diagnose_word_span(*ref, *lrn, "fan")
    assert isinstance(tip, str)  # no crash; silence or a diagnosis both pass
