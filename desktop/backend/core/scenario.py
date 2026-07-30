"""Personalized example sentences for Memorizing (FR-15).

The product deliberately fixes one compact model:
Qwen2.5-0.5B-Instruct GGUF Q4_K_M, run locally through llama.cpp.  It receives
only compact, server-owned facts derived from the current photo and generates
fresh bilingual examples on every selection; there is no canned-sentence path.
"""
from __future__ import annotations

import functools
import json
import os
import re
import threading

from backend.core import model_assets

MODEL = model_assets.QWEN_REPO
MODEL_FILE = model_assets.QWEN_FILENAME
MODEL_REVISION = model_assets.QWEN_REVISION

_INFER_LOCK = threading.RLock()

_SYSTEM = (
    "You are a careful bilingual English teacher. Return exactly one short, "
    "natural English memory-scene sentence and its exact Simplified Chinese "
    "translation. The English sentence MUST contain the exact Target word. The "
    "scene is inspired by the supplied photo facts, but is not a literal photo "
    "caption. Mention only named objects or visible parts. You may add a simple "
    "learner action involving the Target, but do not invent other people, colors, "
    "brands, weather, locations, object condition, or unseen parts. Return only "
    "JSON matching the requested schema. Start the English sentence with I. Use "
    "the Target as the selected object or part itself; do not turn it into a new "
    "compound noun."
)

_SENTENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "en": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["en", "zh"],
            },
        }
    },
    "required": ["sentences"],
}


@functools.lru_cache(maxsize=1)
def _load():
    from llama_cpp import Llama

    model_path = model_assets.download_verified(
        model_assets.QWEN_REPO,
        model_assets.QWEN_FILENAME,
        model_assets.QWEN_REVISION,
        model_assets.QWEN_SIZE,
        model_assets.QWEN_SHA256,
    )
    return Llama(
        model_path=model_path,
        n_ctx=2048,
        n_batch=256,
        n_gpu_layers=-1,
        n_threads=max(1, (os.cpu_count() or 4) - 2),
        use_mmap=True,
        verbose=False,
    )


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    """Release the llama.cpp model and its Metal/CPU buffers."""
    _load.cache_clear()
    import gc

    gc.collect()


def _parse_object(resp: str) -> dict:
    """Extract one JSON object even if a backend adds a Markdown fence."""
    match = re.search(r"\{.*\}", (resp or "").strip(), re.DOTALL)
    if not match:
        raise ValueError("model returned no JSON object")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model JSON is not an object")
    return data


def _parse(resp: str) -> list[dict[str, str]]:
    """Validate the bilingual sentence contract; never invent a canned result."""
    data = _parse_object(resp)
    out: list[dict[str, str]] = []
    for item in data.get("sentences", []):
        if not isinstance(item, dict):
            continue
        en = str(item.get("en") or "").strip()
        zh = str(item.get("zh") or "").strip()
        if en and zh and len(en) <= 300 and len(zh) <= 300:
            out.append({"en": en, "zh": zh})
    if not out:
        raise ValueError("model returned no valid bilingual sentences")
    return out[:3]


def _first_sentence(text: str, endings: str) -> str:
    """Trim a small-model run-on without replacing any model-written text."""
    match = re.search(f"[{re.escape(endings)}]", text)
    if match is None:
        return text.strip()
    return text[: match.end()].strip()


def _normalize_memory_sentence(sentence: dict[str, str]) -> dict[str, str]:
    """Keep the first bilingual sentence when the 0.5B model over-generates."""
    return {
        "en": _first_sentence(sentence["en"], ".!?"),
        "zh": _first_sentence(sentence["zh"], "。！？"),
    }


def _content(response: dict) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("llama.cpp returned an unexpected response") from exc
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _chat_json(messages: list[dict], schema: dict, max_tokens: int = 384) -> dict:
    model = _load()
    with _INFER_LOCK:
        response = model.create_chat_completion(
            messages=messages,
            temperature=0.1,
            top_p=0.8,
            repeat_penalty=1.1,
            max_tokens=max_tokens,
            response_format={"type": "json_object", "schema": schema},
        )
    return _parse_object(_content(response))


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _relevant_context(context: str, object_en: str, selected_en: str) -> str:
    """Keep the visual sentence most relevant to the requested vocabulary."""
    cleaned = _clean(context, 1200)
    if not cleaned:
        return object_en
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", cleaned)
        if item.strip()
    ]
    needles = [item.casefold() for item in (selected_en, object_en) if item]
    relevant = [
        item
        for item in sentences
        if any(
            re.search(rf"(?<![A-Za-z]){re.escape(needle)}(?![A-Za-z])", item, re.I)
            for needle in needles
        )
    ]
    return _clean(" ".join((relevant or sentences)[:2]), 360)


def _valid_memory_sentence(sentence: dict[str, str], selected_en: str) -> bool:
    english = sentence["en"].strip()
    target = re.compile(
        rf"(?<![A-Za-z]){re.escape(selected_en)}(?![A-Za-z])",
        re.IGNORECASE,
    )
    return (
        bool(re.match(r"^I(?:\s|['’])", english))
        and bool(target.search(english))
        and len(re.findall(r"[.!?]", english)) <= 1
    )


def generate(
    label_en: str,
    label_zh: str = "",
    *,
    photo_context: str = "",
    scene_objects: list[str] | None = None,
    part_en: str = "",
    part_zh: str = "",
) -> list[dict[str, str]]:
    """Generate personalized bilingual examples from compact photo facts."""
    object_en = _clean(label_en, 80)
    object_zh = _clean(label_zh, 80)
    selected_en = _clean(part_en, 80) or object_en
    selected_zh = _clean(part_zh, 80) or object_zh
    if not selected_en:
        raise ValueError("an English object or part label is required")

    nearby: list[str] = []
    seen_nearby: set[str] = set()
    for item in scene_objects or []:
        cleaned = _clean(item, 60)
        folded = cleaned.casefold()
        if cleaned and folded not in seen_nearby:
            seen_nearby.add(folded)
            nearby.append(cleaned)
    relevant_context = _relevant_context(photo_context, object_en, selected_en)
    facts = {
        "whole_object": {"en": object_en, "zh": object_zh},
        "selected_word": {"en": selected_en, "zh": selected_zh},
        "visible_crop_description": relevant_context,
        "other_detected_objects": nearby[:8],
    }
    request = (
        f"Target: {selected_en}\n"
        f"Whole object: {object_en}\n"
        f"Visible facts: {facts['visible_crop_description'] or object_en}\n"
        f"Other detected objects: {', '.join(nearby[:8]) or 'none'}\n"
        f"Write one sentence that begins with I and contains the exact word {selected_en}."
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "Target: handle\nWhole object: mug\n"
                "Visible facts: a mug with a handle\nOther detected objects: book"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentences":[{"en":"I hold the mug by its handle beside the book.",'
                '"zh":"我在书旁握住杯子的把手。"}]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Target: bicycle\nWhole object: bicycle\n"
                "Visible facts: a bicycle beside a car\nOther detected objects: car"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"sentences":[{"en":"I walk toward the bicycle beside the car.",'
                '"zh":"我走向汽车旁的自行车。"}]}'
            ),
        },
        {"role": "user", "content": request},
    ]

    for attempt in range(2):
        try:
            data = _chat_json(messages, _SENTENCE_SCHEMA)
            sentences = [
                _normalize_memory_sentence(item)
                for item in _parse(json.dumps(data, ensure_ascii=False))
            ]
            if not all(_valid_memory_sentence(item, selected_en) for item in sentences):
                raise ValueError("model output is not a one-sentence first-person memory scene")
            return sentences
        except (ValueError, json.JSONDecodeError):
            if attempt:
                raise
            messages[-1] = {
                "role": "user",
                "content": (
                    f"Target: {selected_en}\nWhole object: {object_en}\n"
                    f"Visible facts: {relevant_context or object_en}\n"
                    "Other detected objects: none\n"
                    f"Write one sentence beginning with I and containing the exact word "
                    f"{selected_en}, then give one faithful Chinese translation."
                ),
            }
    raise ValueError("scenario generation failed")


def extract_parts(
    object_label: str,
    caption: str,
    dense_labels: list[str],
) -> list[str]:
    """Use the already-loaded small LLM to filter Florence output into parts."""
    schema = {
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string"},
            }
        },
        "required": ["parts"],
    }
    facts = {
        "whole_object": _clean(object_label, 80),
        "crop_caption": _clean(caption, 700),
        "region_labels": [_clean(item, 80) for item in dense_labels[:20]],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only concrete, visible physical component names from image "
                "descriptions. Exclude the whole object, people, background, colors, "
                "materials, actions, and uncertain or invisible parts. Return short "
                "singular English noun phrases as JSON."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "whole_object": "bus",
                    "crop_caption": "Three men stand in front of a bus and one holds a book.",
                    "region_labels": ["bus", "human face", "book"],
                }
            ),
        },
        {"role": "assistant", "content": '{"parts":[]}'},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "whole_object": "bicycle",
                    "crop_caption": "A bicycle with a visible wheel and handlebar.",
                    "region_labels": ["bicycle", "wheel", "handlebar"],
                }
            ),
        },
        {"role": "assistant", "content": '{"parts":["wheel","handlebar"]}'},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]
    data = _chat_json(messages, schema, max_tokens=192)
    result: list[str] = []
    seen: set[str] = set()
    for value in data.get("parts", []):
        term = _clean(value, 60).lower().strip(" .,:;")
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result[:12]


def translate_terms(terms: list[str]) -> dict[str, str]:
    """Translate uncommon English part labels in one compact LLM call."""
    cleaned = [_clean(term, 60).lower() for term in terms if _clean(term, 60)]
    if not cleaned:
        return {}
    schema = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "en": {"type": "string"},
                        "zh": {"type": "string"},
                    },
                    "required": ["en", "zh"],
                },
            }
        },
        "required": ["translations"],
    }
    messages = [
        {
            "role": "system",
            "content": "Translate English physical component names into concise Simplified Chinese. Return JSON only.",
        },
        {"role": "user", "content": json.dumps({"terms": cleaned[:20]}, ensure_ascii=False)},
    ]
    data = _chat_json(messages, schema, max_tokens=256)
    out: dict[str, str] = {}
    for item in data.get("translations", []):
        if not isinstance(item, dict):
            continue
        en = _clean(item.get("en"), 60).lower()
        zh = _clean(item.get("zh"), 60)
        if en in cleaned and zh:
            out[en] = zh
    return out
