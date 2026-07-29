"""Micro / component-part naming for the Memorizing module (FR-14).

When the learner clicks a detected whole object, the frontend zooms into it;
this module names the visible *parts* of that cropped object (e.g. a bicycle ->
frame, handlebar, pedal, wheel, saddle). A small VLM (Qwen2.5-VL) is the right
tool here: there is no generic "parts" detection dataset, but a VLM reliably
lists sub-components of a cropped, zoomed object as text.

Lazy singleton behind ``functools.lru_cache`` (see phoneme.py) with an
``unload()`` for /memorize/release. MPS-preferred (a 3B VLM on CPU is unusably
slow); CPU fallback mirrors phoneme.py:50. The exact model id + quality are
decided by the R-13 gate.
"""
from __future__ import annotations

import functools
import re

# Smallest Qwen2.5-VL that reliably names sub-object parts. The R-13 gate may
# upsize to Qwen2.5-VL-7B if part-naming relevance < 0.75.
MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"

_PROMPT = (
    "You are naming the visible parts of a {en} ({zh}). "
    "List every distinct part you can see. Output ONLY a comma-separated list, "
    "each part as 'english/native', nothing else. "
    "Example: handle/把手, brake/刹车, wheel/车轮"
)


@functools.lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL)
    model = AutoModelForImageTextToText.from_pretrained(MODEL, torch_dtype=torch.float16)
    model.eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    return processor, model, device


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    """Release the VLM so /memorize/release can free several GB of RAM."""
    _load.cache_clear()
    import gc
    import torch
    gc.collect()
    if torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def _parse(text):
    """Parse 'en/zh, en/zh, ...' (possibly wrapped in prose) into [(en, zh)]."""
    parts = []
    for tok in re.split(r"[,;\n、]", text):
        tok = tok.strip().strip("-*•0123456789. ").strip()
        if not tok or "/" not in tok:
            continue
        en, _, zh = tok.partition("/")
        en, zh = en.strip(), zh.strip()
        if en and zh:
            parts.append({"label_en": en, "label_zh": zh})
    return parts


def name_parts(pil_crop, label_en, label_zh):
    """Name the visible parts of a cropped object image. Returns a list of
    ``{label_en, label_zh}``."""
    import torch

    processor, model, device = _load()
    prompt = _PROMPT.format(en=label_en or "this object", zh=label_zh or "")
    messages = [{"role": "user", "content": [
        {"type": "image", "image": pil_crop},
        {"type": "text", "text": prompt},
    ]}]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[pil_crop], return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=96, do_sample=False)
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    resp = processor.decode(new_tokens, skip_special_tokens=True).strip()

    parsed = _parse(resp)
    if not parsed:
        # last-resort fallback: keep whatever the model said as a single en entry
        parsed = [{"label_en": resp[:80] or "(no parts)", "label_zh": ""}]
    return parsed
