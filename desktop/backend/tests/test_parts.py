"""Pure/unit tests for Florence output handling (FR-14)."""
from __future__ import annotations
from PIL import Image

from backend.core import parts, scenario


def test_dense_regions_are_defensive_and_filter_whole_object():
    raw = {
        "<DENSE_REGION_CAPTION>": {
            "labels": ["a bicycle", "Wheel", "wheel", "person", "handlebar", "bad"],
            "bboxes": [
                [0, 0, 100, 100],
                [5, 20, 45, 90],
                [6, 21, 44, 89],
                [0, 0, 10, 10],
                [20, 5, 80, 30],
                [2, 2, 1, 1],
            ],
        }
    }
    assert parts._dense_regions(raw, "bicycle") == [
        {"label": "wheel", "box": [5.0, 20.0, 45.0, 90.0]},
        {"label": "handlebar", "box": [20.0, 5.0, 80.0, 30.0]},
        {"label": "bad"},
    ]


def test_analyze_parts_combines_caption_regions_and_translation(monkeypatch):
    outputs = {
        "<MORE_DETAILED_CAPTION>": {
            "<MORE_DETAILED_CAPTION>": "A bicycle with a visible front wheel and handlebar."
        },
        "<DENSE_REGION_CAPTION>": {
            "<DENSE_REGION_CAPTION>": {
                "labels": ["bicycle", "front wheel", "handlebar"],
                "bboxes": [[0, 0, 100, 100], [5, 20, 45, 90], [20, 5, 80, 30]],
            }
        },
    }
    monkeypatch.setattr(parts, "_run_task", lambda _image, task: outputs[task])
    monkeypatch.setattr(
        scenario,
        "extract_parts",
        lambda object_label, caption, dense: ["front wheel", "handlebar", "bicycle", "handlebar"],
    )
    monkeypatch.setattr(
        scenario,
        "translate_terms",
        lambda terms: {"front wheel": "前轮"} if "front wheel" in terms else {},
    )

    result = parts.analyze_parts(Image.new("RGB", (100, 100)), "bicycle", "自行车")
    assert result["crop_context"].startswith("A bicycle")
    assert result["parts"] == [
        {
            "label_en": "front wheel",
            "label_zh": "前轮",
            "box": [5.0, 20.0, 45.0, 90.0],
        },
        {
            "label_en": "handlebar",
            "label_zh": "车把",
            "box": [20.0, 5.0, 80.0, 30.0],
        },
    ]


def test_analyze_parts_falls_back_only_to_visible_dense_regions(monkeypatch):
    monkeypatch.setattr(
        parts,
        "_run_task",
        lambda _image, task: (
            {task: "A mug on a table."}
            if task == "<MORE_DETAILED_CAPTION>"
            else {task: {"labels": ["mug", "handle"], "bboxes": [[0, 0, 20, 20], [1, 2, 5, 9]]}}
        ),
    )

    def fail(*_args):
        raise RuntimeError("LLM temporarily unavailable")

    monkeypatch.setattr(scenario, "extract_parts", fail)
    result = parts.analyze_parts(Image.new("RGB", (20, 20)), "mug", "杯子")
    assert result["parts"] == [
        {"label_en": "handle", "label_zh": "把手", "box": [1.0, 2.0, 5.0, 9.0]}
    ]


def test_nested_scene_objects_are_not_reported_as_parts():
    assert not parts._looks_like_component("man in the middle")
    assert not parts._looks_like_component("book")
    assert parts._looks_like_component("front wheel")
    assert parts._looks_like_component("derailleur")
    assert not parts._looks_like_component("footwear")
    assert not parts._looks_like_component("trousers")
