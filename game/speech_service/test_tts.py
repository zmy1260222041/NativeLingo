"""Unit tests for the local Stranger TTS boundary.

These tests never call the Qwen API: the WebSocket synthesis helper is
replaced with a fake response.
"""
from __future__ import annotations

import importlib.util
import pathlib
import threading
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


class _FakeSynthesizer:
    def __init__(self, chunks: list[bytes], error_after: int | None = None):
        self._chunks = chunks
        self._error_after = error_after
        self.callback = None
        self.calls: list[str] = []

    def streaming_call(self, text: str) -> None:
        self.calls.append(text)
        def _deliver():
            sent = 0
            for chunk in self._chunks:
                if self._error_after is not None and sent >= self._error_after:
                    self.callback.on_error('{"error":"boom"}')
                    return
                self.callback.on_data(chunk)
                sent += len(chunk)
            self.callback.on_complete()
        threading.Thread(target=_deliver, daemon=True).start()

    def async_streaming_complete(self, complete_timeout_millis=600000) -> None:
        return


class _FakePool:
    def __init__(self, synthesizer):
        self.synthesizer = synthesizer
        self.borrowed = 0
        self.returned = 0

    def borrow_synthesizer(self, **kwargs):
        self.borrowed += 1
        self.synthesizer.callback = kwargs.get("callback")
        return self.synthesizer

    def return_synthesizer(self, synthesizer) -> bool:
        self.returned += 1
        return True


class StreamDynamicReplyTest(unittest.TestCase):
    PCM = bytes(range(256)) * 96  # 24 KiB of bare samples
    STREAM_WAV = (
        b"RIFF" + (0x7FFFFF00).to_bytes(4, "little") + b"WAVE" + b"fmt " +
        (16).to_bytes(4, "little") + (1).to_bytes(2, "little") +
        (1).to_bytes(2, "little") + (24000).to_bytes(4, "little") +
        (48000).to_bytes(4, "little") + (2).to_bytes(2, "little") +
        (16).to_bytes(2, "little") + b"data" + (0x7FFFFF00).to_bytes(4, "little") + PCM
    )

    def setUp(self):
        server._TTS_CACHE.clear()
        server._DYNAMIC_REPLIES.clear()
        self._old_key = server.QWEN_TTS_API_KEY
        server.QWEN_TTS_API_KEY = "test-key"

    def tearDown(self):
        server._TTS_CACHE.clear()
        server._DYNAMIC_REPLIES.clear()
        server.QWEN_TTS_API_KEY = self._old_key

    def test_stream_strips_header_and_caches_repaired_wav(self):
        reply_id = server._register_spoken_reply("tavi", "You got it.", False, prefetch=False)
        record = server._DYNAMIC_REPLIES[reply_id]
        voice = str(record.get("voice") or "")
        pool = _FakePool(_FakeSynthesizer([self.STREAM_WAV[:12000], self.STREAM_WAV[12000:]]))
        with mock.patch.object(server, "_TTS_PREFETCH_ENABLED", False), \
             mock.patch.object(server, "_tts_pool", return_value=pool):
            chunks = list(server._stream_dynamic_reply_audio("tavi", reply_id))
        self.assertEqual(b"".join(chunks), self.PCM)
        self.assertEqual(pool.borrowed, 1)
        self.assertEqual(pool.returned, 1)
        # Repaired full WAV lands in the cache for the /game/tts fallback.
        keys = [server._tts_key("tavi", reply_id, voice), server._tts_text_key("tavi", voice, "You got it.")]
        cached = server._cached_wav(keys)
        self.assertIsNotNone(cached)
        self.assertEqual(cached, server._repair_wav_lengths(self.STREAM_WAV))
        self.assertEqual(int.from_bytes(cached[4:8], "little"), len(self.STREAM_WAV) - 8)

    def test_stream_error_raises_and_returns_synthesizer(self):
        reply_id = server._register_spoken_reply("tavi", "You got it.", False, prefetch=False)
        pool = _FakePool(_FakeSynthesizer([self.STREAM_WAV[:12000]], error_after=0))
        with mock.patch.object(server, "_TTS_PREFETCH_ENABLED", False), \
             mock.patch.object(server, "_tts_pool", return_value=pool):
            with self.assertRaises(RuntimeError):
                list(server._stream_dynamic_reply_audio("tavi", reply_id))
        self.assertEqual(pool.returned, 1)

    def test_unknown_reply_raises_before_pool(self):
        pool = _FakePool(_FakeSynthesizer([self.STREAM_WAV]))
        with mock.patch.object(server, "_tts_pool", return_value=pool):
            with self.assertRaises(KeyError):
                list(server._stream_dynamic_reply_audio("tavi", "reply-not-issued"))
        self.assertEqual(pool.borrowed, 0)


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
