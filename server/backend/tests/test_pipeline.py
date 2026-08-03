"""Integration test for the full MVP pipeline (Track B + prosody + feedback)."""
from __future__ import annotations

from backend.core.pipeline import analyze_full
from backend.tests.conftest import SENTENCE, requires_say


@requires_say
def test_analyze_full_payload_shape(synth):
    ref = synth(SENTENCE, voice="Samantha")
    learner = synth(SENTENCE, voice="Daniel")
    payload = analyze_full(ref, learner)

    # required keys for the frontend
    for key in (
        "overall_score",
        "overall_band",
        "accuracy",
        "fluency",
        "speech_rate_ratio",
        "tips",
        "problem_regions",
        "prosody",
    ):
        assert key in payload, f"missing key: {key}"

    assert 0.0 <= payload["overall_score"] <= 100.0
    assert isinstance(payload["tips"], list) and payload["tips"]
    assert payload["overall_band"] in ("excellent", "good", "fair", "needs work")


@requires_say
def test_wrong_text_produces_actionable_tips(synth):
    ref = synth(SENTENCE, voice="Samantha")
    wrong = synth("Totally different sentence about nothing.", voice="Samantha")
    payload = analyze_full(ref, wrong)
    # low-accuracy read should yield concrete tips and flagged regions
    assert payload["accuracy"] < 80.0
    assert len(payload["tips"]) >= 1
