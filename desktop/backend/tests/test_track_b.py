"""Track B validation tests.

These encode the product hypotheses as executable checks. The most important is
``test_speaker_invariance``: two *different* voices reading the *same correct
text* must still score high. If that fails, the speaker factor isn't being
removed and the reverse-evaluation idea doesn't hold.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.core.pipeline import analyze_arrays
from backend.tests.conftest import SENTENCE, requires_say


@requires_say
def test_same_voice_same_text_scores_high(synth):
    """Identical voice + text read twice -> high accuracy and fluency."""
    ref = synth(SENTENCE, voice="Samantha")
    learner = synth(SENTENCE, voice="Samantha")
    res = analyze_arrays(ref, learner)
    assert res.accuracy >= 85.0, f"accuracy too low: {res.accuracy}"
    assert res.fluency >= 70.0, f"fluency too low: {res.fluency}"


@requires_say
def test_speaker_invariance(synth):
    """THE key test: different voices, same correct text -> still high accuracy.

    This proves the speaker (timbre) factor is normalised away rather than
    being mistaken for mispronunciation.
    """
    ref = synth(SENTENCE, voice="Samantha")
    learner = synth(SENTENCE, voice="Daniel")  # different speaker
    res = analyze_arrays(ref, learner)
    assert res.accuracy >= 70.0, (
        f"speaker normalisation failing: different voices reading the same "
        f"text scored only {res.accuracy}"
    )


@requires_say
def test_wrong_words_lower_accuracy_and_flag_region(synth):
    """Reading different/wrong words should lower accuracy vs the correct read,
    and produce at least one flagged problem region."""
    ref = synth(SENTENCE, voice="Samantha")
    correct = synth(SENTENCE, voice="Samantha")
    wrong = synth(
        "The slow purple cat sleeps under the busy table.", voice="Samantha"
    )
    res_correct = analyze_arrays(ref, correct)
    res_wrong = analyze_arrays(ref, wrong)

    assert res_wrong.accuracy < res_correct.accuracy - 10.0, (
        f"wrong-text accuracy ({res_wrong.accuracy}) not clearly below "
        f"correct ({res_correct.accuracy})"
    )
    assert len(res_wrong.problems) >= 1, "expected at least one problem region"


@requires_say
def test_slower_speech_changes_rate_ratio(synth):
    """Reading slower should stretch the learner relative to the reference.

    Note `say -r` scaling is non-linear and silence trimming removes some of
    the gap, so we assert a clear directional change rather than an exact
    factor.
    """
    ref = synth(SENTENCE, voice="Samantha", rate=200)
    slow = synth(SENTENCE, voice="Samantha", rate=80)  # much slower
    res = analyze_arrays(ref, slow)
    assert res.speech_rate_ratio > 1.1, (
        f"slow speech should stretch the learner; ratio={res.speech_rate_ratio}"
    )


@requires_say
def test_scores_are_bounded(synth):
    """Scores must always stay within [0, 100]."""
    ref = synth(SENTENCE, voice="Samantha")
    learner = synth("Completely unrelated babble noise here.", voice="Daniel")
    res = analyze_arrays(ref, learner)
    for val in (res.accuracy, res.fluency):
        assert 0.0 <= val <= 100.0
