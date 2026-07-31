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
        lambda _crop, en, zh, **_kwargs: {
            "crop_context": f"A {en} with a handlebar.",
            "parts": [
                {
                    "label_en": "handlebar",
                    "label_zh": "车把",
                    "box": [10.0, 8.0, 50.0, 24.0],
                }
            ],
        },
    )
    captured = {}

    def fake_generate(label_en, label_zh, **kwargs):
        captured.update(label_en=label_en, label_zh=label_zh, **kwargs)
        return {
            "scene": "Beside a car",
            "turns": [
                {"speaker": "A", "en": "Can I try your bicycle?", "zh": "我能骑一下你的自行车吗？"},
                {"speaker": "B", "en": "Sure — grip the handlebar.", "zh": "好，握紧车把。"},
            ],
        }

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
    assert part_result.json()["crop_box"] == [2, 4, 96, 72]
    assert part_result.json()["crop_size"] == [96, 72]
    assert part_result.json()["parts"][0]["box"] == [10.0, 8.0, 50.0, 24.0]

    generated = client.post(
        "/memorize/scenario",
        json={"photo_id": photo_id, "object_id": 0, "part_en": "handlebar"},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert "turns" in payload and "scene" in payload
    assert "sentences" not in payload
    assert len(payload["turns"]) >= 2
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


def test_container_contents_are_server_owned_depth_one_leaves(monkeypatch):
    monkeypatch.setattr(
        vision,
        "detect",
        lambda _image: [
            {
                "id": 0,
                "label_en": "cabinet",
                "label_zh": "柜子",
                "score": 0.9,
                "box": [10, 5, 100, 70],
            }
        ],
    )
    captured_box = {}

    def fake_analyze(_crop, en, zh, *, object_box=None):
        captured_box["value"] = object_box
        return {
            "crop_context": "A cabinet with a gold statue.",
            "parts": [{"label_en": "shelf", "label_zh": "架子"}],
            "contents": [
                {
                    "label_en": "gold statue",
                    "label_zh": "金色雕像",
                    "canonical_label": "statue",
                    "box": [30.0, 10.0, 80.0, 40.0],
                }
            ],
            "is_container": True,
        }

    monkeypatch.setattr(parts, "analyze_parts", fake_analyze)
    captured_scenario = {}

    def fake_generate(label_en, label_zh, **kwargs):
        captured_scenario.update(label_en=label_en, label_zh=label_zh, **kwargs)
        return {
            "scene": "At the cabinet",
            "turns": [
                {"speaker": "A", "en": "Is that a gold statue?", "zh": "那是金色雕像吗？"},
                {"speaker": "B", "en": "Yes, it is.", "zh": "是的。"},
            ],
        }

    monkeypatch.setattr(scenario, "generate", fake_generate)
    analyzed = client.post(
        "/memorize/analyze",
        files={"photo": ("photo.jpg", _photo_bytes(), "image/jpeg")},
    )
    photo_id = analyzed.json()["photo_id"]
    details = client.post(
        "/memorize/parts",
        json={"photo_id": photo_id, "object_id": 0},
    )
    assert details.status_code == 200, details.text
    assert captured_box["value"] == [10.0, 5.0, 110.0, 75.0]
    content = details.json()["contents"][0]
    assert content["parent_id"] == 0
    assert content["relation"] == "inside"
    assert content["depth"] == 1
    assert content["kind"] == "content"

    generated = client.post(
        "/memorize/scenario",
        json={
            "photo_id": photo_id,
            "object_id": 0,
            "part_en": "gold statue",
        },
    )
    assert generated.status_code == 200, generated.text
    assert captured_scenario["part_en"] == "gold statue"
    assert captured_scenario["part_zh"] == "金色雕像"

    # Contents have no object_id and therefore cannot become recursive detail
    # roots through the server-owned whole-object endpoint.
    recursive = client.post(
        "/memorize/parts",
        json={"photo_id": photo_id, "object_id": 99},
    )
    assert recursive.status_code == 404


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
