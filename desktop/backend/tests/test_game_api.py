"""API tests for the Survival beta-collection endpoints (FR-22/25/27).

Whisper is stubbed out: these tests pin the endpoint contract, the persistence
path and the three red lines — none of which depend on what the decoder heard.
Whether the decoder hears well enough is R-14 G2, and that is measured by
scripts/game_asr_gate.py against real recordings, not asserted here.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.core import game_store
from backend.main import app

client = TestClient(app)


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NATIVELINGO_DATA_DIR", str(tmp_path))
    return str(tmp_path)


@pytest.fixture()
def fake_asr(monkeypatch):
    """Replace the decoder with a scripted one. Returns a setter so each test
    chooses the transcript, exercising hit / partial / miss without audio."""
    from backend.core import game_transcribe

    state = {"text": "i want bread", "low": False}

    def fake(wav, scenario=None):
        return {
            "text": state["text"],
            "words": [{"word": w, "start": 0.0, "end": 0.1, "probability": 0.9}
                      for w in state["text"].split()],
            "avg_logprob": -0.3,
            "no_speech_prob": 0.01,
            "low_confidence": state["low"],
            "decode": {"model": "base.en", "beam_size": 5, "vad_filter": False,
                       "condition_on_previous_text": False,
                       "hotwords": " ".join(
                           __import__("backend.core.game_scenario", fromlist=["x"])
                           .hotword_terms(scenario or {})),
                       "language": "en"},
        }

    monkeypatch.setattr(game_transcribe, "transcribe_utterance", fake)
    return state


def _wav_bytes(seconds: float = 1.5) -> bytes:
    sr = 16000
    t = np.arange(int(sr * seconds)) / sr
    wav = (0.2 * np.sin(2 * np.pi * 200 * t)).astype("float32")
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _attempt(scenario_id="food-ask-bread", speaker="s01"):
    return client.post(
        "/game/attempt",
        data={"scenario_id": scenario_id, "speaker": speaker},
        files={"learner": ("clip.wav", _wav_bytes(), "audio/wav")},
    )


def test_scenario_withholds_the_english_answer():
    res = client.get("/game/scenario", params={"tier": "infant"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["situation_zh"]
    # The learner must produce the English themselves — leaking either the
    # English situation or the reference answer would void the exercise.
    assert "situation_en" not in body
    assert "reference_answer" not in body
    assert "slots" not in body  # only zh hints, never the accept sets
    for hint in body["slot_hints"]:
        assert "accept" not in hint


def test_scenario_does_not_repeat_within_a_session():
    seen = []
    for _ in range(5):
        res = client.get("/game/scenario",
                         params={"tier": "infant", "session": "no-repeat-test"})
        assert res.status_code == 200, res.text
        seen.append(res.json()["id"])
    assert len(set(seen)) == len(seen), f"scenario repeated: {seen}"


def test_unknown_tier_is_404():
    assert client.get("/game/scenario", params={"tier": "nope"}).status_code == 404


def test_attempt_scores_persists_and_replies(data_dir, fake_asr):
    res = _attempt()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["delivery"] == 85.0 and body["delivered"] is True
    assert body["npc"]["band"] == "hit" and body["npc"]["line"]
    assert body["reward"]["quality"] == "plain"
    assert body["transcript"] == "i want bread"

    aid = body["attempt_id"]
    stored = game_store.load_attempt(aid)
    assert stored["speaker"] == "s01"
    assert stored["scenario_id"] == "food-ask-bread"
    assert stored["tier"] == "infant"
    # The decode settings ride with the attempt: a clip transcribed under
    # different settings is a different measurement.
    assert stored["decode"]["beam_size"] == 5
    assert stored["decode"]["vad_filter"] is False
    assert "bread" in stored["decode"]["hotwords"]
    # ... and the audio itself is on disk, at 16 kHz mono, ready for the gates.
    wav, sr = sf.read(game_store.attempt_wav_path(aid), dtype="float32")
    assert sr == 16000 and wav.ndim == 1 and wav.size > 0


def test_attempt_partial_and_miss_bands(data_dir, fake_asr):
    fake_asr["text"] = "bread"
    body = _attempt().json()
    assert body["npc"]["band"] == "partial" and body["delivered"] is False
    assert body["reward"]["quality"] == "scrap"

    fake_asr["text"] = "hello there"
    body = _attempt().json()
    assert body["npc"]["band"] == "miss" and body["delivery"] == 0.0
    # Nothing earned, but §5.4 spends no attempt.
    assert body["reward"]["quality"] is None
    assert body["reward"]["retry_free"] is True


def test_attempt_response_carries_no_uncalibrated_score(data_dir, fake_asr):
    """红线 3: delivery is G1's criterion and ships; nothing else may."""
    body = _attempt().json()
    forbidden = {"fluency", "naturalness", "idiomaticity", "accuracy",
                 "nativeness", "score", "地道度"}
    assert not forbidden & set(body)
    assert not forbidden & set(body["npc"])


def test_attempt_rejects_empty_and_unknown(data_dir, fake_asr):
    res = client.post("/game/attempt", data={"scenario_id": "food-ask-bread"},
                      files={"learner": ("clip.wav", b"", "audio/wav")})
    assert res.status_code == 400
    res = client.post("/game/attempt", data={"scenario_id": "not-a-scenario"},
                      files={"learner": ("clip.wav", _wav_bytes(), "audio/wav")})
    assert res.status_code == 404


def test_correction_reroutes_and_keeps_both_texts(data_dir, fake_asr):
    """FR-27. The (B) case: the learner said bread, the instrument wrote bit."""
    fake_asr["text"] = "me want bit"
    aid = _attempt().json()["attempt_id"]

    res = client.post(f"/game/attempt/{aid}/correct",
                      json={"corrected_text": "me want bread",
                            "learner_claims_correct": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["delivery"] == 85.0 and body["delivered"] is True
    assert body["retry_free"] is True

    attempt = game_store.load_attempt(aid)
    assert attempt["transcript"] == "me want bit"  # instrument output preserved
    correction = game_store.load_correction(aid)
    assert correction["corrected_text"] == "me want bread"
    assert correction["asr_text"] == "me want bit"
    # Delivery rose => the instrument probably lost a word that was said, so this
    # is an ASR miss (G2's business), not a pronunciation problem.
    assert correction["triage_hint"] == "asr_miss"
    # The learner's own claim is recorded but never promoted to an annotation.
    assert correction["learner_claims_correct"] is True
    assert "well_pronounced" not in correction


def test_correction_that_does_not_help_routes_to_pronunciation(data_dir, fake_asr):
    """The (A) case: correcting changes nothing, so the learner likely did not
    produce the word — that routes to the Speaking module, not to G2."""
    fake_asr["text"] = "hello there"
    aid = _attempt().json()["attempt_id"]
    res = client.post(f"/game/attempt/{aid}/correct",
                      json={"corrected_text": "hello there friend"})
    assert res.status_code == 200, res.text
    assert game_store.load_correction(aid)["triage_hint"] == "pronunciation"


def test_correction_validates_input(data_dir, fake_asr):
    aid = _attempt().json()["attempt_id"]
    assert client.post(f"/game/attempt/{aid}/correct",
                       json={"corrected_text": "   "}).status_code == 400
    assert client.post("/game/attempt/..%2Fescape/correct",
                       json={"corrected_text": "x"}).status_code in (400, 404)
    assert client.post("/game/attempt/deadbeef/correct",
                       json={"corrected_text": "x"}).status_code == 404


def test_export_feeds_both_gates(data_dir, fake_asr):
    fake_asr["text"] = "me want bit"
    aid = _attempt().json()["attempt_id"]
    client.post(f"/game/attempt/{aid}/correct",
                json={"corrected_text": "me want bread"})

    res = client.get("/game/export")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 1 and body["corrected_count"] == 1
    row = body["delivery_rows"][0]
    assert row["response_text"] == "me want bit" and row["delivered"] == ""
    entry = body["asr_manifest"][0]
    assert entry["clip"] == f"{aid}.wav"
    assert entry["expected_keywords"] == [] and entry["well_pronounced"] == []
    # Audio is referenced by path, never served: it carries identifiable voices.
    assert "wav_base64" not in entry and "audio" not in entry


def test_no_review_endpoint_exists():
    """The beta build makes zero outbound requests, so NFR-6's whitelist surface
    is empty this round. /game/review is FR-23 and out of scope."""
    paths = {r.path for r in app.routes}
    assert "/game/review" not in paths
    assert {"/game/scenario", "/game/attempt", "/game/export"} <= paths


def test_all_game_endpoints_require_a_token(data_dir, monkeypatch):
    """The sidecar is local-only but other local processes must not drive it.

    `_TOKEN` is read from the environment at import time, so patch the module
    attribute — setting the env var here would be too late to matter."""
    from backend import main as main_mod

    monkeypatch.setattr(main_mod, "_TOKEN", "secret-token")
    bare = TestClient(app)
    assert bare.get("/game/scenario").status_code == 401
    assert bare.post("/game/attempt", data={"scenario_id": "food-ask-bread"},
                     files={"learner": ("c.wav", _wav_bytes(), "audio/wav")}
                     ).status_code == 401
    assert bare.post("/game/attempt/abc/correct",
                     json={"corrected_text": "x"}).status_code == 401
    assert bare.get("/game/export").status_code == 401
