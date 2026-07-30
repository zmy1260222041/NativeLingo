"""API tests that lock server-owned photo context and part selection."""
from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from PIL import Image

from backend.core import parts, scenario, vision
from backend import main
from backend.main import app

client = TestClient(app)


def _photo_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(output, format="JPEG")
    return output.getvalue()


def test_parts_and_scenario_use_server_owned_detection_context(monkeypatch):
    monkeypatch.setattr(
        vision,
        "detect",
        lambda _image: [
            {
                "id": 0,
                "label_en": "bicycle",
                "label_zh": "自行车",
                "score": 0.9,
                "box": [10, 10, 80, 60],
            },
            {
                "id": 1,
                "label_en": "car",
                "label_zh": "汽车",
                "score": 0.8,
                "box": [90, 10, 20, 20],
            },
        ],
    )
    monkeypatch.setattr(
        parts,
        "analyze_parts",
        lambda _crop, en, zh: {
            "crop_context": f"A {en} with a handlebar.",
            "parts": [{"label_en": "handlebar", "label_zh": "车把"}],
        },
    )
    captured = {}

    def fake_generate(label_en, label_zh, **kwargs):
        captured.update(label_en=label_en, label_zh=label_zh, **kwargs)
        return [{"en": "Grip the handlebar.", "zh": "握紧车把。"}]

    monkeypatch.setattr(scenario, "generate", fake_generate)

    analyzed = client.post(
        "/memorize/analyze",
        files={"photo": ("photo.jpg", _photo_bytes(), "image/jpeg")},
    )
    assert analyzed.status_code == 200, analyzed.text
    photo_id = analyzed.json()["photo_id"]

    part_result = client.post(
        "/memorize/parts",
        json={"photo_id": photo_id, "object_id": 0},
    )
    assert part_result.status_code == 200, part_result.text
    assert part_result.json()["crop_context"].startswith("A bicycle")

    generated = client.post(
        "/memorize/scenario",
        json={"photo_id": photo_id, "object_id": 0, "part_en": "handlebar"},
    )
    assert generated.status_code == 200, generated.text
    assert captured["label_en"] == "bicycle"
    assert captured["part_en"] == "handlebar"
    assert captured["part_zh"] == "车把"
    assert captured["photo_context"] == "A bicycle with a handlebar."
    assert captured["scene_objects"] == ["car"]

    forged = client.post(
        "/memorize/scenario",
        json={"photo_id": photo_id, "object_id": 0, "part_en": "jet engine"},
    )
    assert forged.status_code == 400


def test_macro_detection_times_out_instead_of_leaving_a_spinner(monkeypatch):
    monkeypatch.setattr(main, "_MEMORIZE_REQUEST_TIMEOUT_S", 0.01)

    def slow_detect(_image):
        time.sleep(0.05)
        return []

    monkeypatch.setattr(vision, "detect", slow_detect)
    response = client.post(
        "/memorize/analyze",
        files={"photo": ("photo.jpg", _photo_bytes(), "image/jpeg")},
    )
    assert response.status_code == 504
    assert "超过15秒" in response.json()["detail"]


def test_analyze_returns_final_yoloe_result_without_background_enrichment(monkeypatch):
    monkeypatch.setattr(
        vision,
        "detect",
        lambda _image: [
            {
                "id": 0,
                "label_en": "clock",
                "label_zh": "时钟",
                "score": 0.9,
                "box": [0, 0, 20, 20],
            }
        ],
    )
    analyzed = client.post(
        "/memorize/analyze",
        files={"photo": ("photo.jpg", _photo_bytes(), "image/jpeg")},
    )
    assert analyzed.status_code == 200
    payload = analyzed.json()
    assert "enrichment" not in payload
    assert [item["label_en"] for item in payload["objects"]] == ["clock"]
    assert client.get(f"/memorize/enrichment/{payload['photo_id']}").status_code == 404
