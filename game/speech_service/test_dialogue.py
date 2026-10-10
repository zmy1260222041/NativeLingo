import contextlib
import http.client
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
        provider = mock.patch.object(server, "TTS_PROVIDER", "qwen")
        provider.start()
        self.addCleanup(provider.stop)
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
        self.assertEqual({key for key, value in server._DIALOGUE_SCENARIOS.items() if not server._social_scenario(value)}, expected)
        self.assertEqual(server._DIALOGUE_SCENARIOS["food_counter"]["npc_id"], "tavi")
        self.assertEqual(server._DIALOGUE_SCENARIOS["convenience_store"]["npc_id"], "ori")
        self.assertEqual(server._DIALOGUE_SCENARIOS["parts_desk"]["npc_id"], "vesh")
        for key in expected:
            scenario = server._DIALOGUE_SCENARIOS[key]
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

    def test_inventory_matching_does_not_accept_substrings(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        self.assertFalse(server._transcript_hits_inventory(scenario, "Can I get seafood, please?"))
        reply = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Can I get seafood, please?",
            "history": [],
        })
        self.assertFalse(reply["player_turn"]["transaction_complete"])
        self.assertTrue(reply["player_turn"]["off_inventory"])

    def test_short_orders_and_spoken_promises_agree_in_the_stream(self):
        # Reproduce the live log: 'give me a sandwich okay' was incorrectly
        # offer_choice even though the model had already promised the sandwich.
        for transcript in ("Give me a sandwich okay", "Sandwich.", "A sandwich, please.", "I'd like a sandwich", "I need a sandwich"):
            with self.subTest(transcript=transcript):
                with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), mock.patch.object(server, "_race_gemini_first", return_value=("Sure thing, I'll get that sandwich for you.", None)):
                    events = list(server.iter_dialogue_events({"npc_id": "tavi", "scenario_id": "food_counter", "transcript": transcript, "history": [], "require_live_dialogue": True}))
                speaking = events[0]["data"]
                score = next(event["data"] for event in events if event["event"] == "score")
                self.assertEqual(speaking["speech_act"], "confirm_order")
                self.assertTrue(score["player_turn"]["transaction_complete"])
                self.assertEqual(score["player_turn"]["confirmed_item"], "sandwich")
                self.assertEqual(score["next_state"], "closed")

    def test_browsing_refusal_and_unresolved_choices_cannot_order(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        history = [{"role": "player", "text": "I want a burger"}, {"role": "npc", "text": "For here or to go?"}]
        for transcript in ("I don't want a burger", "No burger please", "Cancel my burger", "Do you have a burger?", "How much is a burger?", "Burger or sandwich?", "If I wanted a burger", "I ate a burger today", "no", "no thanks"):
            with self.subTest(transcript=transcript):
                self.assertFalse(server._is_order_request(scenario, transcript, history))
                turn = server._normalise_player_turn({"transaction_complete": True, "idiomaticity": 90}, transcript, scenario, history, "Sure thing, I'll get your burger.", "confirm_order")
                self.assertFalse(turn["transaction_complete"])
        self.assertTrue(server._is_order_request(scenario, "For here please", history))
        browsing = [{"role": "player", "text": "Do you have a burger?"}]
        self.assertFalse(server._is_order_request(scenario, "yes", browsing))

    def test_plural_and_quantity_orders_settle_on_the_named_item(self):
        # C2-04: inventory lists base forms; natural orders inflect them.
        cases = [
            ("food_counter", "Can I get two tacos, please?", "Sure thing, I'll get you two tacos.", "taco"),
            ("food_counter", "Two burgers to go, please.", "You got it. I'll get you two burgers.", "burger"),
            ("food_counter", "Could I have two sandwiches?", "Sure thing, two sandwiches coming right up.", "sandwich"),
            ("convenience_store", "Can I get two waters?", "Sure thing, I'll grab you two waters.", "water"),
            ("parts_desk", "I need two blankets.", "Sure thing, I'll get you two blankets.", "blanket"),
            ("convenience_store", "Can I get a battery?", "Sure thing, I'll grab you a battery.", "batteries"),
        ]
        for scenario_id, transcript, spoken, item in cases:
            with self.subTest(transcript=transcript):
                scenario = server._DIALOGUE_SCENARIOS[scenario_id]
                self.assertTrue(server._is_order_request(scenario, transcript, []))
                turn = server._normalise_player_turn(
                    {"transaction_complete": True, "idiomaticity": 80}, transcript, scenario, [], spoken, "confirm_order"
                )
                self.assertEqual((turn["requested_item"], turn["confirmed_item"]), (item, item))
                self.assertFalse(turn["off_inventory"])
                self.assertTrue(turn["transaction_complete"])
        food = server._DIALOGUE_SCENARIOS["food_counter"]
        self.assertTrue(server._is_order_request(food, "Three tacos to go.", []))
        stub = server._stub_dialogue({"transcript": "Can I get two tacos, please?", "history": []}, food)
        self.assertTrue(stub["player_turn"]["transaction_complete"])
        self.assertIn("taco", stub["text"])
        # Inflection never loosens the word boundary.
        for transcript in ("Can I get a tacoshell?", "I'd like something watery.", "Can I get burgerish food?"):
            with self.subTest(transcript=transcript):
                self.assertEqual(server._requested_inventory_term(food, transcript, []), "")

    def test_natural_requests_distinguish_named_off_inventory_from_missing_reference(self):
        scenario = server._DIALOGUE_SCENARIOS["convenience_store"]
        for transcript in ("Do you sell phone chargers?", "I'm looking for a flashlight."):
            turn = server._normalise_player_turn(
                {"idiomaticity": 80, "transaction_complete": False, "off_inventory": False},
                transcript,
                scenario,
                [],
            )
            self.assertTrue(turn["off_inventory"], transcript)
        unresolved = server._normalise_player_turn(
            {"idiomaticity": 80, "transaction_complete": False, "off_inventory": False},
            "Could I get one, please?",
            scenario,
            [],
        )
        self.assertFalse(unresolved["off_inventory"])

    def test_borrow_request_completes_but_location_question_does_not(self):
        parts = server._DIALOGUE_SCENARIOS["parts_desk"]
        blanket = server._stub_dialogue({
            "transcript": "Any chance I could borrow an extra blanket?",
            "history": [],
        }, parts)
        self.assertTrue(blanket["player_turn"]["transaction_complete"])
        store = server._DIALOGUE_SCENARIOS["convenience_store"]
        location = server._stub_dialogue({
            "transcript": "Hey, where can I find the batteries?",
            "history": [],
        }, store)
        self.assertFalse(location["player_turn"]["transaction_complete"])
        self.assertEqual(location["speech_act"], "answer_service_question")
        body = {"transcript": "Hey, where can I find the batteries?"}
        self.assertFalse(server._model_text_fits_request(body, store, "Sure thing."))
        self.assertTrue(server._model_text_fits_request(body, store, "I can point those out for you."))

    def test_generic_category_requires_a_specific_item_before_completion(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        stub = server._stub_dialogue({
            "transcript": "Can I have some food, please?",
            "history": [],
        }, scenario)
        self.assertFalse(stub["player_turn"]["transaction_complete"])
        self.assertEqual(stub["speech_act"], "clarify_request")
        self.assertIn("specifically", stub["text"].lower())

    def test_completion_requires_spoken_item_and_handoff_commitment(self):
        scenario = server._DIALOGUE_SCENARIOS["convenience_store"]
        raw = {
            "idiomaticity": 90,
            "progress": "done",
            "transaction_complete": True,
            "off_inventory": False,
        }
        generic = server._normalise_player_turn(
            raw, "Can I get a bottle of water?", scenario, [], "Sure thing.", "confirm_order"
        )
        pronoun_only = server._normalise_player_turn(
            raw, "Can I get some chips?", scenario, [], "Sure, I've got those.", "confirm_order"
        )
        substring_only = server._normalise_player_turn(
            raw, "Can I get some chips?", scenario, [], "I forgot it, chips.", "confirm_order"
        )
        explicit = server._normalise_player_turn(
            raw,
            "Can I get a bottle of water?",
            scenario,
            [],
            "You got it. I'll get you the water now.",
            "confirm_order",
        )
        self.assertFalse(generic["transaction_complete"])
        self.assertEqual(generic["transaction_evidence_reason"], "spoken_item_missing_or_different")
        self.assertFalse(pronoun_only["transaction_complete"])
        self.assertFalse(substring_only["transaction_complete"])
        self.assertTrue(explicit["transaction_complete"])
        self.assertTrue(explicit["spoken_delivery_confirmed"])
        self.assertEqual(explicit["requested_item"], "bottle of water")
        self.assertEqual(explicit["confirmed_item"], "water")

    def test_question_cannot_complete_even_when_it_mentions_the_item(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        turn = server._normalise_player_turn(
            {"idiomaticity": 90, "transaction_complete": True, "off_inventory": False},
            "Can I get a burger?",
            scenario,
            [],
            "Sure thing, do you want the burger for here or to go?",
            "confirm_order",
        )
        self.assertFalse(turn["transaction_complete"])
        self.assertEqual(turn["transaction_evidence_reason"], "spoken_reply_is_question")

    def test_model_complete_flag_is_downgraded_when_spoken_line_is_generic(self):
        lines = gemini_json_lines({
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "text": "Sure thing.",
                "speech_act": "confirm_order",
                "emotion": "neutral",
                "next_state": "closed",
                "player_turn": {
                    "idiomaticity": 90,
                    "progress": "done",
                    "transaction_complete": True,
                    "off_inventory": False,
                },
            })}]}}],
        })
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines)):
                reply = server.generate_dialogue_reply({
                    "npc_id": "ori",
                    "scenario_id": "convenience_store",
                    "transcript": "Can I get a bottle of water?",
                    "history": [],
                })
        self.assertEqual(reply["text"], "Sure thing.")
        self.assertFalse(reply["player_turn"]["transaction_complete"])
        self.assertFalse(reply["player_turn"]["spoken_delivery_confirmed"])
        self.assertEqual(reply["next_state"], "awaiting_follow_up")
        self.assertEqual(reply["speech_act"], "acknowledge_need")

    def test_stub_keeps_service_context_across_turns(self):
        first = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Burger.",
            "history": [],
        })
        self.assertEqual(first["text"], "You got it. I'll get you the burger now.")
        self.assertTrue(first["player_turn"]["transaction_complete"])
        second = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "To go, please.",
            "history": [
                {"role": "player", "text": "Burger."},
                {"role": "npc", "text": first["text"]},
            ],
        })
        self.assertTrue(second["player_turn"]["transaction_complete"])
        self.assertEqual(second["next_state"], "closed")

    def test_stub_sse_keeps_the_complete_service_question(self):
        events = list(server.iter_dialogue_events({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Do you have a burger?",
            "history": [],
        }))
        speaking = events[0]["data"]
        score = next(item["data"] for item in events if item["event"] == "score")
        self.assertEqual(speaking["text"], "Sure. For here or to go?")
        self.assertEqual(score["next_state"], "awaiting_follow_up")

    def test_idiomaticity_accepts_numeric_strings_and_null(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        string_turn = server._normalise_player_turn(
            {"idiomaticity": "0.91"}, "Burger.", scenario, []
        )
        null_turn = server._normalise_player_turn(
            {"idiomaticity": None}, "Burger.", scenario, []
        )
        self.assertEqual(string_turn["idiomaticity"], 91.0)
        # A model that did not score the utterance never becomes a 0 score.
        self.assertIsNone(null_turn["idiomaticity"])
        self.assertEqual(null_turn["idiomaticity_source"], "unavailable")
        missing = server._normalise_player_turn({}, "Burger.", scenario, [], source="gemini")
        self.assertIsNone(missing["idiomaticity"])
        self.assertEqual(missing["errors"], [])
        scored = server._normalise_player_turn({"idiomaticity": 88}, "Burger.", scenario, [], source="gemini")
        self.assertEqual((scored["idiomaticity"], scored["idiomaticity_source"]), (88.0, "gemini"))

    def test_parser_never_invents_a_default_score(self):
        parsed = server._parse_gemini_output("You got it. I'll get you the burger now.")
        self.assertEqual(parsed["text"], "You got it. I'll get you the burger now.")
        self.assertNotIn("player_turn", parsed)

    def _live_score_events(self, model_output, transcript="Can I get a burger, please?"):
        payload = {"candidates": [{"content": {"parts": [{"text": model_output}]}}]}
        lines = [("data: " + json.dumps(payload) + "\n").encode("utf-8")]
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines)):
                events = list(server.iter_dialogue_events({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": transcript,
                    "history": [],
                    "game_context": {"pronunciation": 60},
                    "require_live_dialogue": True,
                }))
        speaking = events[0]["data"]
        score = next(item["data"] for item in events if item["event"] == "score")
        return speaking, score

    def test_first_sentence_won_but_json_truncated_has_no_simulated_score(self):
        # C2-03: the live plane spoke, the work plane JSON was cut off. The
        # stub's constant 82 must not become a "gemini" idiomaticity.
        spoken = "You got it. I'll get you the burger now."
        truncated = spoken + "\n\n" + '{"speech_act": "confirm_order", "player_turn": {"idiomat'
        for output in [truncated, spoken]:
            with self.subTest(output=output[-20:]):
                speaking, score = self._live_score_events(output)
                self.assertEqual((speaking["source"], score["source"]), ("gemini", "gemini"))
                self.assertIsNone(score["player_turn"]["idiomaticity"])
                self.assertEqual(score["player_turn"]["idiomaticity_source"], "unavailable")
                self.assertIsNone(score["session"]["running_score"])
                # The spoken handoff itself is still auditable and settles.
                self.assertTrue(score["player_turn"]["transaction_complete"])

    def test_complete_work_plane_reports_gemini_idiomaticity(self):
        output = "You got it. I'll get you the burger now.\n\n" + json.dumps({
            "speech_act": "confirm_order", "emotion": "neutral", "next_state": "closed",
            "player_turn": {"idiomaticity": 74, "progress": "done", "transaction_complete": True, "off_inventory": False},
        })
        _speaking, score = self._live_score_events(output)
        self.assertEqual(score["player_turn"]["idiomaticity"], 74.0)
        self.assertEqual(score["player_turn"]["idiomaticity_source"], "gemini")
        self.assertEqual(score["session"]["running_score"], 67.0)

    def test_json_path_text_only_reply_has_no_simulated_score(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Sure thing, one burger to go."}]}}]}
        lines = [("data: " + json.dumps(payload) + "\n").encode("utf-8")]
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines)):
                reply = server.generate_dialogue_reply({
                    "npc_id": "tavi", "scenario_id": "food_counter", "transcript": "Can I get a burger to go?",
                    "history": [], "game_context": {"pronunciation": 60},
                })
        self.assertEqual(reply["source"], "gemini")
        self.assertIsNone(reply["player_turn"]["idiomaticity"])
        self.assertEqual(reply["player_turn"]["idiomaticity_source"], "unavailable")
        self.assertIsNone(reply["session"]["running_score"])
        stub = server.generate_dialogue_reply({
            "npc_id": "tavi", "scenario_id": "food_counter", "transcript": "Can I get a burger to go?", "history": [],
        })
        self.assertEqual((stub["source"], stub["player_turn"]["idiomaticity_source"]), ("stub", "stub"))

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
            "Sure thing. I'll get you the coffee now.",
            "confirm_order",
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
        gate = server._dialogue_gate(scenario, "Sure thing, that'll be two bucks.", "confirm_order")
        self.assertFalse(gate["accepted"])
        self.assertIn("invented_price", gate["violations"])
        self.assertEqual(server._sanitize_model_text(scenario, "Sure thing, that'll be two bucks."), "Sure thing.")
        gate = server._dialogue_gate(scenario, "They're right behind me on the shelf.", "answer_service_question")
        self.assertIn("invented_item_location", gate["violations"])
        self.assertEqual(server._sanitize_model_text(scenario, "The batteries are on the shelf."), "")
        gate = server._dialogue_gate(scenario, "Yeah, I've got one right here.", "confirm_order")
        self.assertIn("invented_stock_quantity", gate["violations"])
        self.assertEqual(server._sanitize_model_text(scenario, "Yeah, I've got one right here."), "Yeah.")

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
                                    "text": "You got it. I'll get you the burger now.",
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

    def test_gemini_payload_is_text_only_and_pins_minimal_thinking(self):
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
        self.assertIn("gemini-3.1-flash-lite:streamGenerateContent", captured["url"])
        self.assertEqual(captured["timeout"], server._gemini_socket_timeout())
        # G3: the live plane uses Flash-Lite's lowest-latency thinking level;
        # the env override remains available for compatible future models.
        thinking_level = captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"]
        self.assertEqual(thinking_level, server._gemini_thinking_level())
        self.assertIn(thinking_level.upper(), {"NONE", "MINIMAL", "LOW"})
        self.assertEqual(server._gemini_thinking_level(), "MINIMAL")
        self.assertNotIn("responseMimeType", captured["body"]["generationConfig"])
        payload = json.dumps(captured["body"])
        self.assertNotIn("wav", payload.lower())
        self.assertNotIn("audio", payload.lower())
        self.assertNotIn("base64", payload.lower())
        self.assertIn("burger", payload)
        system_prompt = captured["body"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Never invent a price", system_prompt)
        self.assertIn("American contractions", system_prompt)
        self.assertTrue(reply["player_turn"]["transaction_complete"])
        self.assertEqual(reply["source"], "gemini")
        self.assertEqual(reply["model"], "gemini-3.1-flash-lite")
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
        self.assertEqual(speaking["text"], "You got it. I'll get you the burger now.")
        self.assertTrue(score["player_turn"]["transaction_complete"])
        self.assertGreaterEqual(score["player_turn"]["idiomaticity"], 90)

    def test_late_work_plane_cannot_reverse_the_spoken_commitment(self):
        parsed_json = json.dumps({
            "text": "Here you go.",
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
        with mock.patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "GEMINI_SPEAK_SECONDS": "0.05"},
            clear=False,
        ):
            with mock.patch.object(server, "_gemini_post_stream", new=gemini_stream_factory(lines, delay=0.12)):
                events = list(server.iter_dialogue_events({
                    "npc_id": "tavi",
                    "scenario_id": "food_counter",
                    "transcript": "Do you have a burger?",
                    "history": [],
                }))
        speaking = events[0]["data"]
        score = next(item["data"] for item in events if item["event"] == "score")
        self.assertEqual(speaking["source"], "stub")
        self.assertEqual(speaking["text"], "Sure. For here or to go?")
        self.assertFalse(score["player_turn"]["transaction_complete"])
        self.assertEqual(score["next_state"], "awaiting_follow_up")
        self.assertEqual(score["player_turn"]["idiomaticity"], 91.0)

    def test_gemini_tail_latency_hedge_uses_the_first_model_sentence(self):
        slow = {"partial": "", "parsed": None, "done": False, "thread": mock.Mock()}
        fast = {"partial": "Got it, one burger to go.", "parsed": None, "done": True, "thread": mock.Mock()}
        with mock.patch.object(server, "_gemini_live", side_effect=[slow, fast]) as launch:
            first, winner = server._race_gemini_first({}, {}, {}, 0.8)
        self.assertEqual(first, "Got it, one burger to go.")
        self.assertIs(winner, fast)
        self.assertEqual(launch.call_count, 2)

    def test_live_plane_uses_later_safe_model_sentence(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        state = {
            "partial": "They're right behind me. Do you want me to point them out for you?",
            "parsed": None,
            "done": False,
        }
        first = server._live_safe_sentence(
            state,
            {"transcript": "Where can I find the sandwiches?"},
            scenario,
        )
        self.assertEqual(first, "Do you want me to point them out for you?")

    def test_completion_live_plane_waits_for_named_second_sentence(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        body = {
            "transcript": "I'll take a taco to go, please.",
            "history": [],
        }
        first_only = {
            "partial": "Coming right up.",
            "parsed": None,
            "done": False,
        }
        complete = {
            "partial": "Coming right up. I'll get that taco for you.",
            "parsed": None,
            "done": False,
        }
        self.assertEqual(
            server._live_safe_sentence(first_only, body, scenario, True, "confirm_order"),
            "",
        )
        self.assertEqual(
            server._live_safe_sentence(complete, body, scenario, True, "confirm_order"),
            "Coming right up. I'll get that taco for you.",
        )

    def test_live_plane_does_not_speak_incomplete_partial(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        state = {"partial": "We don", "parsed": None, "done": False}
        self.assertEqual(
            server._live_safe_sentence(
                state,
                {"transcript": "Do you sell phone chargers?"},
                scenario,
            ),
            "",
        )

    def test_v_prewarm_uses_the_shared_session_without_model_tokens(self):
        response = mock.Mock(status_code=200, url="https://generativelanguage.googleapis.com/v1beta/models/test")
        session = mock.Mock()
        session.get.return_value = response
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_session", return_value=session):
                self.assertTrue(server._prewarm_gemini_session("test", 1.0))
        requested_url = session.get.call_args.args[0]
        self.assertIn("/v1beta/models/gemini-3.1-flash-lite", requested_url)
        self.assertNotIn("generateContent", requested_url)
        response.close.assert_called_once()

    def test_model_data_plane_prewarm_is_tiny_and_throttled(self):
        lines = gemini_json_lines({
            "candidates": [{"content": {"parts": [{"text": "Ready now."}]}}],
        })
        captured = {}
        server._GEMINI_DATA_PLANE_LAST = 0.0
        with mock.patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "AIza-test-not-real-key-value"},
            clear=False,
        ):
            with mock.patch.object(
                server,
                "_gemini_post_stream",
                new=gemini_stream_factory(lines, captured=captured),
            ) as post:
                self.assertTrue(server._prewarm_gemini_data_plane("test", 1.0))
                self.assertTrue(server._prewarm_gemini_data_plane("test", 1.0))
        self.assertEqual(captured["body"]["generationConfig"]["maxOutputTokens"], 16)
        self.assertEqual(captured["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "MINIMAL")
        server._GEMINI_DATA_PLANE_LAST = 0.0

    def test_gemini_stream_can_speak_before_full_json(self):
        spoken_line = "Sure thing, one coffee to go."
        spoken = spoken_line + "\n\n" + json.dumps({
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
        first_event = f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': spoken_line}]}}]})}\n".encode()
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


    def test_player_level_travels_to_scene_card_and_prompt(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        profile = server._DIALOGUE_PROFILES["tavi"]
        card = server._scene_card(scenario, profile, "toddler")
        self.assertEqual(card.get("player_level"), "toddler")
        self.assertIn("beginner English learner", server._dialogue_system_prompt("toddler"))
        # G-A2: professional and missing tiers stay byte-identical to the base.
        base = server._dialogue_system_prompt()
        self.assertEqual(server._dialogue_system_prompt("professional"), base)
        self.assertEqual(server._dialogue_system_prompt("nonsense"), base)
        self.assertNotIn("player_level", server._scene_card(scenario, profile))
        self.assertNotIn("player_level", server._scene_card(scenario, profile, "professional"))

    def test_player_level_is_read_from_game_context_only(self):
        self.assertEqual(
            server._player_level_from_body({"game_context": {"player_level": "Toddler"}}),
            "toddler",
        )
        self.assertEqual(server._player_level_from_body({"game_context": {"player_level": "alien"}}), "")
        self.assertEqual(server._player_level_from_body({}), "")

    def test_error_spans_must_be_exact_substrings_of_the_transcript(self):
        spans = server._validated_error_spans(
            ["burger", "a burger please now okay", "espresso", "burger", 7],
            "I want burger, please.",
            62.0,
        )
        self.assertEqual(spans, ["burger"])
        five_words = server._validated_error_spans(
            ["one two three four five"], "one two three four five", 40.0
        )
        self.assertEqual(five_words, [])
        rewritten = server._validated_error_spans(["can i get a burger"], "i want burger", 55.0)
        self.assertEqual(rewritten, [])

    def test_error_spans_capped_and_gated_by_idiomaticity(self):
        raw = ["want", "please", "more"]
        self.assertEqual(
            server._validated_error_spans(raw, "I want more, please?", 84.0),
            ["want", "please"],
        )
        self.assertEqual(server._validated_error_spans(raw, "I want more, please?", 85.0), [])
        self.assertEqual(server._validated_error_spans(None, "I want burger", 10.0), [])

    def test_normalised_player_turn_carries_validated_errors(self):
        scenario = server._DIALOGUE_SCENARIOS["food_counter"]
        turn = server._normalise_player_turn(
            {"idiomaticity": 62, "errors": ["burger", "not in transcript"]},
            "I want burger, please.",
            scenario,
        )
        self.assertEqual(turn["errors"], ["burger"])
        clean = server._normalise_player_turn(
            {"idiomaticity": 92, "errors": ["burger"]},
            "Can I get a burger?",
            scenario,
        )
        self.assertEqual(clean["errors"], [])

    def test_stub_player_turn_carries_no_error_marks(self):
        reply = server.generate_dialogue_reply({
            "npc_id": "tavi",
            "scenario_id": "food_counter",
            "transcript": "Burger.",
            "history": [],
            "game_context": {"player_level": "toddler"},
        })
        self.assertEqual(reply["player_turn"]["errors"], [])


class GeminiRouteTest(unittest.TestCase):
    """GEMINI_PROXY switch: direct first, env proxy only as a fallback."""

    def setUp(self):
        readiness = mock.patch.dict(server._GEMINI_READINESS, {"ready": False, "reason": "not_checked"})
        readiness.start()
        self.addCleanup(readiness.stop)
        server._GEMINI_ROUTE["mode"] = ""
        server._GEMINI_SESSIONS.clear()

    def _sessions(self, direct_get, proxy_get):
        direct = mock.Mock(name="direct-session")
        proxy = mock.Mock(name="proxy-session")
        if isinstance(direct_get, BaseException):
            direct.get.side_effect = direct_get
        else:
            direct.get.return_value = direct_get
        if isinstance(proxy_get, BaseException):
            proxy.get.side_effect = proxy_get
        else:
            proxy.get.return_value = proxy_get
        table = {"direct": direct, "proxy": proxy}
        return direct, proxy, mock.Mock(side_effect=lambda route="": table.get(route, proxy))

    @staticmethod
    def _ok():
        return mock.Mock(status_code=200, url="https://generativelanguage.googleapis.com/v1beta/models/x")

    @staticmethod
    def _region_blocked():
        response = mock.Mock(status_code=400, url="https://generativelanguage.googleapis.com/v1beta/models/x")
        response.text = "User location is not supported for the API use."
        return response

    def test_direct_session_ignores_env_proxy(self):
        if server.requests is None:  # pragma: no cover - deployment without requests
            self.skipTest("requests unavailable")
        session = server._gemini_session("direct")
        self.assertIsNotNone(session)
        self.assertFalse(session.trust_env)
        self.assertTrue(server._gemini_session("proxy").trust_env)

    def test_auto_prefers_direct_when_native_get_works(self):
        direct, proxy, session_factory = self._sessions(self._ok(), self._region_blocked())
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertTrue(server._prewarm_gemini_session("test", 1.0))
        direct.get.assert_called_once()
        proxy.get.assert_not_called()
        self.assertEqual(server._GEMINI_ROUTE["mode"], "direct")

    def test_auto_falls_back_to_proxy_when_direct_fails(self):
        direct, proxy, session_factory = self._sessions(OSError("connection refused"), self._ok())
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertTrue(server._prewarm_gemini_session("test", 1.0))
        direct.get.assert_called_once()
        proxy.get.assert_called_once()
        self.assertEqual(server._GEMINI_ROUTE["mode"], "proxy")
        self.assertEqual(server._GEMINI_READINESS["reason"], "generation_not_checked")

    def test_off_policy_never_uses_the_proxy_route(self):
        direct, proxy, session_factory = self._sessions(OSError("connection refused"), self._ok())
        env = {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "GEMINI_PROXY": "off"}
        with mock.patch.dict(server.os.environ, env, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertFalse(server._prewarm_gemini_session("test", 1.0))
        proxy.get.assert_not_called()
        self.assertEqual(server._GEMINI_ROUTE["mode"], "direct")

    def test_on_policy_pins_the_proxy_route(self):
        direct, proxy, session_factory = self._sessions(self._ok(), self._ok())
        env = {"GEMINI_API_KEY": "AIza-test-not-real-key-value", "GEMINI_PROXY": "on"}
        with mock.patch.dict(server.os.environ, env, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertTrue(server._prewarm_gemini_session("test", 1.0))
        direct.get.assert_not_called()
        proxy.get.assert_called_once()
        self.assertEqual(server._GEMINI_ROUTE["mode"], "proxy")

    def test_failed_cached_route_is_rediscovered(self):
        server._GEMINI_ROUTE["mode"] = "proxy"
        direct, proxy, session_factory = self._sessions(self._ok(), self._region_blocked())
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertTrue(server._prewarm_gemini_session("test", 1.0))
        self.assertEqual(server._GEMINI_ROUTE["mode"], "direct")

    def test_both_routes_down_reports_region_reason(self):
        direct, proxy, session_factory = self._sessions(self._region_blocked(), self._region_blocked())
        with mock.patch.dict(server.os.environ, {"GEMINI_API_KEY": "AIza-test-not-real-key-value"}, clear=False):
            with mock.patch.object(server, "_gemini_session", side_effect=session_factory):
                self.assertFalse(server._prewarm_gemini_session("test", 1.0))
        self.assertEqual(server._GEMINI_READINESS["reason"], "region_unsupported")


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

    def _raw(self, method, path, body=b"", headers=None):
        """Exact request control (bad lengths, foreign Host/Origin) via http.client."""
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=3)
        try:
            connection.putrequest(method, path, skip_host=bool(headers and "Host" in headers), skip_accept_encoding=True)
            sent = dict(headers or {})
            sent.setdefault("Content-Length", str(len(body)))
            for key, value in sent.items():
                connection.putheader(key, value)
            connection.endheaders(body or None)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else {}
        finally:
            connection.close()

    def test_live_dialogue_without_any_model_is_503_not_configured(self):
        # C2-10: no configured model is a service condition, not a refusal.
        for transcript in ("[NPC opens conversation]", "I just arrived and I feel lonely here."):
            for accept in ("application/json", "text/event-stream"):
                with self.subTest(transcript=transcript, accept=accept):
                    status, payload = self._raw("POST", "/game/dialogue", json.dumps({
                        "npc_id": "mira", "scenario_id": "market_conversation", "transcript": transcript,
                        "history": [], "game_context": {"turn_kind": "opening"}, "require_live_dialogue": True,
                    }).encode(), {"Content-Type": "application/json", "Accept": accept})
                    self.assertEqual(status, 503)
                    self.assertEqual((payload["reason"], payload["detail"]), ("VOICE_REASON_SERVICE_UNAVAILABLE", "not_configured"))

    def test_gate_rejected_live_reply_is_retryable_rejection_not_outage(self):
        # C2-10: the model answered, but the answer failed the content gate.
        late = {"parsed": {"text": "Sorry, we're out of tacos right now.", "speech_act": "clarify_request", "_provider": "gemini"},
                "partial": "Sorry, we're out of tacos right now.", "done": True, "thread": mock.Mock()}
        body = {"npc_id": "tavi", "scenario_id": "food_counter", "transcript": "Can I get a taco, please?",
                "history": [], "require_live_dialogue": True}
        with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), \
             mock.patch.object(server, "_race_gemini_first", return_value=("", late)):
            with self.assertRaisesRegex(ValueError, "quality gate"):
                next(server.iter_dialogue_events(body))
            status, payload = self._raw("POST", "/game/dialogue", json.dumps(body).encode(),
                                        {"Content-Type": "application/json", "Accept": "text/event-stream"})
        self.assertEqual(status, 422)
        self.assertEqual((payload["reason"], payload["detail"]), ("VOICE_REASON_DIALOGUE_REJECTED", "reply_rejected"))
        # A provider that never answered stays a 503 outage.
        with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), \
             mock.patch.object(server, "_race_gemini_first", return_value=("", {"parsed": None, "done": False})):
            status, payload = self._raw("POST", "/game/dialogue", json.dumps(body).encode(),
                                        {"Content-Type": "application/json", "Accept": "text/event-stream"})
        self.assertEqual((status, payload["detail"]), (503, "provider_failed"))

    def test_social_reply_rejected_three_times_is_a_rejection(self):
        candidate = {"text": "The fountain looks lovely this morning.", "speech_act": "answer_service_question",
                     "next_state": "awaiting_follow_up", "_provider": "gemini"}
        body = {"npc_id": "mira", "scenario_id": "market_conversation", "transcript": "What do you like here?",
                "history": [], "game_context": {"town_contact": {}}, "require_live_dialogue": True}
        with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), \
             mock.patch.object(server, "_gemini_dialogue", return_value=dict(candidate)) as model:
            with self.assertRaisesRegex(ValueError, "quality gate rejected live reply"):
                next(server.iter_dialogue_events(body))
        self.assertEqual(model.call_count, 3)

    def test_json_path_applies_the_same_social_and_town_checks(self):
        # C2-11: the reviewer's sample was accepted as source=gemini on the
        # JSON (web/headless) path while SSE rejected it four times over.
        bad = {"text": "The fountain looks lovely this morning. You should go see Vesh, he always helps newcomers. What do you think?",
               "speech_act": "answer_service_question", "next_state": "awaiting_follow_up", "_provider": "gemini", "_model": "fixture"}
        good = {"text": "I like seeing the same faces each day. It makes this place feel less strange.",
                "speech_act": "answer_service_question", "next_state": "awaiting_follow_up",
                "player_turn": {"idiomaticity": 80}, "_provider": "gemini", "_model": "fixture"}
        body = {"npc_id": "mira", "scenario_id": "market_conversation", "transcript": "What do you like here?",
                "history": [{"role": "npc", "text": "What brings you here?"}], "game_context": {"town_contact": {}},
                "require_live_dialogue": True}
        violations = server._dialogue_gate(server._DIALOGUE_SCENARIOS["market_conversation"], bad["text"], bad["speech_act"])["violations"]
        violations += server._social_content_violations(body, bad["text"])
        violations += server.town_context.reply_violations(body, server._DIALOGUE_PROFILES["mira"], bad["text"])
        self.assertGreaterEqual(len(violations), 3)
        with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), \
             mock.patch.object(server, "_gemini_dialogue", side_effect=[dict(bad), dict(bad), dict(bad)]):
            with self.assertRaisesRegex(ValueError, "rejected live reply"):
                server.generate_dialogue_reply(body)
        with mock.patch.object(server, "_gemini_api_key", return_value="fixture"), \
             mock.patch.object(server, "_gemini_dialogue", side_effect=[dict(bad), dict(good)]) as model:
            reply = server.generate_dialogue_reply(body)
        self.assertEqual((reply["text"], reply["source"]), (good["text"], "gemini"))
        self.assertEqual(model.call_count, 2)
        self.assertIn("Rewrite your rejected candidate", model.call_args.args[0]["_social_repair"])

    def test_requests_from_foreign_pages_are_refused(self):
        # C2-14: DNS rebinding (foreign Host), cross-site pages (foreign Origin)
        # and CORS-simple bodies cannot reach paid model or TTS calls.
        body = json.dumps({"npc_id": "tavi", "scenario_id": "food_counter", "transcript": "Can I get a burger, please?", "history": []}).encode()
        refused = [
            ({"Content-Type": "application/json", "Origin": "https://evil.example"}, 403),
            ({"Content-Type": "application/json", "Host": "rebind.evil.example:17831"}, 403),
            ({"Content-Type": "text/plain;charset=UTF-8"}, 415),
            ({}, 415),
            ({"Content-Type": "application/x-www-form-urlencoded"}, 415),
        ]
        for headers, expected in refused:
            with self.subTest(headers=headers):
                status, payload = self._raw("POST", "/game/dialogue", body, headers)
                self.assertEqual(status, expected)
                self.assertFalse(payload["ok"])
        status, _payload = self._raw("GET", "/health", headers={"Host": "rebind.evil.example:17831"})
        self.assertEqual(status, 403)
        status, _payload = self._raw("POST", "/game/prewarm", b"{}", {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        status, _payload = self._raw("POST", "/score_word", b"0" * 64, {"Content-Type": "text/plain", "X-Stranger-Lexical": "morning"})
        self.assertEqual(status, 415)
        # Godot (no Origin, Host 127.0.0.1:port) and local dev pages still work.
        for headers in ({"Content-Type": "application/json"},
                        {"Content-Type": "application/json; charset=utf-8", "Origin": "null"},
                        {"Content-Type": "application/json", "Origin": "http://localhost:8060"},
                        {"Content-Type": "application/json", "Host": "localhost:17831"}):
            with self.subTest(headers=headers):
                status, payload = self._raw("POST", "/game/dialogue", body, headers)
                self.assertEqual(status, 200)
                self.assertEqual(payload["npc_id"], "tavi")
        status, payload = self._raw("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIn("asr_ready", payload)

    def test_word_score_service_failure_is_503_over_http(self):
        with mock.patch.object(server, "word_pronunciation", return_value=None), \
             mock.patch.object(server, "_transcribe_with_hotwords", side_effect=OSError("no model")):
            status, payload = self._raw("POST", "/score_word", b"\0" * 128, {"Content-Type": "audio/wav", "X-Stranger-Lexical": "morning"})
        self.assertEqual((status, payload["reason"]), (503, "VOICE_REASON_SERVICE_UNAVAILABLE"))

    def test_malformed_requests_get_json_errors(self):
        # C2-15: bad framing or shapes answer 400 instead of dropping the socket.
        for path in ("/game/dialogue", "/game/tts", "/game/prewarm", "/game/campus/dialogue"):
            with self.subTest(path=path):
                status, payload = self._raw("POST", path, b"{}", {"Content-Type": "application/json", "Content-Length": "abc"})
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])
        status, payload = self._raw("POST", "/transcribe", b"\0" * 64, {"Content-Type": "audio/wav", "Content-Length": "abc"})
        self.assertEqual((status, payload["reason"]), (400, "VOICE_REASON_LENGTH"))
        for body in (b"[1,2]", b"{bad", json.dumps({"npc_id": "mira", "line_id": "word_practice_ask", "options": "food"}).encode()):
            with self.subTest(body=body):
                status, payload = self._raw("POST", "/game/tts", body, {"Content-Type": "application/json"})
                self.assertEqual((status, payload["reason"]), (400, "VOICE_REASON_RESULT_INVALID"))
        campus_body = {"scenario_id": "class_project_roles", "transcript": "Hi there.", "chain_context": ["x"]}
        status, payload = self._raw("POST", "/game/campus/dialogue", json.dumps(campus_body).encode(), {"Content-Type": "application/json"})
        self.assertEqual((status, payload["reason"]), (400, "invalid_campus_request"))

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
