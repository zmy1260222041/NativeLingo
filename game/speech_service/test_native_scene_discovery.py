import json
import tempfile
import unittest
from pathlib import Path

from game.speech_service.native_scene_discovery import (
    discover_scene_candidates,
    infer_scene_family,
    load_scene_spec,
    review_template,
    score_family_caption,
)


class NativeSceneDiscoveryTest(unittest.TestCase):
    def test_infers_scene_family_from_exchange_without_old_scenario_id(self):
        spec = load_scene_spec()
        family = infer_scene_family(
            {"query": '"for here or to go"'},
            {
                "video_id": "counter-1",
                "text": "Can I get a cheesesteak? >> For here or to go? >> For here, please.",
            },
            spec,
        )
        self.assertEqual(family["scene_id"], "counter_order")

    def test_builds_research_candidates_and_keeps_native_gate_closed(self):
        payload = {
            "source": "chrome_filmot",
            "searches": [
                {
                    "query": '"for here or to go"',
                    "hits": [
                        {
                            "video_id": "counter-1",
                            "start": 46,
                            "url": "https://www.youtube.com/watch?v=counter-1&t=46s",
                            "title": "Real Burger Counter",
                            "channel": "Local Eats",
                            "text": "Can I get a burger? >> For here or to go? >> To go, please.",
                        },
                        {
                            "video_id": "lesson-1",
                            "start": 12,
                            "title": "English Dialogue 1",
                            "channel": "Basic English Speaking",
                            "text": "Dialogue 1: Can I get a burger? For here or to go? Repeat after me.",
                        },
                    ],
                },
                {
                    "query": '"how long have you been in line"',
                    "hits": [
                        {
                            "video_id": "line-1",
                            "start": 422,
                            "title": "Local News at the Mall",
                            "channel": "WXX News",
                            "dialogue_evidence": {
                                "adjacent_sequence": {
                                    "request_cue": "how long",
                                    "response_cue": "hours",
                                }
                            },
                            "text": "How long have you been in line? >> Almost two hours.",
                        }
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])

        by_id = {scene["scene_id"]: scene for scene in result["scenes"]}
        self.assertEqual(by_id["counter_order"]["distinct_video_count"], 1)
        self.assertEqual(by_id["waiting_line_small_talk"]["distinct_video_count"], 1)
        self.assertFalse(by_id["counter_order"]["native_speaker_verified"])
        self.assertFalse(by_id["counter_order"]["evidence"][0]["distinct_speakers_verified"])
        self.assertEqual(by_id["counter_order"]["evidence"][0]["review_status"], "pending")
        self.assertFalse(by_id["counter_order"]["runtime_replacement"]["eligible"])
        self.assertTrue(any(item["reason"].startswith("teaching:") for item in result["rejected"]))

    def test_consumes_youtube_best_exchange_without_promoting_it(self):
        payload = {
            "results": [{
                "video_id": "line-youtube-1",
                "title": "Shoppers wait in line",
                "channel": "Denver7",
                "url": "https://www.youtube.com/watch?v=line-youtube-1",
                "verdict": "candidate",
                "best_exchange": {
                    "request_text": "How long have you been in line?",
                    "response_text": "Almost two hours.",
                    "request_start_seconds": 45.32,
                    "response_start_seconds": 47.32,
                    "request_cue": "how long",
                    "response_cue": "hours",
                    "topic_phrase": "how long",
                },
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "youtube.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])
        evidence = result["scenes"][0]["evidence"][0]
        self.assertEqual(result["scenes"][0]["scene_id"], "waiting_line_small_talk")
        self.assertEqual(evidence["start_seconds"], 45.32)
        self.assertIn("Almost two hours", evidence["excerpt"])
        self.assertFalse(evidence["native_speaker_verified"])

    def test_narration_without_exchange_is_not_a_scene(self):
        payload = {
            "results": [
                {
                    "video_id": "narration-1",
                    "title": "Hotel Review",
                    "channel": "Travel Guide",
                    "text": "Hotels usually have extra blankets for guests.",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])
        self.assertEqual(result["scenes"], [])
        self.assertEqual(result["rejected"][0]["reason"], "no_observed_exchange")

    def test_unrelated_caption_marker_is_not_treated_as_request_response(self):
        payload = {
            "results": [{
                "video_id": "narration-2",
                "title": "A market tour",
                "text": "The market opens at nine >> music continues",
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])
        self.assertEqual(result["scenes"], [])
        self.assertEqual(result["rejected"][0]["reason"], "no_observed_exchange")

    def test_non_observational_video_is_rejected_before_family_inference(self):
        payload = {
            "searches": [
                {
                    "query": '"for here or to go"',
                    "hits": [{
                        "video_id": "movie-1",
                        "title": "SML Movie Full Movie Marathon",
                        "text": "Is this for here or to go? >> To go.",
                    }],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])
        self.assertEqual(result["scenes"], [])
        self.assertEqual(result["rejected"][0]["reason"], "non_observational:full movie")

    def test_unicode_fold_filters_non_english_teaching_title(self):
        payload = {
            "searches": [{
                "query": '"for here or to go"',
                "hits": [{
                    "video_id": "lesson-tr",
                    "title": "Yeni Başlayanlar İçin İngilizce Dinleme",
                    "text": "Can I get a coffee? >> For here or to go? >> To go.",
                }],
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = discover_scene_candidates([path])
        self.assertEqual(result["scenes"], [])
        self.assertEqual(result["rejected"][0]["reason"], "teaching:ingilizce")

    def test_metadata_report_enriches_flat_filmot_hit_without_verifying_speaker(self):
        payload = {
            "searches": [{
                "query": '"for here or to go"',
                "hits": [{
                    "video_id": "counter-2",
                    "start": 11,
                    "text": "Can I get a sandwich? >> For here or to go? >> To go.",
                }],
            }]
        }
        metadata = {
            "results": [{
                "video_id": "counter-2",
                "title": "Lunch at the neighborhood deli",
                "channel": "Local Eats",
                "url": "https://www.youtube.com/watch?v=counter-2",
                "verdict": "candidate",
                "native_scope": "on_location_vlog",
                "host_native_score": 60,
                "response_speaker_status": "not_evidenced",
                "evidence": ["us_on_location"],
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            metadata_path = root / "metadata.json"
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            result = discover_scene_candidates([report_path], metadata_paths=[metadata_path])

        evidence = result["scenes"][0]["evidence"][0]
        self.assertEqual(evidence["title"], "Lunch at the neighborhood deli")
        self.assertEqual(evidence["channel"], "Local Eats")
        self.assertEqual(evidence["metadata_screening"]["verdict"], "candidate")
        self.assertFalse(evidence["native_speaker_verified"])

    def test_review_template_contains_manual_native_and_rights_gates(self):
        report = {
            "input_reports": ["filmot.json"],
            "scenes": [{
                "scene_id": "counter_order",
                "evidence": [{"video_id": "counter-1", "start_seconds": 10}],
            }],
        }
        template = review_template(report)
        review = template["reviews"][0]
        self.assertFalse(review["repeated_interaction_verified"])
        self.assertFalse(review["replacement_approved"])
        self.assertEqual(review["evidence"][0]["rights"], "research_pending")
        self.assertFalse(review["evidence"][0]["response_speaker_native_verified"])
        self.assertEqual(template["policy"]["minimum_independent_videos"], 2)

    def test_scores_adjacent_caption_turns_without_verifying_native_speaker(self):
        caption = """WEBVTT

00:00:01.000 --> 00:00:02.000
Customer: Can I get some water?

00:00:02.300 --> 00:00:03.500
Staff: Sure, here you go.
"""
        family = {
            "request_cues": ["can I get some water"],
            "response_cues": ["sure", "here you go"],
            "search_phrases": ["can I get a water"],
            "required_exchange_cues": ["water"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.vtt"
            path.write_text(caption, encoding="utf-8")
            windows = score_family_caption(path, family)
        self.assertEqual(len(windows), 1)
        self.assertTrue(windows[0]["distinct_speakers_verified"])
        self.assertEqual(windows[0]["request_text"], "Can I get some water?")

    def test_caption_question_without_family_request_is_not_a_help_scene(self):
        caption = """WEBVTT

00:00:01.000 --> 00:00:02.000
Reporter: What are the takeaways from that?

00:00:02.300 --> 00:00:03.500
Guest: To make sure our community has what it needs.
"""
        family = {
            "request_cues": ["can you help me"],
            "response_cues": ["sure", "no problem", "I can help"],
            "search_phrases": ["can you help me"],
            "required_exchange_cues": ["sure", "no problem"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.vtt"
            path.write_text(caption, encoding="utf-8")
            windows = score_family_caption(path, family)
        self.assertEqual(windows, [])


if __name__ == "__main__":
    unittest.main()
