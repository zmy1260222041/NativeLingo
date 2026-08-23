import contextlib
import io
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


def gemini_stream_factory(lines, captured=None, delay=0.0):
    """Build a fake server._gemini_post_stream replacement.

    ``lines`` are yielded verbatim as SSE body lines; ``captured`` records the
    request (url/headers/body/timeout) the way the old urlopen fakes did.
    """

    def factory(url, headers, body, timeout):
        if captured is not None:
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["body"] = json.loads(body.decode("utf-8"))
            captured["timeout"] = timeout

        @contextlib.contextmanager
        def _cm():
            if delay:
                time.sleep(delay)
            yield iter([line if isinstance(line, bytes) else line.encode("utf-8") for line in lines])

        return _cm()

    return factory


def gemini_json_lines(payload: dict) -> list[bytes]:
    return [json.dumps(payload).encode("utf-8") + b"\n"]


class DialogueAssetTest(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(
            server.os.environ,
            {"XAI_API_KEY": "", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""},
            clear=False,
        )
        self.env_patch.start()
        server._DYNAMIC_REPLIES.clear()
        server._TTS_PREFETCH_ENABLED = False
        server._GEMINI_LATENCY["first_ms"].clear()
        server._GEMINI_LATENCY["misses"] = 0
        server._GEMINI_ADAPTIVE_LAST["speak"] = 0.0
        server._GEMINI_ADAPTIVE_LAST["timeout"] = 0.0
        server._load_dialogue_assets()

    def tearDown(self):
        server._TTS_PREFETCH_ENABLED = True
        self.env_patch.stop()

    def test_three_service_points_are_role_cards(self):
        expected = {"food_counter", "convenience_store", "parts_desk"}
        self.assertEqual(set(server._DIALOGUE_SCENARIOS), expected)
        self.assertEqual(server._DIALOGUE_SCENARIOS["food_counter"]["npc_id"], "tavi")
        self.assertEqual(server._DIALOGUE_SCENARIOS["convenience_store"]["npc_id"], "ori")
        self.assertEqual(server._DIALOGUE_SCENARIOS["parts_desk"]["npc_id"], "vesh")
        for scenario in server._DIALOGUE_SCENARIOS.values():
            self.assertTrue(scenario.get("inventory"))
            self.assertTrue(scenario.get("role"))
            self.assertTrue(scenario.get("location"))

    def test_occupations_pair_clerks_with_workplaces(self):
        expected = {
            "tavi": ("food_counter_server", "food", "env_market_stall_a"),
            "ori": ("convenience_store_cashier", "water", "pending_convenience_store"),
            "mira": ("market_greeter", "none", "env_plaza_market_a"),
            "vesh": ("hardware_parts_clerk", "none", "pending_parts_desk"),
            "rowan": ("resident_neighbor", "none", "env_plaza_market_a"),
        }
        self.assertEqual(set(server._DIALOGUE_PROFILES), set(expected))
        food_sellers = [
            npc_id
            for npc_id, profile in server._DIALOGUE_PROFILES.items()
            if "food" in (profile.get("sells") or [])
        ]
        water_sellers = [
            npc_id
            for npc_id, profile in server._DIALOGUE_PROFILES.items()
            if "water" in (profile.get("sells") or [])
        ]
        self.assertEqual(food_sellers, ["tavi"])
        self.assertEqual(water_sellers, ["ori"])
        for npc_id, (occupation, mainline, asset) in expected.items():
            profile = server._DIALOGUE_PROFILES[npc_id]
            self.assertEqual(profile.get("occupation"), occupation)
            self.assertEqual(profile.get("mainline"), mainline)
            self.assertEqual((profile.get("workplace") or {}).get("asset"), asset)
        self.assertEqual(server._DIALOGUE_PROFILES["mira"].get("sells"), [])
        tavi_anchor = server._DIALOGUE_PROFILES["tavi"]["workplace"]["anchor"]
        self.assertLess(
            ((tavi_anchor[0] + 1.8) ** 2 + (tavi_anchor[2] + 2.2) ** 2) ** 0.5,
            2.0,
        )

    def test_dialogue_logs_what_was_heard(self):
        captured = io.StringIO()
        with redirect_stdout(captured):
            server.generate_dialogue_reply({
                "npc_id": "tavi",
                "scenario_id": "food_counter",
                "transcript": "Can I get two portions please?",
                "history": [],
            })
        logged = captured.getvalue()
        self.assertIn("[speech] heard channel=dialogue", logged)
        self.assertIn("Can I get two portions please?", logged)
        self.assertIn("npc=tavi", logged)

    def test_log_heard_truncates_and_skips_empty_fields(self):
        captured = io.StringIO()
        with redirect_stdout(captured):
            server._log_heard("transcribe", "portions", target="tavi", extra="")
        logged = captured.getvalue()
        self.assertIn("channel=transcribe", logged)
        self.assertIn("text='portions'", logged)
        self.assertIn("target=tavi", logged)
        self.assertNotIn("extra=", logged)

    def test_same_counter_accepts_two_legal_orders(self):
        burger = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get a burger, please?",
            "history": [],
        })
        coffee = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Could I have a coffee to go?",
            "history": [],
        })
        self.assertTrue(burger["player_turn"]["transaction_complete"])
        self.assertTrue(coffee["player_turn"]["transaction_complete"])
        self.assertEqual(burger["next_state"], "closed")
        self.assertGreaterEqual(burger["player_turn"]["idiomaticity"], 70)

    def test_convenience_store_sells_water_but_not_heater_repair(self):
        water = server.generate_dialogue_reply({
            "npc_id": "ori",
            "scenario_id": "convenience_store",
            "transcript": "Can I get a bottle of water?",
            "history": [],
        })
        heater = server.generate_dialogue_reply({
            "npc_id": "ori",
            "scenario_id": "convenience_store",
            "transcript": "Can I get you to repair the heater?",
            "history": [],
        })
        self.assertTrue(water["player_turn"]["transaction_complete"])
        self.assertFalse(heater["player_turn"]["transaction_complete"])
        self.assertTrue(heater["player_turn"]["off_inventory"])
        self.assertNotEqual(heater["next_state"], "closed")

    def test_irrelevant_transcript_is_rejected_before_generation(self):
        with self.assertRaisesRegex(ValueError, "irrelevant transcript"):
            server.generate_dialogue_reply({
                "npc_id": "tavi",
                "scenario_id": "food_counter",
                "transcript": "Tell me how to repair a spaceship.",
                "history": [],
            })

    def test_follow_up_to_go_can_close_an_in_progress_order(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        history = [
            {"role": "player", "text": "Uh, coffee?"},
            {"role": "npc", "text": "Coffee. Here or to go?"},
        ]
        turn = server._normalise_player_turn(
            {"idiomaticity": 90, "progress": "done", "transaction_complete": True, "off_inventory": False},
            "To go, please.",
            scenario,
            history,
        )
        self.assertFalse(turn["off_inventory"])
        self.assertTrue(turn["transaction_complete"])

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            server.generate_dialogue_reply({
                "npc_id": "tavi",
                "scenario_id": "food_ask_bread",
                "transcript": "hello",
            })

    def test_quality_gate_rejects_teacher_talk_and_long_replies(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        gate = server._dialogue_gate(
            scenario,
            "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty one two three four five six seven eight nine ten eleven",
            "offer_choice",
        )
        self.assertFalse(gate["accepted"])
        self.assertIn("too_long", gate["violations"])
        gate = server._dialogue_gate(scenario, "Your pronunciation score is 80. Repeat after me.", "confirm_order")
        self.assertFalse(gate["accepted"])
        self.assertIn("teacher_talk", gate["violations"])

    def test_dynamic_tts_never_accepts_an_unknown_reply_id(self):
        with self.assertRaises(KeyError):
            server.synthesize_dynamic_reply("tavi", "reply-not-issued")

    def test_retry_selects_a_different_stub_closing_line(self):
        body = {
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get a burger?",
            "history": [],
        }
        first = server.generate_dialogue_reply(body)
        second = server.generate_dialogue_reply({**body, "retry": 1})
        self.assertNotEqual(first["text"], second["text"])
        self.assertEqual(first["source"], "stub")
        self.assertEqual(first["model"], "")

    def test_grok_payload_is_text_only_and_never_sends_audio(self):
        captured = {}

        def fake_urlopen(request, timeout=12):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            class _Resp:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return json.dumps({
                        "choices": [{
                            "message": {
                                "content": json.dumps({
                                    "text": "You got it.",
                                    "speech_act": "confirm_order",
                                    "emotion": "neutral",
                                    "next_state": "closed",
                                    "player_turn": {
                                        "idiomaticity": 88,
                                        "progress": "done",
                                        "transaction_complete": True,
                                        "off_inventory": False,
                                    },
                                })
                            }
                        }]
                    }).encode("utf-8")
            return _Resp()

        with mock.patch.dict(server.os.environ, {"XAI_API_KEY": "xai-test-not-real"}, clear=False):
            with mock.patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger, please?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                })
        self.assertEqual(captured["url"], "https://api.x.ai/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "grok-4.3")
        self.assertEqual(captured["body"]["reasoning_effort"], "none")
        self.assertEqual(captured["body"]["max_tokens"], 80)
        self.assertEqual(captured["timeout"], server._GROK_TIMEOUT_SECONDS)
        payload = json.dumps(captured["body"])
        self.assertNotIn("wav", payload.lower())
        self.assertNotIn("audio", payload.lower())
        self.assertNotIn("base64", payload.lower())
        self.assertIn("burger", payload)
        self.assertTrue(reply["player_turn"]["transaction_complete"])
        self.assertEqual(reply["session"]["running_score"], 84.0)
        self.assertEqual(reply["source"], "grok")
        self.assertEqual(reply["model"], "grok-4.3")

    def test_gemini_payload_is_text_only_and_pins_low_thinking(self):
        captured = {}
        lines = gemini_json_lines({
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "text": "Sure thing, one burger to go.",
                            "speech_act": "close_transaction",
                            "emotion": "neutral",
                            "next_state": "closed",
                            "player_turn": {
                                "idiomaticity": 94,
                                "progress": "done",
                                "transaction_complete": True,
                                "off_inventory": False,
                            },
                        })
                    }]
                }
            }]
        })

        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines, captured)):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger to go?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                })
        self.assertIn("gemini-3.7-flash:streamGenerateContent", captured["url"])
        self.assertEqual(captured["timeout"], server._gemini_socket_timeout())
        # G3: the payload pins a low-or-lower thinking level. gemini-3.7-flash
        # rejects "minimal"/"none" (400) and ignores thinkingBudget=0, so LOW is
        # the accepted floor; the env override stays available for future models.
        thinking_level = captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"]
        self.assertEqual(thinking_level, server._gemini_thinking_level())
        self.assertIn(thinking_level, {"none", "minimal", "LOW"})
        self.assertEqual(server._gemini_thinking_level(), "LOW")
        self.assertNotIn("responseMimeType", captured["body"]["generationConfig"])
        payload = json.dumps(captured["body"])
        self.assertNotIn("wav", payload.lower())
        self.assertNotIn("audio", payload.lower())
        self.assertNotIn("base64", payload.lower())
        self.assertIn("burger", payload)
        self.assertTrue(reply["player_turn"]["transaction_complete"])
        self.assertEqual(reply["source"], "gemini")
        self.assertEqual(reply["model"], "gemini-3.7-flash")
        self.assertEqual(reply["session"]["running_score"], 87.0)

    def test_gemini_thinking_level_follows_env_override(self):
        captured = {}
        lines = gemini_json_lines({
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "text": "You got it.",
                "speech_act": "confirm_order",
                "emotion": "neutral",
                "next_state": "closed",
                "player_turn": {"idiomaticity": 80, "progress": "done", "transaction_complete": True, "off_inventory": False},
            })}]}}]
        })
        with mock.patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "GEMINI_THINKING_LEVEL": "minimal"},
            clear=False,
        ):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines, captured)):
                server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger, please?",
                    "history": [],
                })
        self.assertEqual(
            captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"],
            "minimal",
        )

    def test_gemini_timeout_falls_back_to_stub_instead_of_failing(self):
        @contextlib.contextmanager
        def fail_stream():
            raise urllib.error.URLError("timed out")
            yield  # pragma: no cover

        captured_log = io.StringIO()
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=lambda *a, **k: fail_stream()):
                with redirect_stdout(captured_log):
                    reply = server.generate_dialogue_reply({
                        "npc_id": "tavi",
                        "scenario_id": "food_counter",
                        "transcript": "Can I get a burger, please?",
                        "history": [],
                        "game_context": {"pronunciation": 80},
                    })
        log = captured_log.getvalue()
        self.assertEqual(reply["source"], "stub")
        self.assertEqual(reply["model"], "")
        self.assertTrue(reply["player_turn"]["transaction_complete"])
        self.assertTrue(reply["text"])
        self.assertIn("stage=gemini", log)
        self.assertIn("reason=timeout", log)
        self.assertIn("stage=dialogue", log)
        self.assertIn("source=stub", log)

    def test_gemini_is_preferred_over_grok_when_both_keys_exist(self):
        captured = {}
        lines = gemini_json_lines({
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "text": "You got it.",
                "speech_act": "confirm_order",
                "emotion": "neutral",
                "next_state": "closed",
                "player_turn": {"idiomaticity": 80, "progress": "done", "transaction_complete": True, "off_inventory": False},
            })}]}}]
        })

        with mock.patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "XAI_API_KEY": "xai-test-not-real"},
            clear=False,
        ):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines, captured)):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger, please?",
                    "history": [],
                })
        self.assertIn("generativelanguage.googleapis.com", captured["url"])
        self.assertEqual(reply["source"], "gemini")

    def test_grok_timeout_falls_back_to_stub_instead_of_failing(self):
        def fail_urlopen(_request, timeout=12):
            raise urllib.error.URLError("timed out")

        with mock.patch.dict(server.os.environ, {"XAI_API_KEY": "xai-test-not-real"}, clear=False):
            with mock.patch.object(server.urllib.request, "urlopen", side_effect=fail_urlopen):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger, please?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                })
        self.assertEqual(reply["source"], "stub")
        self.assertEqual(reply["model"], "")
        self.assertTrue(reply["player_turn"]["transaction_complete"])
        self.assertTrue(reply["text"])

    def test_godot_runtime_assets_contain_no_xai_secret(self):
        game_root = Path(__file__).resolve().parents[1]
        runtime_files = list((game_root / "scripts").glob("*.gd")) + list((game_root / "data" / "dialogue").rglob("*.json"))
        combined = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
        self.assertNotIn("XAI_API_KEY", combined)
        self.assertNotIn("GEMINI_API_KEY", combined)
        self.assertNotIn("GOOGLE_API_KEY", combined)
        self.assertNotIn("OPENAI_API_KEY", combined)
        self.assertNotRegex(combined, r"xai-[A-Za-z0-9_-]{16,}")
        self.assertNotRegex(combined, r"sk-[A-Za-z0-9_-]{16,}")
        self.assertNotRegex(combined, r"AIza[A-Za-z0-9_-]{16,}")

    def test_gemini_plain_first_line_then_json_is_parsed(self):
        spoken = "Sure thing, one burger to go.\n\n" + json.dumps({
            "speech_act": "close_transaction",
            "emotion": "neutral",
            "next_state": "closed",
            "player_turn": {
                "idiomaticity": 90,
                "progress": "done",
                "transaction_complete": True,
                "off_inventory": False,
            },
        })
        lines = [f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': spoken}]}}]})}\n".encode("utf-8")]

        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines)):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger to go?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                })
        self.assertEqual(reply["text"], "Sure thing, one burger to go.")
        self.assertEqual(reply["source"], "gemini")
        self.assertTrue(reply["player_turn"]["transaction_complete"])

    def test_backchannel_first_turn_does_not_complete(self):
        reply = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "yeah",
            "history": [],
        })
        self.assertFalse(reply["player_turn"]["transaction_complete"])
        self.assertNotEqual(reply["next_state"], "closed")

    def test_speak_deadline_stubs_text_but_keeps_late_player_turn(self):
        parsed_json = json.dumps({
            "text": "Sure thing, one burger to go.",
            "speech_act": "close_transaction",
            "emotion": "neutral",
            "next_state": "closed",
            "player_turn": {
                "idiomaticity": 91,
                "progress": "done",
                "transaction_complete": True,
                "off_inventory": False,
            },
        })
        lines = gemini_json_lines({"candidates": [{"content": {"parts": [{"text": parsed_json}]}}]})

        env_patch = mock.patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "GEMINI_SPEAK_SECONDS": "0.05"},
            clear=False,
        )
        with env_patch:
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines, delay=0.12)):
                events = list(server.iter_dialogue_events({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Can I get a burger, please?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                }))
        kinds = [item["event"] for item in events]
        self.assertEqual(kinds[:1], ["speaking"])
        self.assertIn("score", kinds)
        self.assertIn("done", kinds)
        speaking = events[0]["data"]
        score = next(item["data"] for item in events if item["event"] == "score")
        self.assertEqual(speaking["source"], "stub")
        self.assertEqual(speaking["text"], "You got it.")
        self.assertTrue(score["player_turn"]["transaction_complete"])
        self.assertGreaterEqual(score["player_turn"]["idiomaticity"], 90)

    def test_gemini_stream_can_speak_before_full_json(self):
        spoken = "One coffee to go.\n\n" + json.dumps({
            "speech_act": "close_transaction",
            "emotion": "neutral",
            "next_state": "closed",
            "player_turn": {
                "idiomaticity": 88,
                "progress": "done",
                "transaction_complete": True,
                "off_inventory": False,
            },
        })
        first_event = f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': 'One coffee to go.'}]}}]})}\n".encode()
        rest_event = f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': spoken}]}}]})}\n".encode()

        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory([first_event, rest_event])):
                events = list(server.iter_dialogue_events({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Could I have a coffee to go?",
                    "history": [],
                    "game_context": {"pronunciation": 80},
                }))
        speaking = events[0]["data"]
        self.assertEqual(speaking["source"], "gemini")
        self.assertIn("coffee", speaking["text"].lower())
        self.assertNotEqual(speaking["text"], "You got it.")

    def test_iter_events_speak_before_score(self):
        events = list(server.iter_dialogue_events({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get a burger, please?",
            "history": [],
            "game_context": {"pronunciation": 80},
        }))
        self.assertEqual([item["event"] for item in events], ["speaking", "score", "done"])
        self.assertTrue(events[0]["data"]["reply_id"].startswith("reply-"))
        self.assertTrue(events[1]["data"]["player_turn"]["transaction_complete"])

    def test_adaptive_window_tracks_p90_and_clamps(self):
        for _ in range(server._GEMINI_LATENCY_SAMPLES):
            server._record_gemini_first(3000)
        self.assertAlmostEqual(server._gemini_speak_window(), server._GEMINI_SPEAK_WINDOW_MAX, places=6)
        self.assertAlmostEqual(server._gemini_socket_timeout(), 5.0, places=6)
        server._GEMINI_LATENCY["first_ms"].clear()
        server._GEMINI_LATENCY["misses"] = 0
        for _ in range(server._GEMINI_LATENCY_SAMPLES):
            server._record_gemini_first(100)
        self.assertAlmostEqual(server._gemini_speak_window(), server._GEMINI_SPEAK_WINDOW_MIN, places=6)
        self.assertAlmostEqual(server._gemini_socket_timeout(), server._GEMINI_TIMEOUT_FLOOR, places=6)

    def test_consecutive_misses_reset_adaptive_samples(self):
        for _ in range(server._GEMINI_LATENCY_SAMPLES):
            server._record_gemini_first(3000)
        for _ in range(server._GEMINI_CONSECUTIVE_MISS_RESET):
            server._record_gemini_miss()
        self.assertAlmostEqual(server._gemini_speak_window(), server._GEMINI_SPEAK_SECONDS, places=6)
        self.assertAlmostEqual(server._gemini_socket_timeout(), server._GEMINI_TIMEOUT_SECONDS, places=6)

    def test_env_pins_speak_window_and_timeout(self):
        env_patch = mock.patch.dict(
            server.os.environ,
            {"GEMINI_SPEAK_SECONDS": "2.5", "GEMINI_TIMEOUT_SECONDS": "4.5"},
            clear=False,
        )
        with env_patch:
            for _ in range(server._GEMINI_LATENCY_SAMPLES):
                server._record_gemini_first(3000)
            self.assertAlmostEqual(server._gemini_speak_window(), 2.5, places=6)
            self.assertAlmostEqual(server._gemini_socket_timeout(), 4.5, places=6)

    def _tts_enabled_context(self):
        return mock.patch.object(server, "QWEN_TTS_API_KEY", "tts-test-key")

    def test_sse_streams_audio_between_speaking_and_score(self):
        pcm = bytes(range(256)) * 64  # 16 KiB of bare samples
        fake_wav = (
            b"RIFF" + (0).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
            + b"\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x77\x01\x00\x02\x00\x10\x00"
            + b"data" + (0x7FFFFF00).to_bytes(4, "little") + pcm
        )
        reply_id = server._register_spoken_reply("tavi", "You got it.", False, prefetch=False)

        def fake_stream(npc_id, rid):
            # Contract of the real generator: header-stripped bare PCM chunks.
            yield pcm[:8192]
            yield pcm[8192:]

        with self._tts_enabled_context():
            with mock.patch.object(server, "_TTS_PREFETCH_ENABLED", True):
                with mock.patch.object(server, "_stream_dynamic_reply_audio", side_effect=fake_stream):
                    events = list(server.iter_dialogue_events({
                        "npc_id": "tavi",
                        "scenario_id": "food_counter",
                        "transcript": "Can I get a burger, please?",
                        "history": [],
                        "game_context": {"pronunciation": 80},
                    }))
        kinds = [item["event"] for item in events]
        self.assertEqual(kinds[0], "speaking")
        self.assertEqual(kinds[1], "audio_begin")
        audio_count = kinds.count("audio")
        self.assertEqual(audio_count, 2)
        self.assertEqual(kinds[1 + 1 + audio_count], "audio_end")
        self.assertEqual(kinds[-2], "score")
        self.assertEqual(kinds[-1], "done")
        import base64 as b64
        chunks = [item["data"] for item in events if item["event"] == "audio"]
        reassembled = b"".join(b64.b64decode(item["pcm_b64"]) for item in chunks)
        self.assertEqual(reassembled, pcm)
        end = next(item["data"] for item in events if item["event"] == "audio_end")
        self.assertEqual(end["bytes"], len(pcm))
        begin = next(item["data"] for item in events if item["event"] == "audio_begin")
        self.assertEqual(begin["sample_rate"], 24000)

    def test_sse_audio_failure_emits_audio_failed_and_keeps_score(self):
        def fake_stream(npc_id, rid):
            yield b"\x01" * 128
            raise RuntimeError("stream broke")

        with self._tts_enabled_context():
            with mock.patch.object(server, "_TTS_PREFETCH_ENABLED", True):
                with mock.patch.object(server, "_stream_dynamic_reply_audio", side_effect=fake_stream):
                    events = list(server.iter_dialogue_events({
                        "npc_id": "tavi",
                        "scenario_id": "food_counter",
                        "transcript": "Can I get a burger, please?",
                        "history": [],
                        "game_context": {"pronunciation": 80},
                    }))
        kinds = [item["event"] for item in events]
        self.assertEqual(kinds[0], "speaking")
        self.assertIn("audio_begin", kinds)
        self.assertIn("audio_failed", kinds)
        self.assertNotIn("audio_end", kinds)
        self.assertIn("score", kinds)
        self.assertEqual(kinds[-1], "done")
        failed = next(item["data"] for item in events if item["event"] == "audio_failed")
        self.assertEqual(failed["reason"], "VOICE_REASON_SERVICE_UNAVAILABLE")


class DialogueHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.env_patch = mock.patch.dict(
            server.os.environ,
            {"XAI_API_KEY": "", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""},
            clear=False,
        )
        self.env_patch.start()
        server._DYNAMIC_REPLIES.clear()
        server._TTS_PREFETCH_ENABLED = False

    def tearDown(self):
        server._TTS_PREFETCH_ENABLED = True
        self.env_patch.stop()

    def _post(self, path, payload, raw=False):
        data = payload if raw else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_dialogue_http_returns_player_turn(self):
        status, payload = self._post("/game/dialogue", {
            "session_id": "test-session",
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get a burger, please?",
            "history": [],
            "game_context": {"scenario_state": "waiting_for_request", "pronunciation": 76},
        })
        self.assertEqual(status, 200)
        self.assertEqual(payload["npc_id"], "tavi")
        self.assertTrue(payload["player_turn"]["transaction_complete"])
        self.assertIn("idiomaticity", payload["player_turn"])
        self.assertNotIn("evidence_ids", payload)

    def test_dialogue_http_rejects_invalid_json_and_low_relevance(self):
        status, payload = self._post("/game/dialogue", b"{invalid", raw=True)
        self.assertEqual((status, payload["reason"]), (400, "VOICE_REASON_RESULT_INVALID"))
        status, payload = self._post("/game/dialogue", {
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Explain orbital mechanics.",
            "history": [],
        })
        self.assertEqual((status, payload["reason"]), (422, "VOICE_REASON_DIALOGUE_REJECTED"))

    def test_tts_http_rejects_forged_reply_id(self):
        status, payload = self._post("/game/tts", {"npc_id": "tavi", "reply_id": "reply-forged"})
        self.assertEqual((status, payload["reason"]), (404, "VOICE_REASON_RESULT_INVALID"))

    def test_prewarm_endpoint_is_always_ok(self):
        status, payload = self._post("/game/prewarm", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, payload = self._post("/game/prewarm", {"npc_id": "tavi"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_dialogue_sse_emits_speaking_then_score(self):
        payload = json.dumps({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get a burger, please?",
            "history": [],
            "game_context": {"pronunciation": 76},
        }).encode("utf-8")
        request = urllib.request.Request(
            self.url + "/game/dialogue",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertIn("text/event-stream", response.headers.get("Content-Type", ""))
            raw = response.read().decode("utf-8")
        self.assertIn("event: speaking", raw)
        self.assertIn("event: score", raw)
        self.assertIn("event: done", raw)
        self.assertLess(raw.find("event: speaking"), raw.find("event: score"))


if __name__ == "__main__":
    unittest.main()
