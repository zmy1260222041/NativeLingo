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


def test_compound_part_uses_local_suffix_translation(monkeypatch):
    monkeypatch.setattr(
        scenario,
        "translate_terms",
        lambda _terms: {},
    )
    assert parts._translate(["bicycle wheel", "cabinet door"]) == {
        "bicycle wheel": "车轮",
        "cabinet door": "门",
    }


def test_container_contents_require_caption_candidate_and_grounded_box(monkeypatch):
    prompts = []

    def fake_run(_image, task, prompt=""):
        prompts.append((task, prompt))
        if task == "<MORE_DETAILED_CAPTION>":
            return {
                task: (
                    "A cabinet has a gold statue on the top shelf and several "
                    "awards below."
                )
            }
        if task == "<DENSE_REGION_CAPTION>":
            return {
                task: {
                    "labels": ["cabinet", "shelf"],
                    "bboxes": [[0, 0, 100, 100], [0, 40, 100, 60]],
                }
            }
        return {
            task: {
                "labels": ["gold statue", "awards"],
                "bboxes": [[40, 10, 75, 38], [12, 55, 35, 82]],
            }
        }

    monkeypatch.setattr(parts, "_run_task", fake_run)
    monkeypatch.setattr(
        scenario,
        "extract_parts",
        lambda *_args: ["shelf", "gold statue"],
    )
    monkeypatch.setattr(
        scenario,
        "extract_contents",
        lambda *_args: [
            "gold statues",
            "awards",
            "shelf",
            "person",
            "unlisted artifact",
        ],
    )
    monkeypatch.setattr(
        scenario,
        "translate_terms",
        lambda terms: {
            term: {
                "gold statue": "金色雕像",
                "award": "奖项",
            }[term]
            for term in terms
        },
    )

    result = parts.analyze_parts(
        Image.new("RGB", (100, 100)),
        "cabinet",
        "柜子",
        object_box=[5, 5, 95, 95],
    )
    assert result["is_container"] is True
    assert result["parts"] == [
        {
            "label_en": "shelf",
            "label_zh": "架子",
            "box": [0.0, 40.0, 100.0, 60.0],
        }
    ]
    assert result["contents"] == [
        {
            "label_en": "gold statue",
            "canonical_label": "statue",
            "box": [40.0, 10.0, 75.0, 38.0],
            "label_zh": "金色雕像",
        },
        {
            "label_en": "award",
            "canonical_label": "award",
            "box": [12.0, 55.0, 35.0, 82.0],
            "label_zh": "奖项",
        },
    ]
    assert prompts[-1] == (
        "<CAPTION_TO_PHRASE_GROUNDING>",
        "gold statues and awards",
    )


def test_content_geometry_and_overlap_gates_are_precision_first(monkeypatch):
    monkeypatch.setattr(scenario, "translate_terms", lambda terms: {})
    grounded = {
        "<CAPTION_TO_PHRASE_GROUNDING>": {
            "labels": ["book", "vase", "statue", "award"],
            "bboxes": [
                [10, 10, 40, 40],
                [12, 12, 39, 39],
                [90, 90, 99, 99],
                [0, 0, 100, 100],
            ],
        }
    }
    assert parts._content_items(
        ["book", "vase", "statue", "award"],
        grounded,
        crop_size=(100, 100),
        container_box=[5, 5, 80, 80],
    ) == [
        {
            "label_en": "book",
            "canonical_label": "book",
            "box": [10.0, 10.0, 40.0, 40.0],
            "label_zh": "",
        }
    ]


def test_only_explicit_container_labels_enable_content_analysis():
    assert parts.is_container("cabinet")
    assert parts.container_relation("bookshelf") == "on"
    assert not parts.is_container("table")


def test_caption_fallback_keeps_visible_plural_but_excludes_structure():
    assert parts._caption_content_terms(
        "A wooden shelf has a gold Buddha statue and several awards."
    ) == ["statue", "awards"]
