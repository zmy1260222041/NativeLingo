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


def test_parse_requires_dialogue_json_and_has_no_canned_fallback():
    fenced = (
        '```json\n{"scene":"Beside a car","turns":['
        '{"speaker":"A","en":"Grip the handle.","zh":"握紧把手。"}'
        ']}```'
    )
    assert scenario._parse(fenced) == {
        "scene": "Beside a car",
        "turns": [{"speaker": "A", "en": "Grip the handle.", "zh": "握紧把手。"}],
    }
    with pytest.raises(ValueError):
        scenario._parse("I use my handle every day.")
    with pytest.raises(ValueError):
        scenario._parse('{"sentences":[{"en":"English only","zh":""}]}')
    with pytest.raises(ValueError):
        scenario._parse('{"scene":"Beside a car","turns":[]}')


def test_generate_includes_photo_part_and_nearby_objects(monkeypatch):
    captured = {}

    def fake_chat(messages, schema, max_tokens=384, **kwargs):
        captured["messages"] = messages
        captured["schema"] = schema
        return {
            "scene": "Beside a car",
            "turns": [
                {"speaker": "A", "en": "Is the handlebar straight?", "zh": "车把正吗？"},
                {"speaker": "B", "en": "Yes, it looks fine.", "zh": "嗯，看着没问题。"},
            ],
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
    assert result["turns"][0]["zh"]


def test_dialogue_gate_rejects_runons_partial_words_and_single_speaker():
    # valid: two speakers, target "bus" appears with word boundaries
    assert scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "I hold the bus handle.", "zh": "我握住公交车把手。"},
                {"speaker": "B", "en": "Careful, it's heavy.", "zh": "小心，很重。"},
            ]
        },
        "bus",
    )
    # invalid: a run-on turn (two sentences) is rejected
    assert not scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "The bus is parked. People walk nearby.", "zh": "公交车停着。"},
                {"speaker": "B", "en": "I see it.", "zh": "我看到了。"},
            ]
        },
        "bus",
    )
    # invalid: "business" must not satisfy the target "bus" (word boundary)
    assert not scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "I discuss business.", "zh": "我讨论生意。"},
                {"speaker": "B", "en": "Sounds good.", "zh": "听起来不错。"},
            ]
        },
        "bus",
    )
    # invalid: only one distinct speaker
    assert not scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "I see the bus.", "zh": "我看到公交车。"},
                {"speaker": "A", "en": "It is red.", "zh": "它是红色的。"},
            ]
        },
        "bus",
    )
    # multi-word target: a head-noun hit ("frame") satisfies "picture frame"
    assert scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "Is this frame level?", "zh": "这个相框正吗？"},
                {"speaker": "B", "en": "Looks straight.", "zh": "看着正。"},
            ]
        },
        "picture frame",
    )
    # but a dialogue mentioning neither token of the target is still rejected
    assert not scenario._valid_dialogue(
        {
            "turns": [
                {"speaker": "A", "en": "Sure thing, I'll check it out.", "zh": "好的，我看看。"},
                {"speaker": "B", "en": "Thanks a lot.", "zh": "多谢。"},
            ]
        },
        "picture frame",
    )


def test_turn_normalization_trims_small_model_run_on():
    assert scenario._normalize_turn(
        {
            "speaker": "A",
            "en": "I see the bus beside a car. Three people stand nearby.",
            "zh": "我看到汽车旁的公交车。三个人站在附近。",
        }
    ) == {
        "speaker": "A",
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


def test_extract_contents_uses_container_relation_prompt(monkeypatch):
    captured = {}

    def fake_chat(messages, schema, max_tokens=384, **kwargs):
        captured["messages"] = messages
        captured["schema"] = schema
        return {"contents": ["gold statue", "award", "gold statue"]}

    monkeypatch.setattr(scenario, "_chat_json", fake_chat)
    assert scenario.extract_contents(
        "cabinet",
        "A cabinet has a gold statue and several awards.",
    ) == ["gold statue", "award"]
    prompt = captured["messages"][-1]["content"]
    assert '"container": "cabinet"' in prompt
    assert "gold statue" in prompt


def test_verify_file_rejects_wrong_size(tmp_path):
    path = tmp_path / "tiny.gguf"
    path.write_bytes(b"abc")
    with pytest.raises(model_assets.ModelIntegrityError):
        model_assets.verify_file(str(path), 4, "0" * 64)
