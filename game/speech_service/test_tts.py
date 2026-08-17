"""Unit tests for the local Stranger TTS boundary.

These tests never call the Qwen API: the WebSocket synthesis helper is
replaced with a fake response.
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest
from unittest import mock

SERVER_PATH = pathlib.Path(__file__).resolve().parent / "server.py"
_spec = importlib.util.spec_from_file_location("stranger_speech_server", SERVER_PATH)
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

WAV_HEADER = (
    b"RIFF" + (44 - 8).to_bytes(4, "little") + b"WAVE" + b"fmt " +
    (16).to_bytes(4, "little") + (1).to_bytes(2, "little") +
    (1).to_bytes(2, "little") + (16000).to_bytes(4, "little") +
    (32000).to_bytes(4, "little") + (2).to_bytes(2, "little") +
    (16).to_bytes(2, "little") + b"data" + (0).to_bytes(4, "little")
)


class NpcLineCatalogTest(unittest.TestCase):
    def test_all_five_npcs_have_greeting_audio_text(self):
        for npc_id in ["mira", "rowan", "tavi", "vesh", "ori"]:
            self.assertIn(npc_id, server.NPC_LINES)
            self.assertIn("greeting", server.NPC_LINES[npc_id])
            self.assertTrue(server.NPC_LINES[npc_id]["greeting"].strip())


class SynthesizeNpcLineTest(unittest.TestCase):
    def setUp(self):
        server._TTS_CACHE.clear()
        self._old_key = server.QWEN_TTS_API_KEY

    def tearDown(self):
        server._TTS_CACHE.clear()
        server.QWEN_TTS_API_KEY = self._old_key

    def test_unknown_line_rejected_before_network(self):
        with self.assertRaises(KeyError):
            server.synthesize_npc_line("mira", "not-a-line")

    def test_missing_key_is_a_safe_503_reason(self):
        server.QWEN_TTS_API_KEY = ""
        with self.assertRaises(RuntimeError):
            server.synthesize_npc_line("mira", "greeting")

    def test_success_caches_by_npc_line_voice(self):
        server.QWEN_TTS_API_KEY = "test-key"
        calls: list[str] = []

        def fake_speech(text: str, voice: str) -> bytes:
            calls.append(voice)
            return WAV_HEADER

        with mock.patch.object(server, "_dashscope_speech", side_effect=fake_speech):
            first = server.synthesize_npc_line("mira", "greeting")
            second = server.synthesize_npc_line("mira", "greeting")
            explicit = server.synthesize_npc_line("mira", "greeting", "longanlufeng")
        self.assertEqual(first, WAV_HEADER)
        self.assertEqual(second, WAV_HEADER)
        # Same catalog voice hits the cache; a different voice synthesizes again.
        self.assertEqual(calls, [server.NPC_TTS_VOICES["mira"], "longanlufeng"])

    def test_voice_resolves_to_npc_default(self):
        server.QWEN_TTS_API_KEY = "test-key"
        seen: list[str] = []

        def fake_speech(text: str, voice: str) -> bytes:
            seen.append(voice)
            return WAV_HEADER

        with mock.patch.object(server, "_dashscope_speech", side_effect=fake_speech):
            server.synthesize_npc_line("tavi", "clarify")
        self.assertEqual(seen, [server.NPC_TTS_VOICES["tavi"]])

    def test_spoken_choice_matches_one_catalog_word(self):
        with mock.patch.object(server, "_transcribe_with_hotwords", return_value=("I want food", {})), \
             mock.patch.object(server, "score_word", return_value={
                 "accepted": True, "text": "food", "reason": "VOICE_REASON_ACCEPTED",
                 "pronunciation": 85.0, "score": 85.0, "pronunciation_source": "reference_dtw", "band": "generous",
             }):
            verdict = server.score_word_choice(["food", "water", "parts"], "/tmp/not-used.wav")
        self.assertEqual(verdict["lexical_id"], "food")
        self.assertTrue(verdict["accepted"])

    def test_ambiguous_spoken_choice_is_clarify(self):
        with mock.patch.object(server, "_transcribe_with_hotwords", return_value=("food water", {})):
            verdict = server.score_word_choice(["food", "water"], "/tmp/not-used.wav")
        self.assertFalse(verdict["accepted"])
        self.assertEqual(verdict["lexical_id"], "")

    def test_word_practice_ask_is_built_from_catalog_ids(self):
        self.assertEqual(
            server.word_practice_ask_text(["food", "water", "parts"]),
            "Do you want food, water, or parts?",
        )
        with self.assertRaises(KeyError):
            server.word_practice_ask_text(["free-text"])


if __name__ == "__main__":
    unittest.main()


class WordScoreTest(unittest.TestCase):
    def test_catalog_contains_social_practice_words(self):
        for word in ["morning", "food", "heater", "water", "help"]:
            self.assertIn(word, server.WORD_LINES)

    def test_reference_dtw_path_is_labelled(self):
        with mock.patch.object(server, "word_pronunciation", return_value=85.0):
            verdict = server.score_word("morning", "/tmp/not-used.wav")
        self.assertEqual(verdict["pronunciation_source"], "reference_dtw")
        self.assertEqual(verdict["band"], "generous")
        self.assertTrue(verdict["accepted"])

    def test_whisper_fallback_never_claims_reference(self):
        with mock.patch.object(server, "word_pronunciation", return_value=None), \
             mock.patch.object(server, "_transcribe_with_hotwords", return_value=("morning", {})):
            verdict = server.score_word("morning", "/tmp/not-used.wav")
        self.assertEqual(verdict["pronunciation_source"], "whisper_confidence")
        self.assertEqual(verdict["pronunciation"], 80.0)
