"""Unit tests for the local Stranger TTS boundary.

These tests never call the Qwen API: urlopen is replaced with a fake response.
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

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return WAV_HEADER

        with mock.patch.object(server.urllib.request, "urlopen", return_value=FakeResponse()) as urlopen:
            first = server.synthesize_npc_line("mira", "greeting")
            second = server.synthesize_npc_line("mira", "greeting", "Cherry")
        self.assertEqual(first, WAV_HEADER)
        self.assertEqual(second, WAV_HEADER)
        self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
