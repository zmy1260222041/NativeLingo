"""Tests for grounding observed YouTube exchanges into Godot patterns.

Plain unittest (also collected by pytest) so `unittest discover` runs them
without pytest installed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import ground_patterns as gp  # noqa: E402


def _scenario(acts=None):
    return {
        "data": {
            "godot_scenario_id": "food_ask_bread",
            "allowed_speech_acts": acts or ["acknowledge_need", "offer_choice", "clarify_request"],
        },
        "path": Path("/tmp/unused.json"),
    }


def _entry(**overrides):
    entry = {
        "scenario_id": "food_ask_bread",
        "tier": "us_onlocation_vlog_oembed",
        "video_id": "abc123",
        "source_url": "https://www.youtube.com/watch?v=abc123&t=35s",
        "title": "A vlog",
        "channel": "A channel",
        "speaker_role": "counter_worker",
        "anchor_seconds": 35,
        "observed_exchange": ["Um can I get the Calabrese?", "Just one slice?", "Just one, please"],
        "grounded_turn_index": 1,
        "grounded_text": "just one slice",
        "speech_act": "clarify_request",
        "emotion": "warm",
        "verification": {},
    }
    entry.update(overrides)
    return entry


class GroundPatternsTest(unittest.TestCase):
    def test_normalize_line_cleans_markers_and_punctuation(self):
        assert gp.normalize_line(">> how can I help you") == "How can I help you."
        assert gp.normalize_line("Anything else?") == "Anything else?"
        assert gp.normalize_line("  spaced   out  ") == "Spaced out."

    def test_validate_entry_accepts_curated_exchange(self):
        assert gp.validate_entry(_entry(), {"food_ask_bread": _scenario()}) == ""

    def test_validate_entry_rejects_bad_acts_tiers_and_text(self):
        scenarios = {"food_ask_bread": _scenario()}
        assert gp.validate_entry(_entry(speech_act="close_transaction"), scenarios) == "speech_act_not_allowed"
        assert gp.validate_entry(_entry(tier="unverified"), scenarios) == "tier_not_allowed"
        assert gp.validate_entry(_entry(grounded_turn_index=9), scenarios) == "grounded_turn_index_out_of_range"
        assert gp.validate_entry(_entry(grounded_text="learn english with this line"), scenarios) == "grounded_text_hits_teaching_marker"
        assert gp.validate_entry(_entry(grounded_text=" ".join(["word"] * 25)), scenarios) == "grounded_text_too_long"
        assert gp.validate_entry(_entry(source_url="https://example.com"), scenarios) == "source_url_video_mismatch"

    def test_build_pattern_keeps_evidence_chain(self):
        pattern = gp.build_pattern(_entry(), 1)
        assert pattern["id"] == "food_ask_bread_yt_01"
        assert pattern["text"] == "Just one slice."
        assert pattern["evidence_ids"] == [pattern["provenance"]["grounding"]["evidence_id"]]
        assert pattern["provenance"]["rights"] == "project_owned"
        assert pattern["provenance"]["grounding"]["observed_exchange"][1] == "Just one slice?"

    def test_run_end_to_end_dedupes_and_updates_scenarios(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        tmp_path = Path(temp.name)
        scenario_dir = tmp_path / "scenarios"
        scenario_dir.mkdir()
        (scenario_dir / "food_ask_bread.json").write_text(json.dumps({
            "godot_scenario_id": "food_ask_bread",
            "allowed_speech_acts": ["offer_choice"],
            "response_pattern_ids": ["food_ask_bread_01"],
            "provenance": {"status": "provisional_source_first_pending"},
        }), encoding="utf-8")
        pattern_dir = tmp_path / "patterns"
        pattern_dir.mkdir()
        (pattern_dir / "authored.json").write_text(json.dumps({
            "schema_version": 1,
            "patterns": [{"id": "food_ask_bread_01", "scenario_id": "food_ask_bread", "text": "Anything else?"}],
        }), encoding="utf-8")
        evidence = {
            "schema_version": 1,
            "exchanges": [
                _entry(grounded_text="Anything else?", speech_act="offer_choice", grounded_turn_index=1),
                _entry(grounded_text="For here or to go?", speech_act="offer_choice", grounded_turn_index=1),
            ],
            "exclusions": [],
        }
        evidence_path = tmp_path / "grounding_evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        with mock.patch.object(gp, "SCENARIO_DIR", scenario_dir), mock.patch.object(gp, "PATTERN_DIR", pattern_dir):
            exit_code = gp.run(evidence_path, tmp_path / "audit.json")
        assert exit_code == 1  # duplicate entry is reported, not silently shipped
        output = json.loads((pattern_dir / gp.OUTPUT_NAME).read_text(encoding="utf-8"))
        assert [item["id"] for item in output["patterns"]] == ["food_ask_bread_yt_01"]
        assert output["patterns"][0]["text"] == "For here or to go?"
        scenario = json.loads((scenario_dir / "food_ask_bread.json").read_text(encoding="utf-8"))
        assert scenario["response_pattern_ids"] == ["food_ask_bread_01", "food_ask_bread_yt_01"]
        assert scenario["provenance"]["status"] == "corpus_grounded_provisional"
        audit = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
        assert audit["skipped"][0]["reason"] == "duplicate_of_existing_pattern"


if __name__ == "__main__":
    unittest.main()
