import json
import tempfile
import unittest
from pathlib import Path

from game.speech_service import corpus_pipeline


class CorpusPipelineTest(unittest.TestCase):
    def authentic_source(self, **overrides):
        source = {
            "source_id": "owned-001",
            "source_url": "https://www.youtube.com/watch?v=example",
            "transcript_path": "owned.vtt",
            "rights": "owned",
            "native_speaker_verified": True,
            "native_speaker_evidence": "Speaker biography and native editor review",
            "source_title": "A Morning at Our Neighborhood Bakery",
            "source_description": "An unscripted visit filmed at the bakery counter.",
            "channel": "Local Life",
            "source_kind": "on_location_service_interaction",
            "metadata_review": {
                "title_checked": True,
                "description_checked": True,
                "channel_checked": True,
                "video_context_checked": True,
            },
            "real_life_verified": True,
            "real_life_evidence": "Customer and staff are visibly interacting at the real counter",
            "unscripted_verified": True,
            "unscripted_evidence": "Continuous on-location service footage, not a demonstration",
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
        }
        source.update(overrides)
        return source

    def test_ingest_keeps_evidence_and_rejects_unlicensed_sources(self):
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
                "sources": [
                    self.authentic_source(),
                    {
                        "source_id": "commercial-001",
                        "transcript_path": "owned.vtt",
                        "rights": "unknown",
                        "native_speaker_verified": True,
                    },
                ]
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(len(result["candidates"]), 1)
            self.assertTrue(result["candidates"][0]["evidence_id"].startswith("evidence-"))
            self.assertEqual(result["candidates"][0]["start_seconds"], 1.1)
            self.assertEqual(
                result["candidates"][0]["request_text"],
                "Could I have a loaf of bread, please?",
            )
            self.assertEqual(len(result["rejected_sources"]), 1)

    def test_only_explicitly_approved_candidates_are_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            review_path = Path(directory) / "review.json"
            review_path.write_text(json.dumps({"candidates": [
                {
                    "approved": True,
                    "release_eligible": True,
                    "rights": "written_permission",
                    "source_screening_version": 2,
                    "source_kind": "on_location_service_interaction",
                    "scenario_id": "warmth_ask_blanket",
                    "evidence_id": "evidence-abc",
                    "request_text": "Could I have an extra blanket, please?",
                    "text": "Of course. I have a spare blanket for you.",
                    "interaction_evidence": "Observed guest and hotel staff exchange",
                    "native_speaker_evidence": "Signed production release",
                    "response_speaker_role": "hotel_staff",
                    "source_id": "licensed-001",
                    "start_seconds": 2.0,
                    "end_seconds": 4.0,
                },
                {
                    "approved": False,
                    "release_eligible": True,
                    "rights": "owned",
                    "source_screening_version": 2,
                    "source_kind": "on_location_service_interaction",
                    "scenario_id": "warmth_ask_blanket",
                    "evidence_id": "evidence-def",
                    "request_text": "Could I have an extra blanket, please?",
                    "text": "This must not ship.",
                    "interaction_evidence": "Observed exchange",
                    "native_speaker_evidence": "Signed release",
                    "response_speaker_role": "hotel_staff",
                },
            ]}), encoding="utf-8")
            promoted = corpus_pipeline.promote(review_path)
            self.assertEqual(len(promoted["patterns"]), 1)
            self.assertEqual(promoted["patterns"][0]["provenance"]["review_status"], "native_editor_approved")

    def test_research_only_sources_keep_evidence_without_becoming_release_patterns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "youtube.vtt").write_text(
                "WEBVTT\n\n00:00:00.100 --> 00:00:01.000\n"
                "Could I have a loaf of bread, please?\n\n"
                "00:00:01.100 --> 00:00:03.000\n"
                "Sure, how many loaves would you like?\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({"sources": [self.authentic_source(
                source_id="youtube-research-001",
                transcript_path="youtube.vtt",
                research_only=True,
                rights="research_pending",
            )]}), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(len(result["candidates"]), 1)
            candidate = result["candidates"][0]
            self.assertEqual(candidate["source_type"], "youtube_caption_research")
            self.assertFalse(candidate["release_eligible"])
            self.assertEqual(candidate["review_status"], "research_pending_rights_and_native_review")

            review_path = root / "review.json"
            review_path.write_text(json.dumps({"candidates": [{
                **candidate,
                "approved": True,
            }]}), encoding="utf-8")
            promoted = corpus_pipeline.promote(review_path)
            self.assertEqual(promoted["patterns"], [])

    def test_promotion_cannot_bypass_source_screening(self):
        with tempfile.TemporaryDirectory() as directory:
            review_path = Path(directory) / "review.json"
            review_path.write_text(json.dumps({"candidates": [{
                "approved": True,
                "release_eligible": True,
                "rights": "owned",
                "scenario_id": "food_ask_bread",
                "evidence_id": "evidence-handcrafted",
                "text": "Sure, how many loaves would you like?",
            }]}), encoding="utf-8")
            promoted = corpus_pipeline.promote(review_path)
            self.assertEqual(promoted["patterns"], [])

    def test_language_teaching_video_is_rejected_even_in_research_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lesson.vtt").write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n"
                "Sure, how many loaves would you like?\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({"sources": [self.authentic_source(
                source_id="youtube-lesson-001",
                transcript_path="lesson.vtt",
                research_only=True,
                rights="research_pending",
                source_title="English Conversation Practice at a Bakery A1-A2",
                source_description="Repeat after the scripted dialogue.",
                channel="Learn English Daily",
            )]}), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(result["candidates"], [])
            self.assertEqual(
                result["rejected_sources"][0]["reason"],
                "language_teaching_or_scripted_source",
            )

    def test_narrated_travel_advice_is_not_direct_dialogue_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "owned.vtt").write_text(
                "WEBVTT\n\n00:00:00.100 --> 00:00:03.000\n"
                "Hotels usually have extra blankets for guests.\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({"sources": [self.authentic_source(
                source_title="Budget Travel Tip: Extra Blankets in Hotels",
                direct_dialogue_verified=False,
                scenario_ids=["warmth_ask_blanket"],
            )]}), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(result["candidates"], [])
            self.assertEqual(
                result["rejected_sources"][0]["reason"],
                "narrated_advice_or_review_source",
            )

    def test_unverified_direct_dialogue_is_rejected_before_caption_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "owned.vtt").write_text(
                "WEBVTT\n\n00:00:00.100 --> 00:00:03.000\n"
                "Of course, I can get you a blanket.\n",
                encoding="utf-8",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({"sources": [self.authentic_source(
                source_title="A Cold Night at a Family Hotel",
                direct_dialogue_verified=False,
            )]}), encoding="utf-8")
            result = corpus_pipeline.ingest_manifest(manifest_path)
            self.assertEqual(result["candidates"], [])
            self.assertEqual(
                result["rejected_sources"][0]["reason"],
                "direct_dialogue_not_verified",
            )


if __name__ == "__main__":
    unittest.main()
