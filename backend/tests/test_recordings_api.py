"""API test for the learner-recording store (FR-8 exact clip replay).

The regression this guards: learner word/sentence replay used to seek inside
the frontend blob with ~250 ms granularity; the /recordings + /recordings/{id}/clip
endpoints cut sample-accurate WAV slices server-side instead.
"""
from __future__ import annotations

import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _wav_bytes(wav: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, wav, 16000, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_store_and_clip_recording_sample_accurate():
    sr = 16000
    t = np.arange(sr * 3) / sr  # 3 s
    wav = (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32")

    res = client.post(
        "/recordings",
        files={"learner": ("learner.wav", _wav_bytes(wav), "audio/wav")},
    )
    assert res.status_code == 200, res.text
    rid = res.json()["recording_id"]
    assert res.json()["duration_s"] == 3.0

    # cut [1.0, 2.0) — must be exactly 16000 samples, content matching the source
    res = client.get(f"/recordings/{rid}/clip", params={"start": 1.0, "end": 2.0})
    assert res.status_code == 200, res.text
    clip, clip_sr = sf.read(io.BytesIO(res.content), dtype="float32")
    assert clip_sr == sr
    assert len(clip) == sr  # exactly one second — no ~250 ms slop
    # the store decodes via load_audio_from_array, which peak-normalises to 1.0
    expected = wav[sr : 2 * sr] / np.abs(wav).max()
    np.testing.assert_allclose(clip, expected, atol=1e-3)


def test_clip_rejects_bad_id_and_range():
    assert client.get("/recordings/not-a-rid/clip",
                      params={"start": 0, "end": 1}).status_code == 400
    assert client.get(f"/recordings/{'0' * 32}/clip",
                      params={"start": 0, "end": 1}).status_code == 404
    # valid id format but backwards range -> id check happens after range check
    sr = 16000
    wav = np.zeros(sr // 2, dtype="float32") + 0.01
    res = client.post("/recordings",
                      files={"learner": ("l.wav", _wav_bytes(wav), "audio/wav")})
    rid = res.json()["recording_id"]
    assert client.get(f"/recordings/{rid}/clip",
                      params={"start": 1.0, "end": 0.5}).status_code == 400
