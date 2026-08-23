import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from game.speech_service import corpus_pipeline
from game.speech_service import native_speaker_screener as screener
from game.speech_service import youtube_discover


class NativeSpeakerScreenerTest(unittest.TestCase):
    def screen(self, **overrides):
        info = {
            "id": "abc123",
            "title": "Shoppers wait in line for Black Friday",
            "channel": "KSHB 41",
            "description": "A field interview with people waiting in line.",
            "tags": ["news"],
            "categories": ["News & Politics"],
            "language": "en",
            "channel_is_verified": True,
            "automatic_caption_langs": ["en", "en-orig"],
            "subtitle_langs": [],
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
        }
        info.update(overrides)
        return screener.screen_video(info)

    def test_inner_circle_news_is_a_candidate_but_not_auto_verified(self):
        result = self.screen()
        self.assertEqual(result["verdict"], "candidate")
        self.assertEqual(result["native_scope"], "channel_org")
        self.assertGreaterEqual(result["host_native_score"], 50)
        self.assertEqual(result["response_speaker_status"], "not_evidenced")
        self.assertFalse(result["can_auto_verify"])
        self.assertFalse(result["native_speaker_verified"])

    def test_chinese_original_audio_is_rejected(self):
        result = self.screen(
            title="FIRST TIME WORKING AT A BAKERY CAFE IN SYDNEY",
            channel="Jessica Lin",
            automatic_caption_langs=["zh-orig", "en"],
            categories=["People & Blogs"],
            channel_is_verified=False,
        )
        self.assertEqual(result["verdict"], "reject")
        self.assertTrue(any("non_english_original_audio" in reason for reason in result["reasons"]))

    def test_language_lesson_is_rejected(self):
        result = self.screen(
            title="English Conversation Practice at a Bakery A1-A2",
            channel="Learn English Daily",
            description="Repeat after the scripted dialogue.",
            categories=["Education"],
        )
        self.assertEqual(result["verdict"], "reject")
        self.assertTrue(any(reason.startswith("language_teaching_or_scripted") for reason in result["reasons"]))

    def test_expat_advice_video_is_rejected(self):
        result = self.screen(
            title="THE TRUTH ABOUT WATER in Mexico & what YOU need to know",
            channel="Expat Family FINTECH",
            description="How expats get safe drinking water.",
            categories=["Travel & Events"],
            channel_is_verified=False,
        )
        self.assertEqual(result["verdict"], "reject")

    def test_dual_original_language_is_rejected(self):
        result = self.screen(
            title="Drinking Water in Mexico - Is it Safe?",
            channel="International Living",
            automatic_caption_langs=["en-orig", "pt-orig"],
            categories=["Travel & Events"],
        )
        self.assertEqual(result["verdict"], "reject")
        self.assertTrue(any("pt-orig" in reason for reason in result["reasons"]))

    def test_travel_tip_title_is_rejected(self):
        result = self.screen(
            title="Budget Travel Tip: Traveling with Children in Hotels",
            channel="Wolters World",
            categories=["Travel & Events"],
        )
        self.assertEqual(result["verdict"], "reject")

    def test_biography_can_mark_host_as_candidate(self):
        result = self.screen(
            title="A Morning at Our Neighborhood Bakery",
            channel="Local Eats",
            description="I was born in Texas and film real bakery counters.",
            categories=["People & Blogs"],
            tags=["texas", "us vlog"],
            channel_is_verified=False,
        )
        self.assertEqual(result["verdict"], "candidate")
        self.assertEqual(result["native_scope"], "host_only")
        self.assertFalse(result["native_speaker_verified"])
        self.assertTrue(any("us_self_identification" in item for item in result["evidence"]))

    def test_uk_bakery_vlog_is_held_out_of_american_candidates(self):
        result = self.screen(
            title="Ordering ENTIRE MENU At UK's Most Expensive Bakery",
            channel="Hannah Ricketts",
            description="Food reviews on a London bakery visit.",
            categories=["People & Blogs"],
            tags=["london", "uk vlog", "learn english"],
            channel_is_verified=True,
        )
        self.assertEqual(result["verdict"], "pending")
        self.assertIn("non_american_english_variety", result["reasons"])
        self.assertFalse(result["native_speaker_verified"])

    def test_us_bakery_vlog_is_candidate_without_a_news_org(self):
        result = self.screen(
            title="Ordering the whole menu at a NYC bakery",
            channel="Local Eats",
            description="A morning at a New York bakery counter.",
            categories=["People & Blogs"],
            tags=["nyc", "bakery"],
            channel_is_verified=False,
        )
        self.assertEqual(result["verdict"], "candidate")
        self.assertEqual(result["native_scope"], "host_only")
        self.assertTrue(any("us_place" in item for item in result["evidence"]))

    def test_english_vlog_without_inner_circle_place_stays_pending(self):
        result = self.screen(
            title="Stuck in the Rain in Prague",
            channel="Marshall and Sabrina",
            description="We hid from the rain and walked around the city.",
            categories=["Travel & Events"],
            tags=["travel vlog"],
            channel_is_verified=False,
        )
        self.assertEqual(result["verdict"], "pending")
        self.assertLess(result["host_native_score"], 50)

    def test_research_stubs_only_include_candidates(self):
        results = [
            self.screen(),
            self.screen(title="English Conversation Practice", channel="Learn English Daily"),
        ]
        stubs = youtube_discover.research_stubs(results)
        self.assertEqual(len(stubs["sources"]), 1)
        self.assertFalse(stubs["sources"][0]["native_speaker_verified"])
        self.assertEqual(stubs["sources"][0]["native_speaker_screen"]["verdict"], "candidate")

    def test_search_queries_use_american_service_talk(self):
        planned = youtube_discover.search_queries(2)
        self.assertTrue(planned)
        joined = " ".join(query for _scenario, query in planned)
        self.assertIn("can I get", joined)
        self.assertIn("USA", joined)
        self.assertIn("UK", joined)
        self.assertNotIn("entire menu", joined.split("-")[0])

    def test_ingest_attaches_screen_without_auto_verifying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "owned.vtt").write_text(
                "WEBVTT\n\n00:00:00.100 --> 00:00:01.000\n"
                "Customer: Could I have a loaf of bread, please?\n\n"
                "00:00:01.100 --> 00:00:03.000\n"
                "Mira: Of course. How many loaves would you like?\n",
                encoding="utf-8",
            )
            manifest = {
                "sources": [{
                    "source_id": "owned-001",
                    "source_url": "https://www.youtube.com/watch?v=example",
                    "transcript_path": "owned.vtt",
                    "rights": "owned",
                    "native_speaker_verified": True,
                    "native_speaker_evidence": "Speaker biography and native editor review",
                    "source_title": "A Morning at Our Neighborhood Bakery",
                    "source_description": "I was born in Texas. Unscripted bakery counter.",
                    "channel": "Local Life",
                    "source_kind": "on_location_service_interaction",
                    "metadata_review": {
                        "title_checked": True,
                        "description_checked": True,
                        "channel_checked": True,
                        "video_context_checked": True,
                    },
                    "real_life_verified": True,
                    "real_life_evidence": "Customer and staff are visibly interacting",
                    "unscripted_verified": True,
                    "unscripted_evidence": "Continuous on-location service footage",
                    "direct_dialogue_verified": True,
                    "verified_interaction_ranges": [{
                        "scenario_id": "food_ask_bread",
                        "request_start_seconds": 0.1,
                        "request_end_seconds": 1.0,
                        "response_start_seconds": 1.1,
                        "response_end_seconds": 3.0,
                        "request_speaker_role": "customer",
                        "response_speaker_role": "bakery_staff",
                        "distinct_speakers_verified": True,
                        "evidence": "Customer request is immediately followed by staff response",
                    }],
                    "scenario_ids": ["food_ask_bread"],
                    "automatic_caption_langs": ["en-orig"],
                }]
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(len(result["candidates"]), 1)
            screen = result["candidates"][0]["native_speaker_screen"]
            self.assertEqual(screen["verdict"], "candidate")
            self.assertFalse(screen["can_auto_verify"])

    def test_search_requires_yt_dlp(self):
        with mock.patch.object(youtube_discover, "_yt_dlp_command", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "yt-dlp"):
                youtube_discover.fetch_search_metadata("BBC bakery interview", 3)


if __name__ == "__main__":
    unittest.main()
