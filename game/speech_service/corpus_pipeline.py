"""Controlled corpus preparation for the five provisional Godot scenarios.

Acquisition is deliberately separate from this module. Operators supply local
captions plus a manifest containing the title/description/channel review and
time ranges for an observed, unscripted interaction. Raw captions and research
candidates remain outside ``game/data``; only explicitly approved,
release-eligible patterns may be promoted into a Godot JSON asset. New scene
families should first pass through ``native_scene_discovery.py``; this module
keeps the legacy scenario IDs stable until a replacement is approved.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUERY_FILE = ROOT / "corpus_queries.json"
ALLOWED_RIGHTS = {"owned", "licensed", "cc0", "cc_by", "written_permission"}
AUTHENTIC_SOURCE_KINDS = {
    "field_news_interview",
    "observational_documentary",
    "on_location_personal_vlog",
    "on_location_service_interaction",
    "workplace_documentary",
}
DEFAULT_ACTS = {
    "food_ask_bread": "offer_choice",
    "water_ask_clean_water": "give_direction",
    "warmth_ask_blanket": "confirm_help",
    "shelter_ask_sit_inside": "grant_permission",
    "belonging_small_talk_waiting_line": "ask_follow_up",
}
AD_MARKERS = ("sponsored by", "use code", "subscribe", "click the link", "patreon")
NON_REAL_LIFE_MARKERS = (
    "learn english",
    "english lesson",
    "english conversation",
    "conversation practice",
    "speaking practice",
    "listening practice",
    "daily dialogue",
    "dialogue practice",
    "esl",
    "a1-a2",
    "a1–a2",
    "a2-b1",
    "beginner english",
    "graded reader",
    "shadowing",
    "repeat after me",
    "podcast for beginners",
    "animated story",
    "movie clip",
    "short drama",
    "role play",
    "roleplay",
    "ai generated",
    "frases en",
    "aprender ingles",
    "aprender inglés",
    "speak english fluently",
    "english speaking for",
    "dialogue one",
    "dialogue collection",
    "easy english",
    "basic english",
    "ingilizce",
)
NON_DIALOGUE_TITLE_MARKERS = (
    "advice",
    "beginner's guide",
    "beginners guide",
    "explained",
    "explainer",
    "hotel review",
    "hotel tour",
    "travel guide",
    "travel tip",
    "travel tips",
    "what you need to know",
)
TAG_RE = re.compile(r"<[^>]+>")
SPEAKER_RE = re.compile(r"^(?P<speaker>[A-Za-z][A-Za-z .'-]{0,30}):\s+(?P<text>.+)$")
TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3})"
)


def load_queries() -> dict[str, dict]:
    payload = json.loads(QUERY_FILE.read_text(encoding="utf-8"))
    return {item["scenario_id"]: item for item in payload["queries"]}


def timestamp_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        hours, minutes, seconds = 0, int(parts[0]), float(parts[1])
    else:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
    return round(hours * 3600 + minutes * 60 + seconds, 3)


def clean_caption(text: str) -> str:
    value = html.unescape(TAG_RE.sub("", text))
    value = re.sub(r"\[[^]]*]|\([^)]*(?:music|applause|laughter)[^)]*\)", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" -\t\r\n")
    match = SPEAKER_RE.match(value)
    return match.group("text").strip() if match else value


def parse_captions(path: Path) -> list[dict]:
    blocks = re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8-sig"))
    cues: list[dict] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((index for index, line in enumerate(lines) if TIME_RE.search(line)), -1)
        if time_index < 0:
            continue
        match = TIME_RE.search(lines[time_index])
        raw_text = " ".join(lines[time_index + 1 :])
        speaker_match = SPEAKER_RE.match(html.unescape(TAG_RE.sub("", raw_text)).strip())
        text = clean_caption(raw_text)
        if not text or any(marker in text.lower() for marker in AD_MARKERS):
            continue
        words = text.split()
        if len(words) < 3 or len(words) > 35 or "http://" in text.lower() or "https://" in text.lower():
            continue
        cue = {
            "start": timestamp_seconds(match.group("start")),
            "end": timestamp_seconds(match.group("end")),
            "speaker": speaker_match.group("speaker").strip() if speaker_match else "unknown",
            "text": text,
        }
        if cues and cue["text"].casefold() == cues[-1]["text"].casefold():
            cues[-1]["end"] = cue["end"]
        elif cues and cue["text"].casefold().startswith(cues[-1]["text"].casefold()):
            cues[-1] = cue
        else:
            cues.append(cue)
    return cues


def segment_turns(cues: list[dict]) -> list[dict]:
    turns: list[dict] = []
    for cue in cues:
        if (
            turns
            and cue["speaker"] != "unknown"
            and cue["speaker"] == turns[-1]["speaker"]
            and cue["start"] - turns[-1]["end"] <= 1.5
            and len((turns[-1]["text"] + " " + cue["text"]).split()) <= 35
        ):
            turns[-1]["text"] += " " + cue["text"]
            turns[-1]["end"] = cue["end"]
        else:
            turns.append(dict(cue))
    return turns


def matching_scenarios(text: str, queries: dict[str, dict], allowed: list[str]) -> list[str]:
    lowered = text.casefold()
    return [
        scenario_id
        for scenario_id in allowed
        if scenario_id in queries
        and any(phrase.casefold() in lowered for phrase in queries[scenario_id]["required_phrases_any"])
    ]


def evidence_id(source_id: str, start: float, text: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{start:.3f}|{text}".encode("utf-8")).hexdigest()[:16]
    return f"evidence-{digest}"


def verified_interaction_ranges(source: dict) -> list[dict]:
    ranges = source.get("verified_interaction_ranges", [])
    if not isinstance(ranges, list):
        return []
    verified: list[dict] = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        try:
            request_start = float(item["request_start_seconds"])
            request_end = float(item["request_end_seconds"])
            response_start = float(item["response_start_seconds"])
            response_end = float(item["response_end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            item.get("scenario_id") not in DEFAULT_ACTS
            or request_start < 0
            or request_end <= request_start
            or response_start < request_start
            or response_end <= response_start
            or not str(item.get("evidence", "")).strip()
            or not str(item.get("request_speaker_role", "")).strip()
            or not str(item.get("response_speaker_role", "")).strip()
            or not bool(item.get("distinct_speakers_verified", False))
        ):
            continue
        verified.append({
            **item,
            "request_start_seconds": request_start,
            "request_end_seconds": request_end,
            "response_start_seconds": response_start,
            "response_end_seconds": response_end,
        })
    return verified


def real_life_source_check(source: dict) -> tuple[bool, str]:
    if not bool(source.get("real_life_verified", False)):
        return False, "real_life_not_verified"
    required_metadata = (
        "source_title",
        "source_description",
        "channel",
        "real_life_evidence",
        "native_speaker_evidence",
        "unscripted_evidence",
    )
    if any(not str(source.get(field, "")).strip() for field in required_metadata):
        return False, "source_metadata_incomplete"
    metadata_review = source.get("metadata_review", {})
    if not isinstance(metadata_review, dict) or not all(
        metadata_review.get(field) is True
        for field in ("title_checked", "description_checked", "channel_checked", "video_context_checked")
    ):
        return False, "source_metadata_not_reviewed"
    if source.get("source_kind") not in AUTHENTIC_SOURCE_KINDS:
        return False, "source_kind_not_allowed"
    searchable = " ".join(
        str(source.get(field, ""))
        for field in ("source_title", "source_description", "channel")
    ).casefold()
    if any(marker in searchable for marker in NON_REAL_LIFE_MARKERS):
        return False, "language_teaching_or_scripted_source"
    title = str(source.get("source_title", "")).casefold()
    if any(marker in title for marker in NON_DIALOGUE_TITLE_MARKERS):
        return False, "narrated_advice_or_review_source"
    if not bool(source.get("unscripted_verified", False)):
        return False, "unscripted_not_verified"
    if not bool(source.get("direct_dialogue_verified", False)):
        return False, "direct_dialogue_not_verified"
    if not verified_interaction_ranges(source):
        return False, "verified_interaction_ranges_missing"
    if not bool(source.get("native_speaker_verified", False)):
        return False, "native_speaker_not_verified"
    return True, ""


def text_in_range(turns: list[dict], start: float, end: float) -> tuple[str, str]:
    matching = [turn for turn in turns if turn["end"] >= start and turn["start"] <= end]
    if not matching:
        return "", "unknown"
    text = " ".join(turn["text"] for turn in matching)
    text = re.sub(r"\s+", " ", text).strip()
    speakers = {turn["speaker"] for turn in matching if turn["speaker"] != "unknown"}
    return text, next(iter(speakers)) if len(speakers) == 1 else "unknown"


def _screen_video(info: dict) -> dict:
    try:
        from game.speech_service.native_speaker_screener import screen_video
    except ImportError:
        from native_speaker_screener import screen_video
    return screen_video(info)


def ingest_manifest(manifest_path: Path) -> dict:

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    queries = load_queries()
    candidates: list[dict] = []
    rejected_sources: list[dict] = []
    rejected_interactions: list[dict] = []
    for source in manifest.get("sources", []):
        source_id = str(source.get("source_id", "")).strip()
        research_only = bool(source.get("research_only", False))
        rights = str(source.get("rights", "")).strip().lower()
        if research_only and not rights:
            rights = "research_pending"
        native_verified = bool(source.get("native_speaker_verified", False))
        transcript = (manifest_path.parent / str(source.get("transcript_path", ""))).resolve()
        real_life_ok, real_life_reason = real_life_source_check(source)
        release_checks_pass = rights in ALLOWED_RIGHTS and native_verified
        if (
            not source_id
            or not transcript.is_file()
            or not real_life_ok
            or (not research_only and not release_checks_pass)
        ):
            if not source_id or not transcript.is_file():
                reason = "source_id_or_file_check_failed"
            elif not real_life_ok:
                reason = real_life_reason
            else:
                reason = "rights_check_failed"
            rejected_sources.append({"source_id": source_id, "reason": reason})
            continue
        allowed_scenarios = source.get("scenario_ids") or list(queries)
        turns = segment_turns(parse_captions(transcript))
        for interaction in verified_interaction_ranges(source):
            scenario_id = interaction["scenario_id"]
            if scenario_id not in allowed_scenarios:
                rejected_interactions.append({
                    "source_id": source_id,
                    "scenario_id": scenario_id,
                    "reason": "scenario_not_allowed_for_source",
                })
                continue
            request_text, request_speaker = text_in_range(
                turns,
                interaction["request_start_seconds"],
                interaction["request_end_seconds"],
            )
            response_text, response_speaker = text_in_range(
                turns,
                interaction["response_start_seconds"],
                interaction["response_end_seconds"],
            )
            if not request_text or not response_text or len(response_text.split()) > 35:
                rejected_interactions.append({
                    "source_id": source_id,
                    "scenario_id": scenario_id,
                    "reason": "verified_dialogue_not_found_in_caption_range",
                })
                continue
            item_evidence_id = evidence_id(
                source_id,
                interaction["response_start_seconds"],
                response_text,
            )
            screen = source.get("native_speaker_screen")
            if not isinstance(screen, dict):
                screen = _screen_video({
                    "id": source_id,
                    "title": source.get("source_title", ""),
                    "channel": source.get("channel", ""),
                    "description": source.get("source_description", ""),
                    "webpage_url": source.get("source_url", ""),
                    "automatic_caption_langs": source.get("automatic_caption_langs", []),
                    "tags": source.get("tags", []),
                    "categories": source.get("categories", []),
                    "location": source.get("location", ""),
                    "channel_is_verified": source.get("channel_is_verified", False),
                })
            candidates.append({
                    "source_screening_version": 2,
                    "evidence_id": item_evidence_id,
                    "scenario_id": scenario_id,
                    "request_text": request_text,
                    "text": response_text,
                    "speech_act": DEFAULT_ACTS[scenario_id],
                    "request_speaker": request_speaker,
                    "speaker": response_speaker,
                    "request_speaker_role": interaction["request_speaker_role"],
                    "response_speaker_role": interaction["response_speaker_role"],
                    "source_id": source_id,
                    "source_url": source.get("source_url", ""),
                    "source_title": source.get("source_title", ""),
                    "source_description": source.get("source_description", ""),
                    "channel": source.get("channel", ""),
                    "source_kind": source.get("source_kind", ""),
                    "real_life_evidence": source.get("real_life_evidence", ""),
                    "unscripted_evidence": source.get("unscripted_evidence", ""),
                    "interaction_evidence": interaction["evidence"],
                    "request_start_seconds": interaction["request_start_seconds"],
                    "request_end_seconds": interaction["request_end_seconds"],
                    "start_seconds": interaction["response_start_seconds"],
                    "end_seconds": interaction["response_end_seconds"],
                    "rights": rights,
                    "native_speaker_evidence": source.get("native_speaker_evidence", ""),
                    "native_speaker_screen": {
                        "verdict": screen.get("verdict"),
                        "native_scope": screen.get("native_scope"),
                        "host_native_score": screen.get("host_native_score"),
                        "response_speaker_status": screen.get("response_speaker_status"),
                        "can_auto_verify": False,
                        "evidence": screen.get("evidence", []),
                        "reasons": screen.get("reasons", []),
                    },
                    "source_type": "youtube_caption_research" if research_only else "authorized_caption",
                    "review_status": (
                        "research_pending_rights_and_native_review"
                        if research_only
                        else "pending_native_editorial_review"
                    ),
                    "release_eligible": not research_only and release_checks_pass,
                    "approved": False,
                })
    return {
        "schema_version": 2,
        "candidates": candidates,
        "rejected_sources": rejected_sources,
        "rejected_interactions": rejected_interactions,
    }


def promote(review_path: Path) -> dict:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    patterns: list[dict] = []
    for item in review.get("candidates", []):
        if (
            not item.get("approved")
            or item.get("rights") not in ALLOWED_RIGHTS
            or not item.get("release_eligible")
            or item.get("source_screening_version") != 2
            or item.get("source_kind") not in AUTHENTIC_SOURCE_KINDS
            or not str(item.get("request_text", "")).strip()
            or not str(item.get("interaction_evidence", "")).strip()
            or not str(item.get("native_speaker_evidence", "")).strip()
            or not str(item.get("response_speaker_role", "")).strip()
        ):
            continue
        scenario_id = str(item.get("scenario_id", ""))
        evidence = str(item.get("evidence_id", ""))
        text = clean_caption(str(item.get("text", "")))
        if scenario_id not in DEFAULT_ACTS or not evidence or not text or len(text.split()) > 30:
            continue
        patterns.append({
            "id": f"corpus_{scenario_id}_{evidence.removeprefix('evidence-')}",
            "scenario_id": scenario_id,
            "text": text,
            "speech_act": str(item.get("speech_act") or DEFAULT_ACTS[scenario_id]),
            "emotion": str(item.get("emotion") or "natural"),
            "evidence_ids": [evidence],
            "provenance": {
                "source_type": "authorized_caption",
                "source_id": item.get("source_id", ""),
                "source_url": item.get("source_url", ""),
                "source_title": item.get("source_title", ""),
                "channel": item.get("channel", ""),
                "source_kind": item.get("source_kind", ""),
                "request_text": item.get("request_text", ""),
                "request_start_seconds": item.get("request_start_seconds"),
                "request_end_seconds": item.get("request_end_seconds"),
                "start_seconds": item.get("start_seconds"),
                "end_seconds": item.get("end_seconds"),
                "rights": item.get("rights"),
                "review_status": "native_editor_approved",
            },
        })
    return {"schema_version": 1, "patterns": patterns}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("queries")
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("manifest", type=Path)
    ingest.add_argument("output", type=Path)
    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("review", type=Path)
    promote_parser.add_argument("output", type=Path)
    screen = subparsers.add_parser("screen")
    screen.add_argument("input", type=Path)
    screen.add_argument("output", type=Path)
    discover = subparsers.add_parser("discover")
    discover.add_argument("output", type=Path)
    discover.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    if args.command == "queries":
        print(QUERY_FILE.read_text(encoding="utf-8"), end="")
    elif args.command == "ingest":
        write_json(args.output, ingest_manifest(args.manifest.resolve()))
    elif args.command == "screen":
        try:
            from game.speech_service.youtube_discover import build_report, format_table, research_stubs
            from game.speech_service.native_speaker_screener import screen_directory
        except ImportError:
            from youtube_discover import build_report, format_table, research_stubs
            from native_speaker_screener import screen_directory

        results = screen_directory(args.input.resolve())
        write_json(args.output, build_report(results, "local_info_json"))
        write_json(args.output.with_name(args.output.stem + "_research_stubs.json"), research_stubs(results))
        print(format_table(results))
    elif args.command == "discover":
        try:
            from game.speech_service.youtube_discover import build_report, discover_search, format_table, research_stubs
        except ImportError:
            from youtube_discover import build_report, discover_search, format_table, research_stubs

        results = discover_search(args.limit)
        write_json(args.output, build_report(results, "youtube_search"))
        write_json(args.output.with_name(args.output.stem + "_research_stubs.json"), research_stubs(results))
        print(format_table(results))
    else:
        write_json(args.output, promote(args.review.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
