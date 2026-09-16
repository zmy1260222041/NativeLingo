import unittest
from unittest.mock import patch
import server
import campus
from test_campus import request

class SocialDepthTest(unittest.TestCase):
    def test_full_reply_reaches_subtitles_and_tts(self):
        text = "I enjoy the quieter moments here. They give me time to notice what makes each person different. What helps you feel at home in a new place?"
        reply = dict(text=text, speech_act='answer_service_question', next_state='awaiting_follow_up', player_turn=dict(idiomaticity=90, transaction_complete=False), _model='test')
        with patch.object(server, '_gemini_api_key', return_value='fixture'), patch.object(server, '_gemini_dialogue', return_value=reply), patch.object(server, '_TTS_PREFETCH_ENABLED', False), patch.object(server, '_race_gemini_first', side_effect=AssertionError('social reply truncated')):
            events = list(server.iter_dialogue_events(dict(npc_id='mira', scenario_id='market_conversation', transcript='What do you like about this place?', history=[], require_live_dialogue=True)))
        spoken = next(e['data'] for e in events if e['event']=='speaking')
        self.assertEqual(spoken['text'], text)
        self.assertEqual(server._DYNAMIC_REPLIES[spoken['reply_id']]['text'],text)
        score = next(e['data'] for e in events if e['event']=='score')
        self.assertFalse(score['player_turn']['transaction_complete'])

    def test_opening_has_no_invented_player_turn_or_reward(self):
        payloads=[]
        def generate(prompt,payload):
            payloads.append(payload)
            return dict(text='I like having a rough outline before a project starts. It helps me see where I need another opinion.', meaningful=True, remember=True, remember_reply=True), 'gemini','fixture'
        events=list(campus.iter_events(request(turn_kind='opening'),server,generate))
        self.assertEqual(len(payloads),1)
        self.assertEqual(payloads[0]['CURRENT_PLAYER_TURN_TO_ANSWER'],'')
        self.assertFalse(any(t['speaker_id']=='player' for t in payloads[0]['history']))
        receipt=events[-1]['data']
        self.assertFalse(receipt['activity_candidate']['meaningful'])
        self.assertEqual(receipt['memory_candidates'],[])
        self.assertEqual(receipt['coaching'],[])

    def test_social_limits_do_not_weaken_shop_limits(self):
        text='I like quiet evenings. They make it easier to think. What helps you relax?'
        self.assertTrue(server._dialogue_gate(server._DIALOGUE_SCENARIOS['market_conversation'],text,'acknowledge_need')['accepted'])
        self.assertFalse(server._dialogue_gate(server._DIALOGUE_SCENARIOS['food_counter'],text,'acknowledge_need')['accepted'])

    def test_content_checks_reject_interview_loop_and_invented_scenery(self):
        body={'history':[{'role':'npc','text':'What helps you feel at home?'}]}
        self.assertTrue(server._social_content_violations(body,'What makes you comfortable?'))
        self.assertTrue(server._social_content_violations({},'The fountain is lovely this morning.'))
        self.assertEqual(server._social_content_violations(body,'I like having one familiar routine. It makes a new place less overwhelming.'),[])
