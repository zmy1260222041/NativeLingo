import unittest
import server
import town_context

class TownContextTest(unittest.TestCase):
    def test_familiarity_uses_only_own_completed_encounters(self):
        profile=server._DIALOGUE_PROFILES['mira']
        self.assertEqual(town_context.social_context({},profile)['stage'],'first_meeting')
        self.assertEqual(town_context.social_context({'game_context':{'town_contact':{'completed_exchanges':8,'days_met':1}}},profile)['stage'],'returning_face')
        self.assertEqual(town_context.social_context({'game_context':{'town_contact':{'completed_exchanges':4,'days_met':2}}},profile)['stage'],'familiar_face')
        self.assertEqual(town_context.social_context({'game_context':{'town_contact':{'completed_exchanges':'friend','days_met':True}}},profile)['stage'],'first_meeting')

    def test_help_is_known_only_to_rowan_and_campus_is_separate(self):
        body={'game_context':{'town_contact':{'helped_rowan':True}}}
        self.assertEqual(town_context.social_context(body,server._DIALOGUE_PROFILES['mira'])['confirmed_help'],[])
        self.assertEqual(len(town_context.social_context(body,server._DIALOGUE_PROFILES['rowan'])['confirmed_help']),1)
        body['game_context']['chapter']='campus'
        self.assertIsNone(town_context.social_context(body,server._DIALOGUE_PROFILES['tavi']))
        payload=server._dialogue_user_payload(body,server._DIALOGUE_SCENARIOS['food_counter'],server._DIALOGUE_PROFILES['tavi'])
        self.assertNotIn('town_role',payload['scene'])
        self.assertNotIn('town_orientation',payload)

    def test_distinct_roles_and_grounded_opening_seed(self):
        profiles=server._DIALOGUE_PROFILES
        self.assertEqual(len({profiles[n]['town_role']['first_contact'] for n in ['mira','tavi','ori','vesh','rowan']}),5)
        body={'transcript':'[NPC opens conversation]','history':[],'game_context':{'turn_kind':'opening','day':1,'town_contact':{'completed_exchanges':5,'days_met':2}}}
        payload=server._dialogue_user_payload(body,server._DIALOGUE_SCENARIOS['market_conversation'],profiles['mira'])
        self.assertIn('Familiar face',payload['topic_seed'])
        self.assertEqual(payload['CURRENT_PLAYER_TURN_TO_ANSWER'],'')

    def test_local_orientation_keeps_whole_service_reply(self):
        text="New here? Tell me what needs fixing and we can start there."
        scenario=server._DIALOGUE_SCENARIOS['parts_desk']
        state={'done':True,'parsed':{'text':text,'speech_act':'clarify_request'}}
        body={'transcript':"I'm new here.",'game_context':{'town_contact':{}}}
        self.assertEqual(server._live_safe_sentence(state,body,scenario),text)
        state['done']=False
        self.assertEqual(server._live_safe_sentence(state,body,scenario),'')

    def test_orientation_does_not_become_constant_errands_or_promises(self):
        body={'transcript':'What do you like about working here?'}
        profile=server._DIALOGUE_PROFILES['mira']
        self.assertFalse(town_context.referral_allowed(body))
        self.assertFalse(town_context.referral_allowed({'npc_id':'mira','transcript':'Hi Mira, how are you today?'}))
        self.assertTrue(town_context.reply_violations(body,profile,'You should go see Ori.'))
        self.assertEqual(town_context.reply_violations(body,profile,'I like seeing familiar faces. It makes a place feel less strange.'),[])
        body['transcript']='Who can help me settle in?'
        self.assertTrue(town_context.referral_allowed(body))
        self.assertTrue(town_context.reply_violations(body,profile,'Rowan always helps if you have a small task.'))
        self.assertEqual(town_context.reply_violations(body,profile,'Ori handles water and everyday supplies.'),[])
