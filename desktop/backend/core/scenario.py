"""Personalized everyday dialogues for Memorizing (FR-15).

The product deliberately fixes one compact model:
Qwen2.5-0.5B-Instruct GGUF Q4_K_M, run locally through llama.cpp.  It receives
only compact, server-owned facts derived from the current photo and generates a
fresh two-speaker bilingual dialogue on every selection; there is no canned
dialogue path.
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
    "You are a careful bilingual English teacher. Write ONE short, natural, "
    "everyday spoken dialogue set in the scene described by the photo facts. "
    "Use exactly TWO speakers, labelled A and B, with 2 or 3 turns total. Each "
    "turn is ONE short spoken line — a question, a request, an offer, or a "
    "reply — the way people really talk in daily life, NOT a formal declarative "
    "sentence. CRITICAL RULES: (1) Speaker A's first English line MUST contain "
    "the exact Target phrase. (2) In each turn, put only the spoken line as the "
    "English text and only the label (A or B) as the speaker — never put the "
    "speaker label or the Target word alone as the spoken line. (3) Mention "
    "ONLY objects or parts named in the facts; do not invent other people, "
    "colors, brands, weather, locations, object condition, or unseen parts. "
    "Keep each English turn under 200 characters and to a single sentence. "
    "Return ONLY JSON matching the requested schema: a short \"scene\" phrase "
    "and a \"turns\" array of {speaker, en, zh}."
)

_DIALOGUE_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string"},
        "turns": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "en": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["speaker", "en", "zh"],
            },
        },
    },
    "required": ["scene", "turns"],
}

# Per-attempt sampling temperature. The first attempt stays conservative for
# reliability; retries escalate so a stuck 0.5B can't keep emitting the same
# off-target line (e.g. naming "plates" instead of "dining table"). Each call
# is ~1–2s, so three attempts stay far inside the 15s scenario deadline.
_RETRY_TEMPERATURES = (0.1, 0.45, 0.7)


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


def _parse(resp: str) -> dict:
    """Validate the dialogue contract; never invent a canned result."""
    data = _parse_object(resp)
    scene = str(data.get("scene") or "").strip()
    raw_turns = data.get("turns")
    if not isinstance(raw_turns, list):
        raise ValueError("model JSON has no turns array")
    turns: list[dict[str, str]] = []
    for item in raw_turns:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip()
        en = str(item.get("en") or "").strip()
        zh = str(item.get("zh") or "").strip()
        if speaker and en and zh and len(en) <= 200 and len(zh) <= 120:
            turns.append({"speaker": speaker[:24], "en": en, "zh": zh})
    if not scene or not turns:
        raise ValueError("model returned no valid dialogue")
    return {"scene": scene[:80], "turns": turns[:4]}


def _first_sentence(text: str, endings: str) -> str:
    """Trim a small-model run-on without replacing any model-written text."""
    match = re.search(f"[{re.escape(endings)}]", text)
    if match is None:
        return text.strip()
    return text[: match.end()].strip()


def _normalize_turn(turn: dict[str, str]) -> dict[str, str]:
    """Keep the first sentence of each turn when the 0.5B model over-generates."""
    return {
        "speaker": turn["speaker"],
        "en": _first_sentence(turn["en"], ".!?"),
        "zh": _first_sentence(turn["zh"], "。！？"),
    }


def _content(response: dict) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("llama.cpp returned an unexpected response") from exc
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _chat_json(
    messages: list[dict],
    schema: dict,
    max_tokens: int = 384,
    *,
    temperature: float = 0.1,
    top_p: float = 0.8,
) -> dict:
    model = _load()
    with _INFER_LOCK:
        response = model.create_chat_completion(
            messages=messages,
            temperature=temperature,
            top_p=top_p,
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


def _valid_dialogue(dialogue: dict, selected_en: str) -> bool:
    # The target anchors the vocabulary. Match the full phrase OR any of its
    # whitespace tokens (e.g. "frame" stands in for "picture frame"): a 0.5B
    # model often drops a modifier, and a head-noun hit still ties the line to
    # the clicked object. Word boundaries on every token keep "business" from
    # satisfying a "bus" target.
    needles = [selected_en] + [t for t in re.split(r"\s+", selected_en) if t]
    patterns = [
        re.compile(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", re.IGNORECASE)
        for n in needles
    ]
    turns = dialogue.get("turns", [])
    if not (2 <= len(turns) <= 4):
        return False
    if len({t["speaker"].strip().casefold() for t in turns}) < 2:
        return False  # need at least two distinct speakers
    target_anywhere = False
    for turn in turns:
        en = turn["en"].strip()
        if not (turn["speaker"].strip() and turn["zh"].strip()):
            return False
        if len(en) > 200 or len(re.findall(r"[.!?]", en)) > 1:
            return False
        if any(p.search(en) for p in patterns):
            target_anywhere = True
    return target_anywhere


def generate(
    label_en: str,
    label_zh: str = "",
    *,
    photo_context: str = "",
    scene_objects: list[str] | None = None,
    part_en: str = "",
    part_zh: str = "",
) -> dict:
    """Generate a short two-speaker everyday dialogue from compact photo facts."""
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
        f"Write a short everyday dialogue between A and B (2 or 3 turns) ABOUT the "
        f"{selected_en} itself. Speaker A's first line MUST name the {selected_en}. "
        f"Do not replace it with another object."
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
                '{"scene":"Beside a book on a desk","turns":['
                '{"speaker":"A","en":"Could you hand me that mug?",'
                '"zh":"能把那个杯子递给我吗？"},'
                '{"speaker":"B","en":"Sure — grip the handle so it doesn\'t slip.",'
                '"zh":"好，握住把手别滑了。"}]}'
            ),
        },
        {
            "role": "user",
            "content": (
                "Target: picture frame\nWhole object: picture frame\n"
                "Visible facts: a picture frame on a shelf\n"
                "Other detected objects: shelf"
            ),
        },
        {
            "role": "assistant",
            "content": (
                '{"scene":"By a shelf","turns":['
                '{"speaker":"A","en":"Is this picture frame level?",'
                '"zh":"这个相框挂正了吗？"},'
                '{"speaker":"B","en":"Looks straight to me.",'
                '"zh":"我看挺正的。"}]}'
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
                '{"scene":"Beside a car on the street","turns":['
                '{"speaker":"A","en":"Is that your bicycle next to the car?",'
                '"zh":"汽车旁边那辆自行车是你的吗？"},'
                '{"speaker":"B","en":"Yes, I ride it to work every day.",'
                '"zh":"是的，我每天骑它上班。"},'
                '{"speaker":"A","en":"Want me to move the car so you can get out?",'
                '"zh":"要我把车挪一下好让你出来吗？"}]}'
            ),
        },
        {"role": "user", "content": request},
    ]

    for attempt in range(3):
        try:
            data = _chat_json(
                messages,
                _DIALOGUE_SCHEMA,
                temperature=_RETRY_TEMPERATURES[attempt],
                top_p=0.9,
            )
            dialogue = _parse(json.dumps(data, ensure_ascii=False))
            dialogue["turns"] = [_normalize_turn(turn) for turn in dialogue["turns"]]
            if not _valid_dialogue(dialogue, selected_en):
                raise ValueError("model output is not a valid two-speaker dialogue")
            return dialogue
        except (ValueError, json.JSONDecodeError):
            if attempt >= 2:
                raise
            # Retry with a stricter, target-anchoring ask. The 0.5B occasionally
            # paraphrases the target noun away (e.g. "these things" for "cabinet",
            # or "plates" for "dining table"), so force the exact word into
            # Speaker A's first line and tell it not to substitute other objects.
            # _RETRY_TEMPERATURES escalates so the model can't repeat the same
            # off-target line.
            messages[-1] = {
                "role": "user",
                "content": (
                    f"Target: {selected_en}\nWhole object: {object_en}\n"
                    f"Visible facts: {relevant_context or object_en}\n"
                    "Other detected objects: none\n"
                    f"Write a 2-turn dialogue between speakers A and B. Speaker A's "
                    f"first line MUST contain the exact word {selected_en} — refer "
                    f"to the {selected_en} itself, not other objects. Give a "
                    f"faithful Simplified Chinese translation per turn. JSON only."
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


def extract_contents(container_label: str, caption: str) -> list[str]:
    """Extract visible independent objects placed inside or on a container."""
    schema = {
        "type": "object",
        "properties": {
            "contents": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string"},
            }
        },
        "required": ["contents"],
    }
    facts = {
        "container": _clean(container_label, 80),
        "crop_caption": _clean(caption, 700),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only independent, tangible objects explicitly visible "
                "inside or on the selected container. Exclude the container itself, "
                "people, background, colors, materials, inferred objects, and "
                "structural parts such as shelves, doors, drawers, handles, panels, "
                "walls, and frames. Return short singular English noun phrases as "
                "JSON. An award, statue, vase, book, bottle, or ornament is content."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "container": "cabinet",
                    "crop_caption": (
                        "A wooden cabinet has a gold statue on the top shelf and "
                        "several awards on the bottom shelf."
                    ),
                }
            ),
        },
        {
            "role": "assistant",
            "content": '{"contents":["gold statue","award"]}',
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "container": "bookshelf",
                    "crop_caption": "A bookshelf with books and a blue vase.",
                }
            ),
        },
        {
            "role": "assistant",
            "content": '{"contents":["book","vase"]}',
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "container": "cabinet",
                    "crop_caption": "A cabinet with two shelves and a closed door.",
                }
            ),
        },
        {"role": "assistant", "content": '{"contents":[]}'},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]
    data = _chat_json(messages, schema, max_tokens=160)
    result: list[str] = []
    seen: set[str] = set()
    for value in data.get("contents", []):
        term = _clean(value, 60).lower().strip(" .,:;")
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result[:8]


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
