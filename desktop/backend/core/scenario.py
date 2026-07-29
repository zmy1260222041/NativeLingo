"""Scenario example-sentence generation for the Memorizing module (FR-15).

Given an object/part name, generate 1-3 vivid target-language (English) example
sentences that place it in a memorable real-world situation (the "车把手" -> bus
sharp-turn -> "grip the handrail" idea), each with a Chinese gloss. This is a
*memory reinforcement* aid, text-only, deliberately separate from the Speaking
module's pronunciation evaluation -- so it never produces a synthetic reference
audio and cannot collide with FR-M1.

A very small instruct LLM is used ("越小越好"): default Qwen2.5-1.5B-Instruct,
with the R-13 gate escalating 0.5B -> 1.5B -> 3B until fluency >= 4.0. Lazy
singleton + unload() mirror parts.py.
"""
from __future__ import annotations

import functools
import json
import re

# Smallest viable instruct model with usable English fluency. R-13 decides the
# final tier (0.5B / 1.5B / 3B) and writes the choice back here.
MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

_SYSTEM = (
    "You write short, vivid English example sentences that help a Chinese learner "
    "remember an everyday word by placing it in a concrete real-life situation. "
    "Always return strict JSON."
)


@functools.lru_cache(maxsize=1)
def _load():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16)
    model.eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    return tokenizer, model, device


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def unload() -> None:
    """Release the LLM so /memorize/release can free RAM."""
    _load.cache_clear()
    import gc
    import torch
    gc.collect()
    if torch.backends.mps.is_available():
        try:
            torch.mps.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def _parse(resp):
    """Defensively extract a sentences list from the model output (Qwen often
    wraps JSON in ```json fences or adds a leading line)."""
    resp = resp.strip()
    m = re.search(r"\{.*\}", resp, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            sents = data.get("sentences", [])
            out = []
            for s in sents:
                en, zh = s.get("en"), s.get("zh")
                if en:
                    out.append({"en": str(en).strip(), "zh": str(zh or "").strip()})
            if out:
                return out[:3]
        except Exception:  # noqa: BLE001
            pass
    # fallback: treat non-empty lines as English-only sentences
    return [{"en": ln.strip(), "zh": ""} for ln in resp.splitlines() if ln.strip()][:3]


def generate(label_en, label_zh):
    """Generate 1-3 bilingual example sentences for an object/part. Returns a
    list of ``{en, zh}``."""
    import torch

    tokenizer, model, device = _load()
    user = (
        f'Generate 2 vivid English example sentences that place the word '
        f'"{label_en}" ({label_zh}) in a memorable real-world situation. '
        f'For each sentence also give the Chinese translation. '
        f'Respond ONLY with JSON: {{"sentences":[{{"en":"...","zh":"..."}}]}}.'
    )
    messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    resp = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    sents = _parse(resp)
    if not sents:
        sents = [{"en": f"I use my {label_en} every day.", "zh": ""}]
    return sents
