"""Pure preprocessing/filter tests for the YOLOE-26S-PF FR-13 path."""
from __future__ import annotations

import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from backend.core import vision
from backend.main import app

client = TestClient(app)


def test_expanded_everyday_vocabulary_is_runtime_visible():
    new_labels = {
        "bus stop",
        "coffee machine",
        "faucet",
        "grass",
        "path",
        "road",
        "tree",
    }
    names = {index: label for index, label in enumerate(sorted(new_labels))}
    specs = vision._load_label_specs(names)

    assert set(specs) == new_labels
    assert specs["coffee machine"] == {"zh": "咖啡机", "min_score": 0.17}
    assert specs["tree"] == {"zh": "树", "min_score": 0.11}


def test_teapot_vocabulary_is_runtime_visible():
    specs = vision._load_label_specs({0: "tea pot"})

    assert specs == {"tea pot": {"zh": "茶壶", "min_score": 0.35}}


def test_squid_threshold_remains_unchanged():
    specs = vision._load_label_specs({0: "squid"})

    assert specs == {"squid": {"zh": "鱿鱼", "min_score": 0.40}}


def test_plant_vocabulary_is_runtime_visible():
    labels = {"bamboo", "cactus", "fern", "herb", "houseplant", "leaf", "vine"}
    names = {index: label for index, label in enumerate(sorted(labels))}

    specs = vision._load_label_specs(names)

    assert specs["herb"] == {"zh": "香草", "min_score": 0.10}
    assert specs["houseplant"] == {"zh": "盆栽植物", "min_score": 0.40}
    assert set(specs) == labels


def test_everyday_vocabulary_is_runtime_visible():
    labels = {
        "chopstick",
        "hanger",
        "key",
        "liner",
        "napkin",
        "paper",
        "paper towel",
        "parchment",
        "rice cooker",
        "toothpaste",
    }
    names = {index: label for index, label in enumerate(sorted(labels))}

    specs = vision._load_label_specs(names)

    assert set(specs) == labels
    assert specs["parchment"] == {"zh": "烘焙纸", "min_score": 0.40}
    assert specs["chopstick"] == {"zh": "筷子", "min_score": 0.60}
    assert specs["key"] == {"zh": "钥匙", "min_score": 0.60}


def test_gallery_driven_vocabulary_is_runtime_visible():
    gallery_labels = {
        "bedside lamp",
        "chisel",
        "computer screen",
        "crosswalk",
        "dish washer",
        "drill",
        "fence",
        "hydrant",
        "kitchen counter",
        "lamp shade",
        "mailbox",
        "nightstand",
        "pen",
        "pencil",
        "saw",
        "seesaw",
        "shower curtain",
        "slide",
        "tissue",
        "toilet bowl",
        "towel",
        "workbench",
    }
    names = {index: label for index, label in enumerate(sorted(gallery_labels))}
    specs = vision._load_label_specs(names)

    assert set(specs) == gallery_labels
    assert specs["hydrant"] == {"zh": "消防栓", "min_score": 0.50}
    assert specs["crosswalk"] == {"zh": "人行横道", "min_score": 0.24}
    assert specs["workbench"] == {"zh": "工作台", "min_score": 0.60}


def test_dynamic_letterbox_roundtrip_and_stride_shape():
    for width, height in [(320, 240), (640, 640), (480, 720), (1280, 720)]:
        ratio, pad_x, pad_y, input_width, input_height = vision.letterbox(
            (width, height)
        )
        assert input_width <= 640 and input_height <= 640
        assert input_width % 32 == 0 and input_height % 32 == 0
        assert max(input_width, input_height) == 640

        original_x, original_y = width / 2.0, height / 2.0
        model_x = original_x * ratio + pad_x
        model_y = original_y * ratio + pad_y
        assert abs((model_x - pad_x) / ratio - original_x) < 1e-6
        assert abs((model_y - pad_y) / ratio - original_y) < 1e-6


def test_parse_output_filters_unknown_and_per_label_threshold():
    raw = np.array(
        [[
            [20, 30, 120, 130, 0.81, 0],  # allowed clock
            [160, 30, 260, 130, 0.59, 1],  # clock below 0.60
            [300, 30, 400, 130, 0.99, 2],  # unknown action/scene label
        ]],
        dtype=np.float32,
    )
    detections = vision._parse_output(
        raw,
        ratio=1.0,
        pad_x=0,
        pad_y=0,
        orig_wh=(640, 480),
        names={0: "clock", 1: "clock", 2: "courtyard"},
        label_specs={"clock": {"zh": "时钟", "min_score": 0.60}},
    )
    assert detections == [
        {
            "id": 0,
            "label_en": "clock",
            "label_zh": "时钟",
            "score": 0.81,
            "box": [20.0, 30.0, 100.0, 100.0],
        }
    ]


def test_parse_output_rescales_and_deduplicates_synonyms():
    ratio, pad_x, pad_y, _, _ = vision.letterbox((320, 240))
    # Original box [110, 80, 100, 80], expressed as end-to-end xyxy in
    # letterboxed model coordinates twice with different vocabulary aliases.
    x1, y1 = 110 * ratio + pad_x, 80 * ratio + pad_y
    x2, y2 = 210 * ratio + pad_x, 160 * ratio + pad_y
    raw = np.array(
        [[[x1, y1, x2, y2, 0.90, 0], [x1 + 1, y1, x2 + 1, y2, 0.82, 1]]],
        dtype=np.float32,
    )
    detections = vision._parse_output(
        raw,
        ratio=ratio,
        pad_x=pad_x,
        pad_y=pad_y,
        orig_wh=(320, 240),
        names={0: "mug", 1: "cup"},
        label_specs={
            "mug": {"zh": "马克杯", "min_score": 0.45},
            "cup": {"zh": "杯子", "min_score": 0.45},
        },
    )
    assert len(detections) == 1
    assert detections[0]["label_en"] == "mug"
    assert detections[0]["box"] == [110.0, 80.0, 100.0, 80.0]


def test_parse_output_deduplicates_nested_alias_box():
    raw = np.array(
        [[
            [10, 10, 110, 210, 0.80, 0],
            [30, 30, 90, 180, 0.70, 1],
        ]],
        dtype=np.float32,
    )
    detections = vision._parse_output(
        raw,
        ratio=1.0,
        pad_x=0,
        pad_y=0,
        orig_wh=(640, 480),
        names={0: "fan", 1: "floor fan"},
        label_specs={
            "fan": {"zh": "风扇", "min_score": 0.55},
            "floor fan": {"zh": "落地扇", "min_score": 0.48},
        },
    )
    assert [item["label_en"] for item in detections] == ["fan"]


def test_multiscale_plaque_geometry_keeps_nameplate_and_rejects_noise():
    base = {
        "label_en": "plaque",
        "label_zh": "牌匾",
        "score": 0.4,
    }
    assert vision._multiscale_detection_is_usable(
        {**base, "box": [10.0, 10.0, 80.0, 42.0]}
    )
    assert not vision._multiscale_detection_is_usable(
        {**base, "box": [10.0, 10.0, 70.0, 47.0]}
    )
    assert not vision._multiscale_detection_is_usable(
        {**base, "box": [10.0, 10.0, 185.0, 69.0]}
    )


def test_multiscale_tiles_cover_image_with_800px_overlapping_crops():
    tiles = vision._multiscale_tiles((1440, 1920))

    assert len(tiles) == 12
    assert set(tiles) == {
        (0, 0, 800, 800),
        (0, 400, 800, 1200),
        (0, 800, 800, 1600),
        (0, 1120, 800, 1920),
        (400, 0, 1200, 800),
        (400, 400, 1200, 1200),
        (400, 800, 1200, 1600),
        (400, 1120, 1200, 1920),
        (640, 0, 1440, 800),
        (640, 400, 1440, 1200),
        (640, 800, 1440, 1600),
        (640, 1120, 1440, 1920),
    }
    for point in [(0, 0), (719, 719), (720, 720), (1439, 1919)]:
        x, y = point
        covering_tiles = [
            crop
            for crop in tiles
            if crop[0] <= x < crop[2] and crop[1] <= y < crop[3]
        ]
        assert covering_tiles


def test_complete_detection_from_any_overlap_is_offset_to_the_full_image():
    detection = {
        "id": 0,
        "label_en": "squid",
        "label_zh": "鱿鱼",
        "score": 0.54,
        "box": [282.0, 108.0, 275.0, 112.0],
    }

    mapped = vision._offset_complete_detection(
        detection,
        crop_box=(0, 800, 800, 1600),
        image_size=(1440, 1920),
    )
    assert mapped["box"] == [282.0, 908.0, 275.0, 112.0]


def test_internal_edge_clips_are_rejected_but_source_edges_are_allowed():
    detection = {
        "id": 0,
        "label_en": "squid",
        "label_zh": "鱿鱼",
        "score": 0.54,
        "box": [0.0, 0.0, 275.0, 112.0],
    }

    rejected = vision._offset_complete_detection(
        detection,
        crop_box=(400, 800, 1200, 1600),
        image_size=(1440, 1920),
    )
    source_edge = vision._offset_complete_detection(
        detection,
        crop_box=(0, 0, 800, 800),
        image_size=(1440, 1920),
    )

    assert rejected is None
    assert source_edge["box"] == [0.0, 0.0, 275.0, 112.0]


def test_overlapping_complete_views_keep_the_highest_score():
    weak = vision._offset_complete_detection(
        {
            "label_en": "squid",
            "label_zh": "鱿鱼",
            "score": 0.41,
            "box": [280.0, 509.0, 273.0, 111.0],
        },
        crop_box=(0, 400, 800, 1200),
        image_size=(1440, 1920),
    )
    strong = vision._offset_complete_detection(
        {
            "label_en": "squid",
            "label_zh": "鱿鱼",
            "score": 0.54,
            "box": [282.0, 108.0, 275.0, 112.0],
        },
        crop_box=(0, 800, 800, 1600),
        image_size=(1440, 1920),
    )

    assert vision._deduplicate_detections([weak, strong]) == [
        {**strong, "id": 0}
    ]


def test_jittered_same_label_tile_boxes_keep_the_highest_score():
    strong = {
        "label_en": "microwave",
        "label_zh": "微波炉",
        "score": 0.612,
        "box": [765.8, 296.2, 280.9, 289.4],
    }
    weak = {
        "label_en": "microwave",
        "label_zh": "微波炉",
        "score": 0.591,
        "box": [723.7, 322.0, 305.3, 294.1],
    }

    assert vision._box_iou(strong["box"], weak["box"]) < 0.72
    assert vision._deduplicate_detections([weak, strong]) == [
        {**strong, "id": 0}
    ]


def test_cross_scale_deduplication_keeps_stronger_box():
    weak = {
        "id": 0,
        "label_en": "herb",
        "label_zh": "香草",
        "score": 0.177,
        "box": [279.0, 829.0, 265.0, 184.0],
    }
    strong = {
        "id": 0,
        "label_en": "herb",
        "label_zh": "香草",
        "score": 0.769,
        "box": [307.0, 819.0, 219.0, 116.0],
    }

    detections = vision._deduplicate_detections([weak, strong])

    assert detections == [{**strong, "id": 0}]


def test_detect_runs_whole_image_plus_every_global_tile(monkeypatch):
    run_calls = []

    monkeypatch.setattr(vision, "_load", lambda: (object(), {}, {}))

    def fake_run(_session, image, *, new_size=vision._IN_SIZE):
        run_calls.append((image.size, new_size))
        return np.empty((1, 0, 6), dtype=np.float32), 1.0, 0, 0

    monkeypatch.setattr(vision, "_run", fake_run)

    detections = vision.detect(Image.new("RGB", (1440, 1920)))

    assert detections == []
    assert run_calls[0] == ((1440, 1920), 640)
    assert run_calls[1:] == [((800, 800), 1280)] * 12


def test_memorize_analyze_rejects_non_image():
    response = client.post(
        "/memorize/analyze",
        files={"photo": ("not.jpg", b"definitely not an image", "image/jpeg")},
    )
    assert response.status_code == 400


def test_memorize_status_endpoint():
    response = client.get("/memorize/status")
    assert response.status_code == 200
    assert "stage" in response.json()


def test_memorize_analyze_degrades_without_model(monkeypatch):
    monkeypatch.setattr(
        vision,
        "detect",
        lambda _image: (_ for _ in ()).throw(FileNotFoundError("not staged")),
    )
    output = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 40)).save(output, format="PNG")
    response = client.post(
        "/memorize/analyze",
        files={"photo": ("x.png", output.getvalue(), "image/png")},
    )
    assert response.status_code == 503
    assert "object detection unavailable" in response.json()["detail"]
