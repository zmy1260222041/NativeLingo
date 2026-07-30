"""Florence-2 visual enhancement for component naming (FR-14).

The default enhancement pack is Microsoft's Florence-2-base-ft weights through
the pinned ``florence-community/Florence-2-base-ft`` native Transformers
conversion. It describes only the selected server-side crop. Florence's
detailed caption and dense region labels are then conservatively filtered into
visible physical parts by the already-loaded 0.5B text model.
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


def _run_task(pil_crop, task: str):
    """Run one official Florence task and return post-processed output."""
    import torch

    processor, model, device, dtype = _load()
    inputs = processor(text=task, images=pil_crop, return_tensors="pt")
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
    return translated


def analyze_parts(pil_crop, label_en: str, label_zh: str = "") -> dict:
    """Return ``{crop_context, parts}`` for one selected object crop."""
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
    return {"crop_context": context, "parts": parts}


def name_parts(pil_crop, label_en: str, label_zh: str = "") -> list[dict]:
    """Backward-compatible wrapper used by older callers/tests."""
    return analyze_parts(pil_crop, label_en, label_zh)["parts"]
