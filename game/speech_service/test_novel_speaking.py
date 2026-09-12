"""FR-46 speech catalog/readiness contracts, with no paid model calls."""
import json
from pathlib import Path
import unittest
from unittest import mock
import server


class NovelSpeakingTests(unittest.TestCase):
    def test_place_openings_match_server_voice_catalog(self):
        import re
        source = (server.REPO_ROOT / 'game/scripts/novel/novel_content.gd').read_text()
        matches = re.findall(r'"npc": "([a-z]+)".*?"opening_id": "([a-z_]+)", "opening": "([^"]+)"', source)
        self.assertEqual(len(matches), 5)
        for npc, line, text in matches:
            self.assertEqual(server.NPC_LINES[npc][line], text)

    def test_every_visible_social_line_has_matching_server_audio(self):
        scenes = json.loads((server.DIALOGUE_ROOT / 'novel_daily_life.json').read_text())
        self.assertGreaterEqual(len(scenes), 8)
        ids = set()
        for scene in scenes:
            self.assertTrue(scene['hint'])
            self.assertTrue(scene['phrase'])
            self.assertGreaterEqual(len(scene['lines']), 4)
            self.assertEqual(len({line[0] for line in scene['lines']}), 2)
            for npc, line, text in scene['lines']:
                self.assertNotIn(line, ids)
                ids.add(line)
                self.assertEqual(server.NPC_LINES[npc][line], text)
                self.assertLessEqual(len(text.split()), 30)
            for word in scene['words']:
                self.assertIn(word, server.WORD_LINES)

    def test_life_situation_reaches_the_model(self):
        for scenario_id, scenario in server._DIALOGUE_SCENARIOS.items():
            card = server._scene_card(scenario, server._DIALOGUE_PROFILES[scenario['npc_id']])
            self.assertEqual(card['situation'], scenario['situation'])
        prompt = server._dialogue_system_prompt('toddler')
        self.assertIn('do not repeat answered questions', prompt)
        self.assertIn('not permission to hand over an item', prompt)

    def test_fulfillment_uses_player_answers_and_latest_correction(self):
        scenario = server._DIALOGUE_SCENARIOS['food_counter']
        profile = server._DIALOGUE_PROFILES['tavi']
        cases = [
            ([], 'A sandwich to go, please.', 'to_go'),
            ([{'role': 'npc', 'text': 'For here or to go?'}], 'A sandwich, please.', ''),
            ([{'role': 'player', 'text': 'A sandwich to go.'}], 'Actually, for here, please.', 'for_here'),
            ([], 'A sandwich, not to go.', ''),
            ([], 'A sandwich please, then I need to go home.', ''),
        ]
        for history, text, expected in cases:
            user = server._dialogue_user_payload({'transcript': text, 'history': history}, scenario, profile)
            self.assertEqual(user.get('service_context', {}).get('fulfillment_already_stated', ''), expected)
            self.assertEqual(user['transcript'], text)
            self.assertEqual(user['history'], history)

    def test_handoff_hint_does_not_turn_browsing_into_an_order(self):
        scenario = server._DIALOGUE_SCENARIOS['convenience_store']
        profile = server._DIALOGUE_PROFILES['ori']
        for text, expected in [("Do you carry batteries?", False), ("I'll take some batteries, please.", True), ("I don't want batteries.", False), ("Can I get directions?", False), ("Can I get batteries or water?", False), ("I want to see the batteries.", False)]:
            payload = server._dialogue_user_payload({'transcript': text}, scenario, profile)
            self.assertEqual('response_mode' in payload, expected)

    def test_entry_audio_matches_role_card(self):
        for npc, scenario in [('tavi', 'food_counter'), ('ori', 'convenience_store'), ('vesh', 'parts_desk')]:
            card = json.loads((server.REPO_ROOT / f'game/data/dialogue/scenarios/{scenario}.json').read_text())
            self.assertEqual(server.NPC_LINES[npc]['service_entry'], card['entry_dialogue'])

    def test_word_model_is_exact_and_whitelisted(self):
        with mock.patch.object(server, '_tts_configured', return_value=True), mock.patch.object(server, '_synthesize_speech', return_value=b'0' * 100) as tts, mock.patch.object(server, '_TTS_CACHE', {}):
            server.synthesize_npc_line('mira', 'word_practice_model', options=['please'])
            self.assertEqual(tts.call_args.args[0], 'please')
            for words in [[], ['arbitrary text'], ['water', 'food']]:
                with self.assertRaises(KeyError):
                    server.synthesize_npc_line('mira', 'word_practice_model', options=words)

    def test_live_required_never_registers_stub_reply(self):
        body = {"npc_id": "tavi", "scenario_id": "food_counter", "transcript": "a burger please", "session_id": "novel-test", "history": [], "game_context": {}, "require_live_dialogue": True}
        with mock.patch.object(server, '_gemini_api_key', return_value='fixture'), mock.patch.object(server, '_gemini_dialogue', return_value=None), mock.patch.object(server, '_race_gemini_first', return_value=('', None)), mock.patch.object(server, '_register_spoken_reply') as register:
            with self.assertRaises(RuntimeError):
                server.generate_dialogue_reply(body)
            with self.assertRaises(RuntimeError):
                next(server.iter_dialogue_events(body))
            register.assert_not_called()

    def test_connection_prewarm_preserves_verified_generation(self):
        with mock.patch.object(server, '_gemini_api_key', return_value='fixture'), mock.patch.object(server, '_gemini_session', return_value=mock.Mock()), mock.patch.object(server, '_gemini_route_probe', return_value=(True, '', 1)), mock.patch.dict(server._GEMINI_READINESS, {'ready': True, 'reason': ''}):
            self.assertTrue(server._prewarm_gemini_session('test', 1))
            self.assertTrue(server._GEMINI_READINESS['ready'])

    def test_region_rejection_exposes_only_safe_code(self):
        response = mock.Mock(status_code=400, text='User location is not supported for the API use.', url='https://example.invalid', headers={})
        session = mock.Mock()
        session.get.return_value = response
        with mock.patch.object(server, '_gemini_api_key', return_value='fixture'), mock.patch.object(server, '_gemini_session', return_value=session), mock.patch.dict(server._GEMINI_READINESS, {'ready': True, 'reason': ''}):
            self.assertFalse(server._prewarm_gemini_session('test', 1))
            self.assertEqual(server._GEMINI_READINESS, {'ready': False, 'reason': 'region_unsupported'})


if __name__ == '__main__':
    unittest.main()
