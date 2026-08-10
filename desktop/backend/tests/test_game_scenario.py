"""Survival delivery judgement (FR-22) — and the guard that keeps it honest.

THE LOAD-BEARING TEST HERE IS test_matcher_bit_identical_to_g1_harness.
core/game_scenario.py carries a verbatim copy of the matcher from
scripts/game_delivery_gate.py, because scripts/ is not bundled by freeze.spec
and product code cannot import it at runtime. A copy that silently drifts is
worse than no copy at all: the G1 harness would keep reporting precision/recall
for an implementation the product no longer uses, and R-14's G1 verdict would be
measuring nothing. That test loads the harness by file path and compares both
implementations field-by-field on every scenario in the shipped library.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

from backend.core import game_scenario

_REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
_GATE = os.path.join(_REPO, "scripts", "game_delivery_gate.py")


@pytest.fixture(scope="module")
def gate():
    """Load scripts/game_delivery_gate.py as a module by path (it is a CLI, not
    an installed package — R-1/R-4/R-13 precedent keeps gate harnesses there)."""
    if not os.path.isfile(_GATE):
        pytest.skip(f"G1 harness not present: {_GATE}")
    spec = importlib.util.spec_from_file_location("g1_gate", _GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scenarios():
    loaded, notes = game_scenario.load_scenarios()
    assert loaded, f"scenario library failed to load: {notes}"
    return loaded


# Responses spanning the cases the matcher must get right: full hit, partial,
# miss, multi-word accept terms, the substring trap, casing and curly quotes.
_PROBES = [
    "",
    "bread",
    "i want bread",
    "I WANT BREAD PLEASE",
    "can i have some bread, please",
    "me want bread",
    "give  me   bread",
    "i'm hungry",
    "i’m hungry",  # curly apostrophe must fold to the ASCII form
    "business",    # must not hit a "bus" accept term anywhere
    "breading breads unbread",
    "blanket i cold",
    "i need water",
    "thank you",
    "uh... i, i want, want the thing",
]


def test_matcher_bit_identical_to_g1_harness(gate, scenarios):
    """R-14 acceptance: product and harness must agree on every field."""
    compared = 0
    for sid, scenario in sorted(scenarios.items()):
        for response in _PROBES:
            mine = game_scenario.evaluate(scenario, response)
            theirs = gate.evaluate(scenario, response)
            assert mine == theirs, f"matcher drift on {sid!r} / {response!r}"
            compared += 1
    assert compared >= len(_PROBES), "no comparisons ran"


def test_normalise_and_pattern_match_harness(gate):
    for text in _PROBES + ["  spaced   out  ", None, "‘quoted’"]:
        assert game_scenario.normalise(text) == gate.normalise(text)
    for term in ["bread", "give me", "can i have", "GIVE  ME"]:
        assert (
            game_scenario.accept_pattern(term).pattern
            == gate.accept_pattern(term).pattern
        )


def test_word_boundary_not_substring():
    slot = {"key": "k", "required": True, "accept": ["bus", "eat"]}
    assert match(slot, "business") is False
    assert match(slot, "i eat") is True
    assert match(slot, "eating") is False  # "eat" must not hit "eating"


def match(slot, text) -> bool:
    hit, _ = game_scenario.match_slot(slot, game_scenario.normalise(text))
    return hit


def test_delivery_bands_and_delivered_reads_required_only():
    scenario = {
        "id": "t",
        "slots": [
            {"key": "a", "required": True, "accept": ["bread"]},
            {"key": "b", "required": True, "accept": ["want"]},
            {"key": "c", "required": False, "accept": ["please"]},
        ],
    }
    both = game_scenario.evaluate(scenario, "i want bread")
    assert both["delivery"] == 85.0 and both["delivered"] is True
    polite = game_scenario.evaluate(scenario, "i want bread please")
    assert polite["delivery"] == 100.0 and polite["delivered"] is True
    # An optional slot alone can move the band but never carry `delivered`.
    only_opt = game_scenario.evaluate(scenario, "please")
    assert only_opt["delivered"] is False and only_opt["delivery"] == 15.0
    half = game_scenario.evaluate(scenario, "bread")
    assert half["delivered"] is False and half["delivery"] == 42.5


def test_npc_bands_follow_required_hits(scenarios):
    scenario = scenarios["food-ask-bread"]
    assert game_scenario.judge(scenario, "i want bread")["npc"]["band"] == "hit"
    assert game_scenario.judge(scenario, "bread")["npc"]["band"] == "partial"
    assert game_scenario.judge(scenario, "hello there")["npc"]["band"] == "miss"


def test_npc_line_is_deterministic_for_a_seed(scenarios):
    scenario = scenarios["food-ask-bread"]
    a = game_scenario.judge(scenario, "i want bread", seed=7)["npc"]["line"]
    b = game_scenario.judge(scenario, "i want bread", seed=7)["npc"]["line"]
    assert a == b and a  # replaying a stored attempt reproduces what was shown


def test_reward_bands_and_free_retry(scenarios):
    scenario = scenarios["food-ask-bread"]
    generous = game_scenario.reward_for(scenario, 100.0)
    assert generous["quality"] == "generous" and generous["items"]
    assert game_scenario.reward_for(scenario, 85.0)["quality"] == "plain"
    assert game_scenario.reward_for(scenario, 42.5)["quality"] == "scrap"
    nothing = game_scenario.reward_for(scenario, 0.0)
    assert nothing["quality"] is None and nothing["items"] == []
    # §5.4: below the lowest band costs no attempt — that is what makes a false
    # negative cheap, and precision the asymmetric side of G1.
    assert nothing["retry_free"] is True
    assert generous["retry_free"] is True


def test_judge_emits_no_uncalibrated_score(scenarios):
    """红线 3: delivery is G1's own criterion and may ship. Nothing else may."""
    result = game_scenario.judge(scenarios["food-ask-bread"], "i want bread")
    forbidden = {"fluency", "naturalness", "idiomaticity", "accuracy", "score",
                 "nativeness", "地道度"}
    assert not forbidden & set(result), f"uncalibrated score leaked: {result.keys()}"


def test_hotword_terms_dedupe_across_slots(scenarios):
    """`please` appears in two slots of food-ask-bread; the decoding prior must
    list it once."""
    terms = game_scenario.hotword_terms(scenarios["food-ask-bread"])
    assert len(terms) == len({t.lower() for t in terms})
    assert "bread" in terms and "please" in terms


def test_load_scenarios_is_tolerant(tmp_path):
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "no-id.json").write_text('{"slots": []}', encoding="utf-8")
    (tmp_path / "no-required.json").write_text(
        '{"id": "x", "slots": [{"key": "a", "required": false, "accept": ["a"]}]}',
        encoding="utf-8",
    )
    (tmp_path / "ok.json").write_text(
        '{"id": "y", "slots": [{"key": "a", "required": true, "accept": ["a"]}]}',
        encoding="utf-8",
    )
    loaded, notes = game_scenario.load_scenarios(str(tmp_path))
    assert set(loaded) == {"y"}          # one bad file cannot take the module down
    assert len(notes) == 3               # ... but every skip is reported


def test_shipped_library_loads_clean(scenarios):
    """Every shipped scenario must survive the tolerant loader — a note here
    means a scenario silently stopped being reachable in the game."""
    _, notes = game_scenario.load_scenarios()
    assert notes == [], f"shipped scenario library has problems: {notes}"
    assert len(scenarios) >= 40, f"expected the 45-scenario library, got {len(scenarios)}"
    for sid, s in scenarios.items():
        assert s.get("tier") in game_scenario.TIERS, f"{sid}: bad tier {s.get('tier')!r}"
        assert (s.get("situation") or {}).get("zh"), f"{sid}: no Chinese situation"
        assert ((s.get("npc") or {}).get("responses") or {}).keys() >= {
            "hit", "partial", "miss"
        }, f"{sid}: incomplete NPC responses"
