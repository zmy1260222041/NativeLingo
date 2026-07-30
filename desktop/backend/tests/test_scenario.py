"""Contract tests for the fixed Qwen GGUF scenario path (FR-15)."""
from __future__ import annotations

import json

import pytest

from backend.core import model_assets, scenario


def test_fixed_qwen_artifact_manifest():
    assert scenario.MODEL == "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    assert scenario.MODEL_FILE == "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    assert model_assets.QWEN_SIZE == 491_400_032
    assert len(model_assets.QWEN_SHA256) == 64
    assert model_assets.FLORENCE_ORIGIN == "microsoft/Florence-2-base-ft"
    assert model_assets.FLORENCE_REPO == "florence-community/Florence-2-base-ft"
    assert model_assets.YOLO_REPO == "ultralytics/assets"
    assert model_assets.YOLO_SOURCE_FILENAME == "yoloe-26s-seg-pf.pt"
    assert model_assets.YOLO_SIZE == 45_190_231
    assert len(model_assets.YOLO_SHA256) == 64


def test_parse_requires_bilingual_json_and_has_no_canned_fallback():
    fenced = '```json\n{"sentences":[{"en":"Grip the handle.","zh":"握紧把手。"}]}\n```'
    assert scenario._parse(fenced) == [{"en": "Grip the handle.", "zh": "握紧把手。"}]
    with pytest.raises(ValueError):
        scenario._parse("I use my handle every day.")
    with pytest.raises(ValueError):
        scenario._parse('{"sentences":[{"en":"English only","zh":""}]}')


def test_generate_includes_photo_part_and_nearby_objects(monkeypatch):
    captured = {}

    def fake_chat(messages, schema, max_tokens=384):
        captured["messages"] = messages
        captured["schema"] = schema
        return {
            "sentences": [
                {
                    "en": "I grip the handlebar as the bicycle rolls beside the car.",
                    "zh": "自行车从汽车旁经过时，我握紧车把。",
                }
            ]
        }

    monkeypatch.setattr(scenario, "_chat_json", fake_chat)
    result = scenario.generate(
        "bicycle",
        "自行车",
        photo_context="A bicycle with a visible handlebar and front wheel.",
        scene_objects=["car", "person"],
        part_en="handlebar",
        part_zh="车把",
    )
    prompt = captured["messages"][-1]["content"]
    assert "Target: handlebar" in prompt
    assert "visible handlebar" in prompt
    assert "Other detected objects: car, person" in prompt
    assert result[0]["zh"]


def test_memory_sentence_gate_rejects_caption_copy_and_partial_word():
    assert scenario._valid_memory_sentence(
        {"en": "I hold the bus handle.", "zh": "我握住公交车把手。"},
        "bus",
    )
    assert not scenario._valid_memory_sentence(
        {"en": "The bus is parked. People walk nearby.", "zh": "公交车停着。"},
        "bus",
    )
    assert not scenario._valid_memory_sentence(
        {"en": "I discuss business.", "zh": "我讨论生意。"},
        "bus",
    )


def test_memory_sentence_normalization_trims_small_model_run_on():
    assert scenario._normalize_memory_sentence(
        {
            "en": "I see the bus beside a car. Three people stand nearby.",
            "zh": "我看到汽车旁的公交车。三个人站在附近。",
        }
    ) == {
        "en": "I see the bus beside a car.",
        "zh": "我看到汽车旁的公交车。",
    }


def test_relevant_context_prefers_sentence_with_target_object():
    context = (
        "Three people stand outside. "
        "A bus is parked beside a building. "
        "Trees are visible in the background."
    )
    assert scenario._relevant_context(context, "bus", "bus") == (
        "A bus is parked beside a building."
    )


def test_translate_terms_uses_structured_result(monkeypatch):
    monkeypatch.setattr(
        scenario,
        "_chat_json",
        lambda *_args, **_kwargs: {
            "translations": [
                {"en": "front fork", "zh": "前叉"},
                {"en": "not requested", "zh": "忽略"},
            ]
        },
    )
    assert scenario.translate_terms(["front fork"]) == {"front fork": "前叉"}


def test_verify_file_rejects_wrong_size(tmp_path):
    path = tmp_path / "tiny.gguf"
    path.write_bytes(b"abc")
    with pytest.raises(model_assets.ModelIntegrityError):
        model_assets.verify_file(str(path), 4, "0" * 64)
