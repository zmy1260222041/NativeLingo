"""Survival module scenario loading + deterministic delivery judgement (FR-22).

WHY THE MATCHER IS DUPLICATED FROM scripts/game_delivery_gate.py
  `normalise` / `accept_pattern` / `match_slot` / `evaluate` below are copied
  VERBATIM from scripts/game_delivery_gate.py:143-216. That script is the G1
  measurement harness; if the two implementations ever diverge, the harness
  stops measuring the product and G1's precision/recall numbers become
  meaningless. The copy exists (rather than an import) because scripts/ is not
  bundled by desktop/backend/freeze.spec -- product code cannot reach it at
  runtime. tests/test_game_scenario.py imports both and asserts bit-identical
  output on a shared corpus, so the duplication is enforced, not hoped for.
  Change one side => change the other side => the assertion test tells you.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
  No fluency, naturalness or 地道度 scoring. `delivery` is a deterministic
  slot-hit rate -- it *is* G1's criterion -- so it may be shown to the learner.
  Every other dimension's threshold is unfixed until R-14 G7; emitting one now
  would make an uncalibrated number look finished.
"""
from __future__ import annotations

import json
import os
import re

# --------------------------------------------------------------------------
# §6.1 deterministic matcher -- VERBATIM from scripts/game_delivery_gate.py.
# Do not "improve" anything below this line without updating the harness and
# re-running: python scripts/game_delivery_gate.py
# --------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Whitespace normalisation only (§6.1). Curly quotes folded to ASCII so a
    transcript artefact does not masquerade as a matcher failure. No stemming,
    no contraction expansion, no article/tense repair -- §6.1 forbids grammar
    checking, and silently normalising morphology would hide real recall gaps
    that belong in the `accept` sets instead."""
    return " ".join(str(text or "").replace("’", "'").replace("‘", "'").split())


def accept_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern for one `accept` entry.

    Reuses the in-production idiom of core/scenario.py:223 --
    `(?<![A-Za-z])...(?![A-Za-z])` with re.IGNORECASE -- so "bus" cannot hit
    "business". Multi-word phrases are matched as a whole after whitespace
    normalisation, with `\\s+` between tokens so "give  me" still matches.
    """
    tokens = [t for t in normalise(term).split(" ") if t]
    if not tokens:
        raise ValueError("empty accept term")
    body = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE)


def match_slot(slot: dict, text: str) -> tuple[bool, list[str]]:
    """Return (hit, matched accept terms) for one slot against a response."""
    matched = []
    for term in slot.get("accept") or []:
        try:
            pattern = accept_pattern(term)
        except ValueError:
            continue
        if pattern.search(text):
            matched.append(term)
    return bool(matched), matched


def evaluate(scenario: dict, response: str, min_required_rate: float = 1.0) -> dict:
    """Deterministic delivery scoring for one response.

    delivery: required-slot hit rate is the body (0..85); optional slots add up
    to 15 on top. Optional slots therefore move the reward band of §5.4 but can
    never decide whether the meaning got across -- `delivered` reads required
    slots only, per §5.3.
    """
    text = normalise(response)
    slots = []
    for slot in scenario.get("slots") or []:
        hit, matched = match_slot(slot, text)
        slots.append(
            {
                "key": slot.get("key", "?"),
                "required": bool(slot.get("required")),
                "hit": hit,
                "matched": matched,
                "accept": list(slot.get("accept") or []),
            }
        )
    required = [s for s in slots if s["required"]]
    optional = [s for s in slots if not s["required"]]
    req_rate = (
        sum(1 for s in required if s["hit"]) / len(required) if required else 0.0
    )
    opt_rate = (
        sum(1 for s in optional if s["hit"]) / len(optional) if optional else 0.0
    )
    return {
        "text": text,
        "slots": slots,
        "required_rate": req_rate,
        "optional_rate": opt_rate,
        "delivery": round(85.0 * req_rate + 15.0 * opt_rate, 1),
        "delivered": req_rate >= min_required_rate - 1e-9,
    }

# --------------------------------------------------------------------------
# end of the verbatim block
# --------------------------------------------------------------------------


TIERS = ("infant", "toddler", "youth", "professional")


def scenarios_dir() -> str:
    """The shipped scenario library, always inside the package (read-only data,
    unlike recordings -- those go to NATIVELINGO_DATA_DIR, see game_store)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_scenarios")


def load_scenarios(path: str | None = None) -> tuple[dict[str, dict], list[str]]:
    """Load `*.json` scenarios. Tolerant by design, same rules as the G1
    harness: a missing dir, an empty one, a malformed file, a scenario with no
    required slot and a duplicate id are all *reported* rather than fatal, so
    one bad file cannot take the module down."""
    if path is None:
        path = scenarios_dir()
    notes: list[str] = []
    scenarios: dict[str, dict] = {}
    if not os.path.isdir(path):
        notes.append(f"scenario dir not found: {path}")
        return scenarios, notes
    names = sorted(n for n in os.listdir(path) if n.endswith(".json"))
    if not names:
        notes.append(f"scenario dir is empty: {path}")
    for name in names:
        full = os.path.join(path, name)
        try:
            with open(full, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            notes.append(f"unreadable scenario {name}: {exc}")
            continue
        sid = data.get("id")
        if not sid:
            notes.append(f"scenario {name} has no id, skipped")
            continue
        if not [s for s in (data.get("slots") or []) if s.get("required")]:
            notes.append(f"scenario {sid} has no required slot, skipped")
            continue
        if sid in scenarios:
            notes.append(f"duplicate scenario id {sid} ({name}), keeping the first")
            continue
        scenarios[sid] = data
    return scenarios, notes


def hotword_terms(scenario: dict) -> list[str]:
    """Every `accept` term of the scenario, for the decoding prior in
    game_transcribe. The game knows the scenario before the learner speaks, so
    this is free -- and it biases towards *which words could occur here* (dozens
    of equivalent phrasings across the slots), not towards one answer."""
    terms: list[str] = []
    seen: set[str] = set()
    for slot in scenario.get("slots") or []:
        for term in slot.get("accept") or []:
            t = normalise(term)
            key = t.lower()
            if t and key not in seen:
                seen.add(key)
                terms.append(t)
    return terms


def _pick(options, seed: int):
    """Deterministic choice from an NPC response list. Deterministic rather than
    random so an attempt replayed from its stored JSON reproduces exactly what
    the learner saw."""
    items = [o for o in (options or []) if str(o or "").strip()]
    if not items:
        return None
    return items[seed % len(items)]


def npc_reply(scenario: dict, verdict: dict, seed: int = 0) -> dict:
    """Pick the NPC's three-tier reaction: hit when every required slot landed,
    miss when none did, partial in between."""
    required = [s for s in verdict["slots"] if s["required"]]
    hits = sum(1 for s in required if s["hit"])
    if required and hits == len(required):
        band = "hit"
    elif hits == 0:
        band = "miss"
    else:
        band = "partial"
    responses = ((scenario.get("npc") or {}).get("responses") or {})
    return {"band": band, "line": _pick(responses.get(band), seed)}


def reward_for(scenario: dict, delivery: float) -> dict:
    """Highest reward band whose `min_delivery` the score reaches.

    Below the lowest band the learner gets nothing but -- per §5.4 -- spends no
    attempt: `retry_free` is always True, which is also what makes precision the
    asymmetric side of G1 (a false negative only costs a retry)."""
    bands = sorted(
        (b for b in (scenario.get("reward") or []) if b.get("min_delivery") is not None),
        key=lambda b: float(b["min_delivery"]),
        reverse=True,
    )
    for band in bands:
        if delivery >= float(band["min_delivery"]) - 1e-9:
            return {
                "quality": band.get("quality"),
                "items": [dict(i) for i in (band.get("items") or [])],
                "retry_free": True,
            }
    return {"quality": None, "items": [], "retry_free": True}


def judge(scenario: dict, response: str, seed: int = 0,
          min_required_rate: float = 1.0) -> dict:
    """One learner response -> everything the beta build needs to render.

    Carries `delivery` (G1's own criterion, safe to show) and nothing else
    scored. `new_words` rides along so the NPC's reply can gloss the words it
    just used -- that is the vocabulary-acquisition path of FR-25, not a score.
    """
    verdict = evaluate(scenario, response, min_required_rate=min_required_rate)
    return {
        "scenario_id": scenario.get("id"),
        "tier": scenario.get("tier"),
        "transcript": verdict["text"],
        "slots": verdict["slots"],
        "delivery": verdict["delivery"],
        "delivered": verdict["delivered"],
        "npc": npc_reply(scenario, verdict, seed=seed),
        "reward": reward_for(scenario, verdict["delivery"]),
        "new_words": [dict(w) for w in (scenario.get("new_words") or [])],
    }
