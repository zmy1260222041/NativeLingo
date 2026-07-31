"""Florence-2 visual enhancement for component and container-content naming.

The default enhancement pack is Microsoft's Florence-2-base-ft weights through
the pinned ``florence-community/Florence-2-base-ft`` native Transformers
conversion. It describes only the selected server-side crop. Florence's
detailed caption and dense region labels are then conservatively filtered into
visible physical parts by the already-loaded 0.5B text model. For an explicit
container label, independently named contents must also be mentioned by the
detailed caption and localized by one joint phrase-grounding pass. Contents are
returned as leaves; the API never promotes them to recursively analyzable
whole-object detections.
"""
from __future__ import annotations

import functools
import json
import os
import re

from backend.core import model_assets

MODEL = model_assets.FLORENCE_REPO
MODEL_REVISION = model_assets.FLORENCE_REVISION

_HERE = os.path.dirname(os.path.abspath(__file__))
_DETAIL_TASK = "<MORE_DETAILED_CAPTION>"
_DENSE_TASK = "<DENSE_REGION_CAPTION>"
_GROUND_TASK = "<CAPTION_TO_PHRASE_GROUNDING>"
_CONTAINER_RELATIONS = {
    "bookcase": "inside",
    "bookshelf": "on",
    "cabinet": "inside",
    "closet": "inside",
    "cupboard": "inside",
    "filing cabinet": "inside",
    "shelf": "on",
    "showcase": "inside",
    "supermarket shelf": "on",
    "wardrobe": "inside",
}
_CONTENT_STRUCTURE_LABELS = set(_CONTAINER_RELATIONS) | {
    "background",
    "cabinet",
    "ceiling",
    "closet",
    "cupboard",
    "door",
    "drawer",
    "floor",
    "foreground",
    "handle",
    "hinge",
    "panel",
    "shelf",
    "showcase",
    "wall",
    "wardrobe",
}
# Florence can name these useful display objects even when prompt-free YOLOE's
# vocabulary does not contain the same head noun.
_CONTENT_EXTRA_HEADS = {
    "award",
    "certificate",
    "figurine",
    "medal",
    "ornament",
}
_GENERIC_LABELS = {
    "background",
    "foreground",
    "image",
    "object",
    "photo",
    "picture",
    "person",
    "people",
    "scene",
    "thing",
}
_HUMAN_WORDS = {
    "boy",
    "child",
    "face",
    "girl",
    "hand",
    "human",
    "man",
    "men",
    "people",
    "person",
    "woman",
    "women",
}


@functools.lru_cache(maxsize=1)
def _translations() -> dict[str, str]:
    with open(os.path.join(_HERE, "parts_zh.json"), encoding="utf-8") as handle:
        return {str(k).lower(): str(v) for k, v in json.load(handle).items()}


@functools.lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoProcessor, Florence2ForConditionalGeneration

    # Resolve and verify the pinned weight before transformers loads the rest of
    # the fixed-revision snapshot (config, tokenizer and remote model code).
    model_assets.download_verified(
        model_assets.FLORENCE_REPO,
        model_assets.FLORENCE_FILENAME,
        model_assets.FLORENCE_REVISION,
        model_assets.FLORENCE_SIZE,
        model_assets.FLORENCE_SHA256,
    )
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device == "mps" else torch.float32
    processor = AutoProcessor.from_pretrained(
        MODEL,
        revision=MODEL_REVISION,
    )
    model = Florence2ForConditionalGeneration.from_pretrained(
        MODEL,
        revision=MODEL_REVISION,
        torch_dtype=dtype,
    )
    model.eval()
    model.to(device)
    return processor, model, device, dtype


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    """Release Florence weights and MPS buffers on tab exit."""
    had_model = _load.cache_info().currsize > 0
    _load.cache_clear()
    if not had_model:
        return
    import gc
    import torch

    gc.collect()
    if torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def _run_task(pil_crop, task: str, prompt: str = ""):
    """Run one official Florence task and return post-processed output."""
    import torch

    processor, model, device, dtype = _load()
    inputs = processor(text=f"{task}{prompt}", images=pil_crop, return_tensors="pt")
    inputs = inputs.to(device, dtype)
    with torch.inference_mode():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=256,
            num_beams=3,
            do_sample=False,
            early_stopping=True,
        )
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    return processor.post_process_generation(
        generated_text,
        task=task,
        image_size=pil_crop.size,
    )


def _task_value(result, task: str):
    if isinstance(result, dict):
        return result.get(task, result)
    return result


def _caption_text(result) -> str:
    value = _task_value(result, _DETAIL_TASK)
    if isinstance(value, str):
        return " ".join(value.split())[:1200]
    if isinstance(value, dict):
        for key in ("caption", "text", "labels"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return " ".join(candidate.split())[:1200]
    return ""


def _normalize_label(value: object) -> str:
    text = " ".join(str(value or "").strip().split()).lower()
    text = re.sub(r"^(?:a|an|the)\s+", "", text)
    return text.strip(" .,:;!?-")[:80]


def is_container(label: str) -> bool:
    """Return whether FR-14 should look for independent contained objects."""
    return _normalize_label(label) in _CONTAINER_RELATIONS


def container_relation(label: str) -> str:
    """Describe how content is spatially related to the selected container."""
    return _CONTAINER_RELATIONS.get(_normalize_label(label), "inside")


def _valid_box(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = [round(float(item), 1) for item in value]
    except (TypeError, ValueError):
        return None
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return None
    return box


def _dense_regions(
    result,
    object_label: str = "",
    *,
    keep_repeats: bool = False,
) -> list[dict]:
    """Normalize Florence dense-caption output defensively."""
    value = _task_value(result, _DENSE_TASK)
    if not isinstance(value, dict):
        return []
    labels = value.get("labels") or []
    boxes = value.get("bboxes") or value.get("boxes") or []
    object_name = _normalize_label(object_label)
    regions: list[dict] = []
    seen: set[str] = set()
    for index, raw_label in enumerate(labels):
        label = _normalize_label(raw_label)
        if (
            not label
            or (label in seen and not keep_repeats)
            or label in _GENERIC_LABELS
            or label == object_name
        ):
            continue
        seen.add(label)
        item = {"label": label}
        if index < len(boxes):
            box = _valid_box(boxes[index])
            if box is not None:
                item["box"] = box
        regions.append(item)
    return regions[:30]


@functools.lru_cache(maxsize=1)
def _content_heads() -> tuple[str, ...]:
    """Vocabulary gate for independent tangible objects in a container.

    Returned longest-phrase-first so a multi-word head (``glass bottle``) is
    matched before its shorter suffix (``bottle``).
    """
    with open(os.path.join(_HERE, "coco_names.txt"), encoding="utf-8") as handle:
        coco = {_normalize_label(line) for line in handle if line.strip()}
    with open(os.path.join(_HERE, "yoloe_labels.json"), encoding="utf-8") as handle:
        configured = {
            _normalize_label(label)
            for label in json.load(handle).get("labels", {})
        }
    heads = (coco | configured | _CONTENT_EXTRA_HEADS) - {"person"}
    return tuple(
        sorted(heads, key=lambda value: (len(value.split()), len(value)), reverse=True)
    )


def _match_content_head(term: str) -> str | None:
    for head in _content_heads():
        if term == head or term.endswith(f" {head}"):
            return head
    return None


def _normalize_content_term(value: object) -> tuple[str, str] | None:
    """Return a conservative ``(display phrase, tangible head)`` pair."""
    term = _normalize_label(value)
    if not term or " and " in term or set(term.split()) & _HUMAN_WORDS:
        return None
    if term in _CONTENT_STRUCTURE_LABELS or term in _GENERIC_LABELS:
        return None

    head = _match_content_head(term)
    if head is not None:
        return term, head

    # The extraction prompt asks for singular nouns, but normalize a small
    # model's common plural slips only when the resulting head is allowlisted.
    words = term.split()
    if not words:
        return None
    last = words[-1]
    variants = []
    if last.endswith("ies") and len(last) > 3:
        variants.append(f"{last[:-3]}y")
    if last.endswith("es") and len(last) > 2:
        variants.append(last[:-2])
    if last.endswith("s") and not last.endswith("ss") and len(last) > 1:
        variants.append(last[:-1])
    for singular in variants:
        normalized = " ".join([*words[:-1], singular])
        head = _match_content_head(normalized)
        if head is not None and normalized not in _CONTENT_STRUCTURE_LABELS:
            return normalized, head
    return None


def _plural_forms(head: str) -> list[str]:
    """Return the singular head plus one conservative regular plural."""
    words = head.split()
    if not words:
        return []
    last = words[-1]
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        plural = f"{last[:-1]}ies"
    elif last.endswith(("s", "x", "z", "ch", "sh")):
        plural = f"{last}es"
    else:
        plural = f"{last}s"
    return [head, " ".join([*words[:-1], plural])]


def _caption_content_terms(caption: str) -> list[str]:
    """Recover explicit tangible nouns when the 0.5B relation pass is silent.

    This fallback cannot introduce a noun absent from the Florence caption, and
    every returned surface phrase must still pass phrase grounding and geometry.
    Keeping a caption's plural (``awards``) improves joint grounding while the
    final UI label is normalized back to singular.
    """
    text = " ".join(str(caption or "").casefold().split())
    if not text:
        return []
    matches: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []
    for head in _content_heads():
        if (
            head in _CONTENT_STRUCTURE_LABELS
            or head in _GENERIC_LABELS
            or set(head.split()) & _HUMAN_WORDS
        ):
            continue
        forms = sorted(_plural_forms(head), key=len, reverse=True)
        pattern = re.compile(
            rf"(?<![a-z])(?:{'|'.join(re.escape(form) for form in forms)})(?![a-z])"
        )
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            matches.append((span[0], span[1], match.group(0)))
            break
    matches.sort(key=lambda item: item[0])
    return [surface for _, _, surface in matches[:8]]


def _grounded_regions(result) -> list[dict]:
    """Normalize Florence phrase-grounding boxes without inventing confidence."""
    value = _task_value(result, _GROUND_TASK)
    if not isinstance(value, dict):
        return []
    labels = value.get("labels") or []
    boxes = value.get("bboxes") or value.get("boxes") or []
    regions = []
    for index, raw_label in enumerate(labels):
        normalized = _normalize_content_term(raw_label)
        if normalized is None or index >= len(boxes):
            continue
        box = _valid_box(boxes[index])
        if box is not None:
            regions.append(
                {
                    "label": normalized[0],
                    "canonical_label": normalized[1],
                    "box": box,
                }
            )
    return regions


def _box_iou_xyxy(first: list[float], second: list[float]) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    first_area = (ax2 - ax1) * (ay2 - ay1)
    second_area = (bx2 - bx1) * (by2 - by1)
    return intersection / (first_area + second_area - intersection + 1e-9)


def _box_containment_xyxy(first: list[float], second: list[float]) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    first_area = (ax2 - ax1) * (ay2 - ay1)
    second_area = (bx2 - bx1) * (by2 - by1)
    return intersection / (min(first_area, second_area) + 1e-9)


def _usable_content_box(
    value: object,
    crop_size,
    container_box: list[float] | None,
) -> list[float] | None:
    box = _valid_box(value)
    if box is None:
        return None
    crop_width, crop_height = (float(item) for item in crop_size)
    x1, y1, x2, y2 = box
    clipped = [
        max(0.0, min(crop_width, x1)),
        max(0.0, min(crop_height, y1)),
        max(0.0, min(crop_width, x2)),
        max(0.0, min(crop_height, y2)),
    ]
    x1, y1, x2, y2 = clipped
    width, height = x2 - x1, y2 - y1
    if width < 4.0 or height < 4.0:
        return None
    area_ratio = width * height / max(1.0, crop_width * crop_height)
    if not 0.001 <= area_ratio <= 0.45:
        return None
    if container_box is not None:
        px1, py1, px2, py2 = container_box
        center_x, center_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        if not (px1 <= center_x <= px2 and py1 <= center_y <= py2):
            return None
    return [round(item, 1) for item in clipped]


def _content_items(
    candidates: list[str],
    grounded,
    *,
    crop_size,
    container_box: list[float] | None = None,
) -> list[dict]:
    """Join caption-derived candidates to grounded boxes and apply hard gates."""
    normalized_candidates: list[tuple[str, str]] = []
    seen_candidates: set[str] = set()
    for raw in candidates:
        normalized = _normalize_content_term(raw)
        if normalized is None or normalized[0] in seen_candidates:
            continue
        seen_candidates.add(normalized[0])
        normalized_candidates.append(normalized)

    grounded_regions = _grounded_regions(grounded)
    kept: list[dict] = []
    for term, head in normalized_candidates:
        match = next(
            (
                region
                for region in grounded_regions
                if region["label"] == term
                or region["canonical_label"] == head
                or term in region["label"]
                or region["label"] in term
            ),
            None,
        )
        if match is None:
            continue
        box = _usable_content_box(match["box"], crop_size, container_box)
        if box is None:
            continue
        if any(
            _box_iou_xyxy(box, prior["box"]) >= 0.55
            or _box_containment_xyxy(box, prior["box"]) >= 0.90
            for prior in kept
        ):
            continue
        kept.append(
            {
                "label_en": term,
                "canonical_label": head,
                "box": box,
            }
        )
        if len(kept) >= 8:
            break

    translations = _translate([item["label_en"] for item in kept])
    for item in kept:
        item["label_zh"] = translations.get(item["label_en"], "")
    return kept


def _match_region(term: str, regions: list[dict]) -> list[float] | None:
    normalized = _normalize_label(term)
    for region in regions:
        label = region["label"]
        if normalized == label or normalized in label or label in normalized:
            return region.get("box")
    return None


def _fallback_terms(regions: list[dict], object_label: str) -> list[str]:
    """A conservative fallback when structured LLM extraction fails."""
    object_name = _normalize_label(object_label)
    return [
        item["label"]
        for item in regions
        if item["label"] != object_name and len(item["label"].split()) <= 4
    ][:8]


def _looks_like_component(term: str) -> bool:
    """Precision-first terminology gate after the 0.5B semantic filter."""
    words = set(term.split())
    if words & _HUMAN_WORDS:
        return False
    glossary = _translations()
    # Dense captions frequently return nested scene objects (book, trousers,
    # another person) rather than components of the selected whole. The small
    # LLM alone is not a reliable relationship classifier, so unknown terms are
    # held back until R-13 expands this tiny physical-component glossary.
    return term in glossary or (term.split() and term.split()[-1] in glossary)


def _translate(terms: list[str]) -> dict[str, str]:
    glossary = _translations()
    translated = {term: glossary[term] for term in terms if term in glossary}
    missing = [term for term in terms if term not in translated]
    if missing:
        try:
            from backend.core import scenario

            translated.update(scenario.translate_terms(missing))
        except Exception:  # noqa: BLE001 -- English labels remain useful
            pass
    # Florence often adds the whole object as a modifier ("bicycle wheel",
    # "cabinet door"). If the LLM omitted such a phrase, inherit the longest
    # known physical-part suffix so the overlay still has a Chinese name.
    glossary_suffixes = sorted(
        glossary,
        key=lambda value: (len(value.split()), len(value)),
        reverse=True,
    )
    for term in terms:
        if term in translated:
            continue
        suffix = next(
            (
                candidate
                for candidate in glossary_suffixes
                if term.endswith(f" {candidate}")
            ),
            None,
        )
        if suffix is not None:
            translated[term] = glossary[suffix]
    return translated


def _dedup_content_terms(terms: list[str]) -> tuple[list[str], set[str]]:
    """Normalize extracted terms and head-dedup them into a grounding prompt."""
    grounding_terms: list[str] = []
    seen_heads: set[str] = set()
    for term in terms:
        normalized = _normalize_content_term(term)
        if normalized is None or normalized[1] in seen_heads:
            continue
        seen_heads.add(normalized[1])
        grounding_terms.append(_normalize_label(term))
    return grounding_terms, seen_heads


def _container_contents(
    pil_crop,
    label_en: str,
    context: str,
    object_box: list[float] | None,
) -> list[dict]:
    """One-level contents for an explicit container label.

    Candidates come from the 0.5B relation pass; when that yields no usable
    terms, the same Florence caption is scanned for allowlisted nouns (PRD:
    the deterministic fallback never overrides an explicit extraction). Every
    candidate must then get a Florence phrase-grounding box and pass the hard
    geometry/overlap gates in ``_content_items``.
    """
    from backend.core import scenario

    grounding_terms, _ = _dedup_content_terms(
        scenario.extract_contents(label_en, context)
    )
    if not grounding_terms:
        grounding_terms, _ = _dedup_content_terms(_caption_content_terms(context))
    if not grounding_terms:
        return []
    grounded = _run_task(
        pil_crop,
        _GROUND_TASK,
        " and ".join(grounding_terms[:8]),
    )
    return _content_items(
        grounding_terms,
        grounded,
        crop_size=pil_crop.size,
        container_box=object_box,
    )


def analyze_parts(
    pil_crop,
    label_en: str,
    label_zh: str = "",
    *,
    object_box: list[float] | None = None,
) -> dict:
    """Return visible parts and one-level contents for a selected object crop."""
    detailed = _run_task(pil_crop, _DETAIL_TASK)
    dense = _run_task(pil_crop, _DENSE_TASK)
    context = _caption_text(detailed)
    regions = _dense_regions(dense, label_en)
    dense_labels = [item["label"] for item in regions]

    try:
        from backend.core import scenario

        terms = scenario.extract_parts(label_en, context, dense_labels)
    except Exception:  # noqa: BLE001 -- preserve a visible-only Florence fallback
        terms = _fallback_terms(regions, label_en)

    object_name = _normalize_label(label_en)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = _normalize_label(term)
        if (
            normalized
            and normalized not in seen
            and normalized != object_name
            and normalized not in _GENERIC_LABELS
            and _looks_like_component(normalized)
        ):
            seen.add(normalized)
            deduped.append(normalized)
    translations = _translate(deduped)

    parts: list[dict] = []
    for term in deduped[:12]:
        item = {"label_en": term, "label_zh": translations.get(term, "")}
        box = _match_region(term, regions)
        if box is not None:
            item["box"] = box
        parts.append(item)

    contents: list[dict] = []
    container = is_container(label_en)
    if container and context:
        try:
            contents = _container_contents(pil_crop, label_en, context, object_box)
        except Exception:  # noqa: BLE001 -- empty is the precision-first fallback
            contents = []

    return {
        "crop_context": context,
        "parts": parts,
        "contents": contents,
        "is_container": container,
    }


def name_parts(pil_crop, label_en: str, label_zh: str = "") -> list[dict]:
    """Backward-compatible wrapper used by older callers/tests."""
    return analyze_parts(pil_crop, label_en, label_zh)["parts"]
