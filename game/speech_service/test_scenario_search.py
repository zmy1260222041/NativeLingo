import tempfile
import unittest
from pathlib import Path

from game.speech_service import scenario_search


class ScenarioSearchTest(unittest.TestCase):
    def test_planned_queries_prefer_american_counter_talk(self):
        planned = scenario_search.planned_queries(4)
        by_scenario = {}
        for item in planned:
            by_scenario.setdefault(item["scenario_id"], []).append(item["query"])
        self.assertIn("food_ask_bread", by_scenario)
        food = " ".join(by_scenario["food_ask_bread"])
        water = " ".join(by_scenario["water_ask_clean_water"])
        self.assertIn("can I get", food)
        self.assertIn("NYC", food)
        self.assertIn("UK", food)
        self.assertIn("can I get a water", water)
        self.assertNotIn("refill my water bottle", water)
        self.assertNotIn("Mexico", water)
        self.assertNotIn("travel vlog", water)

    def test_filmot_queries_put_teaching_excludes_in_the_title_field(self):
        planned = scenario_search.planned_filmot_queries(2)
        by_scenario = {}
        for item in planned:
            by_scenario.setdefault(item["scenario_id"], []).append(item)
        water = by_scenario["water_ask_clean_water"][0]
        shelter = by_scenario["shelter_ask_sit_inside"][0]
        line = by_scenario["belonging_small_talk_waiting_line"][0]
        self.assertEqual(water["query"], '"can I get a water"')
        self.assertIn("title=", water["filmot_url"])
        self.assertIn("-learn", water["title_query"])
        self.assertIn("-dialogue", water["title_query"])
        self.assertIn("roblox", water["title_query"])
        self.assertIn("wait inside", shelter["query"])
        self.assertIn("lyrics", shelter["title_query"])
        self.assertIn("Black Friday", line["query"])
        self.assertIn("election", line["title_query"])
        self.assertNotIn("learn english", water["query"])

    def test_language_teaching_cards_are_filtered_from_filmot_hits(self):
        kept, rejected = scenario_search.filter_language_teaching([
            {
                "text": "160 English Dialogues for Travelling and Tourism Boston English Centre "
                        "dialogue 1 I'll have a bottle of the"
            },
            {
                "text": "1300 frases en inglés. Pronunciación lenta. Aprender Ingles pa... Best Teacher "
                        "tea please tea please tea please for here or to go for here or to go"
            },
            {
                "title": "Restaurant English: Where is your bathroom?",
                "channel": "Jon Peng English",
                "text": "the bathroom is just right over there",
            },
            {
                "title": "Trying Supposedly One of The Best Burgers In NYC",
                "channel": "Mo's Tasting",
                "text": "would you like that for here or to go? >> To go, to go, yeah",
            },
            {
                "title": "Shoppers wait in New England for Black Friday",
                "channel": "New England 10",
                "text": "how long have you been waiting",
            },
            {
                "text": "Yeni Başlayanlar İçin 4 Saat İngilizce Dinleme Egsersizi! İngilizce Kelime Öğrenme "
                        "Yes Coffee, pancakes, and eggs, please"
            },
        ])
        reasons = " ".join(item.get("language_teaching_reason", "") for item in rejected)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["channel"], "Mo's Tasting")
        self.assertEqual(kept[1]["channel"], "New England 10")
        self.assertTrue("dialogue 1" in reasons or "boston english" in reasons)
        self.assertIn("frases", reasons)

    def test_caption_dialogue_keeps_adjacent_american_exchange(self):
        turns = [
            {"speaker": "Customer", "start": 1.0, "end": 2.2, "text": "Can I get a loaf of bread?"},
            {"speaker": "Staff", "start": 2.3, "end": 3.8, "text": "Sure. For here or to go?"},
        ]
        result = scenario_search.score_caption_dialogue(turns, {
            "required_phrases_any": ["bread", "loaf"],
            "request_cues": ["can i get"],
            "response_cues": ["sure", "for here"],
        })
        self.assertTrue(result["dialogue_fit"])
        self.assertEqual(result["best_exchange"]["response_cue"], "sure")

    def test_caption_narration_is_not_an_exchange(self):
        turns = [
            {"speaker": "Host", "start": 1.0, "end": 4.0, "text": "Hotels usually have extra blankets for guests."},
            {"speaker": "Host", "start": 4.2, "end": 7.0, "text": "I always pack my own just in case."},
        ]
        result = scenario_search.score_caption_dialogue(turns, {
            "required_phrases_any": ["blanket"],
            "request_cues": ["can i get"],
            "response_cues": ["sure", "of course"],
        })
        self.assertFalse(result["dialogue_fit"])

    def test_caption_file_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.vtt"
            path.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:02.200\n"
                "Customer: Can I get a loaf of bread?\n\n"
                "00:00:02.300 --> 00:00:03.800\n"
                "Staff: Sure. How many would you like?\n",
                encoding="utf-8",
            )
            result = scenario_search.score_caption_file(path, "food_ask_bread")
            self.assertTrue(result["dialogue_fit"])


if __name__ == "__main__":
    unittest.main()
