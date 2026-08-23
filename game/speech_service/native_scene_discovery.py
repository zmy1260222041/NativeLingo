"""Derive research-only scene families from observed video exchanges.

This is deliberately separate from the five pilot scenarios. The input is a
local Filmot or YouTube discovery report, not a network client. A hit becomes
evidence for a scene family only when it contains an observable exchange; the
output never verifies a native speaker, grants rights, or edits Godot assets.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_QUERY_FILE = ROOT / "native_scene_queries.json"
TEACHING_MARKERS = (
    "learn english",
    "english lesson",
    "english conversation",
    "conversation practice",
    "dialogue collection",
    "dialogue one",
    "dialogue 1",
    "repeat after",
    "shadowing",
    "frases",
    "ingles",
    "inglés",
    "english singsing",
    "basic english",
    "easy english",
    "boston english",
    "ingilizce",
)
NON_OBSERVATIONAL_MARKERS = (
    "full movie",
    "movie marathon",
    "sml movie",
    "roblox",
    "minecraft",
    "game grumps",
    "official audio",
    "music video",
    "lyrics",
    "podcast",
    "prank",
    "roleplay",
    "role play",
    "fictional story",
    "storytime",
    "reddit story",
    "revenge served",
    "gender reveal",
    "full episode",
    "livestream",
    "live stream",
    "poker",
    "final table",
    "protest",
    "tiktok",
    "challenge",
    "ai controls",
    "tuscany",
    "italy",
    "europe",
    "c-drama",
)
_FOLD_RE = re.compile(r"\s+")
SEARCH_CAPTIONS = ROOT / "corpus_work" / "source_first_search_captions"


def load_scene_spec(path: Path = DEFAULT_QUERY_FILE) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("scene_families"), list):
        raise ValueError(f"Invalid source-first scene specification: {path}")
    return payload


def _fold(value: object) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "").casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return _FOLD_RE.sub(" ", folded).strip()


def _phrase_present(text: object, phrase: object) -> bool:
    folded_phrase = _fold(phrase)
    if not folded_phrase:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(folded_phrase)}(?!\w)", _fold(text)))


def _iter_searches(payload: object, source_name: str) -> Iterable[tuple[str, dict]]:
    if not isinstance(payload, dict):
        return
    searches = payload.get("searches")
    if isinstance(searches, list):
        for search in searches:
            if not isinstance(search, dict):
                continue
            for hit in search.get("hits") or []:
                if isinstance(hit, dict):
                    yield source_name, {"search": search, "hit": hit}
            for hit in search.get("results") or []:
                if isinstance(hit, dict):
                    yield source_name, {"search": search, "hit": hit}
        return
    for key in ("results", "hits"):
        for hit in payload.get(key) or []:
            if isinstance(hit, dict):
                yield source_name, {"search": payload, "hit": hit}


def _hit_blob(search: dict, hit: dict) -> str:
    best_exchange = hit.get("best_exchange") if isinstance(hit.get("best_exchange"), dict) else {}
    return _fold(" ".join(
        str(value or "")
        for value in (
            search.get("title"),
            search.get("query"),
            search.get("family"),
            search.get("scenario_id"),
            hit.get("title"),
            hit.get("channel"),
            hit.get("description"),
            hit.get("text"),
            best_exchange.get("request_text"),
            best_exchange.get("response_text"),
            best_exchange.get("request_cue"),
            best_exchange.get("response_cue"),
            best_exchange.get("topic_phrase"),
        )
    ))


def teaching_reason(search: dict, hit: dict) -> str:
    if hit.get("language_teaching") is True:
        return str(hit.get("language_teaching_reason") or "marked_by_local_filter")
    blob = _hit_blob(search, hit)
    for marker in TEACHING_MARKERS:
        if marker in blob:
            return marker
    return ""


def non_observational_reason(search: dict, hit: dict) -> str:
    blob = _hit_blob(search, hit)
    for marker in NON_OBSERVATIONAL_MARKERS:
        if marker in blob:
            return marker
    return ""


def exchange_reason(search: dict, hit: dict) -> str:
    evidence = hit.get("dialogue_evidence")
    if isinstance(evidence, dict):
        if evidence.get("adjacent_sequence"):
            return "adjacent_sequence"
        if evidence.get("speaker_boundary_marker") is True:
            return "speaker_boundary_marker"
    best_exchange = hit.get("best_exchange")
    if isinstance(best_exchange, dict) and best_exchange.get("request_text") and best_exchange.get("response_text"):
        return "caption_adjacent_turns"
    text = str(hit.get("text") or "")
    segments = [segment.strip() for segment in text.split(">>") if segment.strip()]
    if len(segments) >= 2:
        request_re = re.compile(
            r"\b(?:can i|could i|would you|how long|do you|is it|what|where|which|"
            r"anything else|i(?:'ll| will) take|i want|i need)\b",
            re.I,
        )
        response_re = re.compile(
            r"\b(?:sure|yeah|yes|no|for here|to go|almost|right|left|of course|"
            r"no problem|one|two|maybe|since|hours?)\b",
            re.I,
        )
        if request_re.search(text) and response_re.search(text):
            return "caption_speaker_marker"
    if re.search(r"\?[^?]{0,160}(?:sure|yeah|yes|no problem|of course|to go|for here)", text, re.I):
        return "question_response_sequence"
    return ""


def _family_score(search: dict, hit: dict, family: dict) -> int:
    blob = _hit_blob(search, hit)
    primary = 0
    for phrase in family.get("search_phrases") or []:
        if _phrase_present(blob, phrase):
            primary += 1
    if primary == 0:
        best_exchange = hit.get("best_exchange") if isinstance(hit.get("best_exchange"), dict) else {}
        exchange_blob = " ".join(
            str(best_exchange.get(key) or "")
            for key in ("request_text", "response_text", "request_cue", "response_cue", "topic_phrase")
        )
        for cue in family.get("required_exchange_cues") or []:
            if _phrase_present(exchange_blob, cue):
                primary += 1
        hints = {str(item).strip() for item in hit.get("scenario_hints") or []}
        if str(family.get("scene_id")) in hints:
            primary = max(primary, 1)
    if primary == 0:
        return 0
    score = primary * 3
    for cue in family.get("required_exchange_cues") or []:
        if _phrase_present(blob, cue):
            score += 1
    return score


def infer_scene_family(search: dict, hit: dict, spec: dict) -> dict | None:
    ranked = []
    for family in spec.get("scene_families") or []:
        if not isinstance(family, dict) or not str(family.get("scene_id") or "").strip():
            continue
        ranked.append((_family_score(search, hit, family), family))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("scene_id"))))
    if not ranked or ranked[0][0] <= 0:
        return None
    return ranked[0][1]


def _video_url(hit: dict) -> str:
    url = str(hit.get("url") or hit.get("source_url") or "").strip()
    if url:
        return url
    video_id = str(hit.get("video_id") or hit.get("id") or "").strip()
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _evidence_record(
    source_name: str,
    search: dict,
    hit: dict,
    reason: str,
    metadata: dict | None = None,
) -> dict:
    metadata = metadata or {}
    best_exchange = hit.get("best_exchange") if isinstance(hit.get("best_exchange"), dict) else {}
    video_id = str(hit.get("video_id") or hit.get("id") or metadata.get("video_id") or "").strip()
    source_url = _video_url(hit) or str(metadata.get("url") or metadata.get("source_url") or "").strip()
    excerpt = str(hit.get("text") or hit.get("excerpt") or "").strip()
    if not excerpt and best_exchange:
        excerpt = (
            f"{best_exchange.get('request_text', '')} >> "
            f"{best_exchange.get('response_text', '')}"
        ).strip()
    return {
        "video_id": video_id,
        "source_url": source_url,
        "start_seconds": hit.get("start", hit.get("start_seconds", best_exchange.get("request_start_seconds"))),
        "title": str(hit.get("title") or search.get("title") or metadata.get("title") or "").strip(),
        "channel": str(hit.get("channel") or metadata.get("channel") or "").strip(),
        "excerpt": excerpt,
        "exchange_evidence": reason,
        "source_report": source_name,
        "search_query": str(search.get("query") or "").strip(),
        "search_family": str(search.get("family") or "").strip(),
        "metadata_screening": {
            "verdict": metadata.get("verdict", "unknown"),
            "native_scope": metadata.get("native_scope", "unknown"),
            "host_native_score": metadata.get("host_native_score"),
            "response_speaker_status": metadata.get("response_speaker_status", "not_evidenced"),
            "evidence": list(metadata.get("evidence") or []),
        },
        "distinct_speakers_verified": False,
        "native_speaker_verified": False,
        "rights": "research_pending",
        "review_status": "pending",
        **({"interaction_window": best_exchange} if best_exchange else {}),
    }


def _metadata_index(paths: Iterable[Path]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("results") if isinstance(payload, dict) else None
        if entries is None and isinstance(payload, dict):
            entries = payload.get("sources")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            video_id = str(entry.get("video_id") or entry.get("id") or "").strip()
            if not video_id:
                source_id = str(entry.get("source_id") or "")
                video_id = source_id.removeprefix("youtube-")
            if video_id:
                index[video_id] = entry
    return index


def discover_scene_candidates(
    input_paths: Iterable[Path],
    spec: dict | None = None,
    metadata_paths: Iterable[Path] = (),
) -> dict:
    scene_spec = spec or load_scene_spec()
    metadata = _metadata_index(metadata_paths)
    families = {
        str(item["scene_id"]): item
        for item in scene_spec.get("scene_families") or []
        if isinstance(item, dict) and str(item.get("scene_id") or "").strip()
    }
    evidence_by_scene: dict[str, list[dict]] = {scene_id: [] for scene_id in families}
    rejected: list[dict] = []
    seen: set[tuple[str, object, str]] = set()

    for input_path in input_paths:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        for source_name, item in _iter_searches(payload, str(input_path)):
            search = item["search"]
            hit = item["hit"]
            reason = teaching_reason(search, hit)
            if reason:
                rejected.append({"video_id": hit.get("video_id"), "reason": f"teaching:{reason}"})
                continue
            reason = non_observational_reason(search, hit)
            if reason:
                rejected.append({"video_id": hit.get("video_id"), "reason": f"non_observational:{reason}"})
                continue
            exchange = exchange_reason(search, hit)
            if not exchange:
                rejected.append({"video_id": hit.get("video_id"), "reason": "no_observed_exchange"})
                continue
            family = infer_scene_family(search, hit, scene_spec)
            if family is None:
                rejected.append({"video_id": hit.get("video_id"), "reason": "no_scene_family"})
                continue
            scene_id = str(family["scene_id"])
            video_id = str(hit.get("video_id") or hit.get("id") or "").strip()
            record = _evidence_record(source_name, search, hit, exchange, metadata.get(video_id))
            key = (record["video_id"], record["start_seconds"], scene_id)
            if key in seen:
                continue
            seen.add(key)
            evidence_by_scene[scene_id].append(record)

    scenes = []
    for scene_id, family in families.items():
        evidence = evidence_by_scene[scene_id]
        if not evidence:
            continue
        scenes.append({
            "scene_id": scene_id,
            "label": family.get("label", scene_id),
            "status": "research_candidate",
            "observed_evidence_count": len(evidence),
            "distinct_video_count": len({item["video_id"] for item in evidence if item["video_id"]}),
            "evidence": evidence,
            "native_speaker_verified": False,
            "rights": "research_pending",
            "runtime_replacement": {
                "eligible": False,
                "reason": "requires independent native-speaker, rights, and scene review",
            },
        })
    scenes.sort(key=lambda item: (-item["distinct_video_count"], item["scene_id"]))
    return {
        "schema_version": 1,
        "mode": "source_first",
        "policy": scene_spec.get("policy", {}),
        "input_reports": [str(path) for path in input_paths],
        "scenes": scenes,
        "rejected": rejected,
    }


def review_template(candidate_report: dict) -> dict:
    """Create a human-review file without changing candidate eligibility."""
    reviews = []
    for scene in candidate_report.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        evidence_reviews = []
        for evidence in scene.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            evidence_reviews.append({
                "video_id": evidence.get("video_id", ""),
                "start_seconds": evidence.get("start_seconds"),
                "real_event_verified": False,
                "adjacent_request_response_verified": False,
                "distinct_speakers_verified": False,
                "response_speaker_native_verified": False,
                "native_speaker_evidence": "",
                "rights": "research_pending",
                "rights_evidence": "",
                "review_status": "pending",
                "notes": "",
            })
        reviews.append({
            "scene_id": scene.get("scene_id", ""),
            "replacement_target": "",
            "repeated_interaction_verified": False,
            "replacement_approved": False,
            "reviewer": "",
            "review_notes": "",
            "evidence": evidence_reviews,
        })
    return {
        "schema_version": 1,
        "mode": "source_first_review",
        "policy": {
            "required_evidence": [
                "real_event_verified",
                "adjacent_request_response_verified",
                "distinct_speakers_verified",
                "response_speaker_native_verified",
                "rights",
            ],
            "minimum_independent_videos": 2,
            "allowed_rights": ["owned", "licensed", "cc0", "cc_by", "written_permission"],
            "replacement_approval_is_manual": True,
        },
        "candidate_report_inputs": candidate_report.get("input_reports", []),
        "reviews": reviews,
    }


def score_family_caption(caption_path: Path, family: dict) -> list[dict]:
    """Find adjacent request/response windows in one downloaded caption file."""
    try:
        from game.speech_service.corpus_pipeline import parse_captions, segment_turns
    except ImportError:
        from corpus_pipeline import parse_captions, segment_turns

    turns = segment_turns(parse_captions(caption_path))
    request_cues = [_fold(cue) for cue in family.get("request_cues") or []]
    response_cues = [_fold(cue) for cue in family.get("response_cues") or []]
    topic_cues = [
        _fold(cue)
        for cue in (family.get("search_phrases") or []) + (family.get("required_exchange_cues") or [])
    ]
    windows: list[dict] = []
    for index, request_turn in enumerate(turns):
        request_text = str(request_turn.get("text") or "")
        request_folded = _fold(request_text)
        if not any(_phrase_present(request_folded, cue) for cue in request_cues):
            continue
        for response_turn in turns[index + 1 : index + 3]:
            gap = float(response_turn.get("start") or 0) - float(request_turn.get("end") or 0)
            if gap > 8:
                break
            response_text = str(response_turn.get("text") or "")
            response_folded = _fold(response_text)
            if not any(_phrase_present(response_folded, cue) for cue in response_cues):
                continue
            combined = f"{request_folded} {response_folded}"
            if topic_cues and not any(_phrase_present(combined, cue) for cue in topic_cues):
                continue
            request_speaker = str(request_turn.get("speaker") or "unknown")
            response_speaker = str(response_turn.get("speaker") or "unknown")
            if (
                request_speaker != "unknown"
                and response_speaker != "unknown"
                and request_speaker == response_speaker
            ):
                continue
            windows.append({
                "request_text": request_text,
                "response_text": response_text,
                "request_start_seconds": request_turn.get("start"),
                "request_end_seconds": request_turn.get("end"),
                "response_start_seconds": response_turn.get("start"),
                "response_end_seconds": response_turn.get("end"),
                "request_speaker": request_speaker,
                "response_speaker": response_speaker,
                "distinct_speakers_verified": (
                    request_speaker != "unknown"
                    and response_speaker != "unknown"
                    and request_speaker != response_speaker
                ),
                "exchange_evidence": "caption_adjacent_turns",
            })
            break
    return windows


def discover_youtube_scene_candidates(limit: int = 5, families_limit: int = 6) -> dict:
    """Search YouTube and build research-only source-first candidates.

    This command downloads metadata and captions through yt-dlp, then applies
    the same local filters as saved Filmot reports. It never changes runtime
    dialogue assets or sets native-speaker verification.
    """
    try:
        from game.speech_service.youtube_discover import fetch_auto_captions, fetch_search_metadata
        from game.speech_service.native_speaker_screener import screen_video
    except ImportError:
        from youtube_discover import fetch_auto_captions, fetch_search_metadata
        from native_speaker_screener import screen_video

    scene_spec = load_scene_spec()
    families = {
        str(item["scene_id"]): item
        for item in scene_spec.get("scene_families") or []
        if isinstance(item, dict) and str(item.get("scene_id") or "").strip()
    }
    evidence_by_scene: dict[str, list[dict]] = {scene_id: [] for scene_id in families}
    rejected: list[dict] = []
    seen: set[str] = set()
    search_requests: list[dict] = []

    for family in list(families.values())[:families_limit]:
        scene_id = str(family["scene_id"])
        for query in family.get("youtube_queries") or []:
            query = str(query).strip()
            if not query:
                continue
            search_requests.append({"scene_id": scene_id, "query": query})
            for info in fetch_search_metadata(query, limit):
                video_id = str(info.get("id") or "").strip()
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                search = {"query": query, "family": "youtube_source_first", "scenario_id": scene_id}
                reason = teaching_reason(search, info)
                if reason:
                    rejected.append({"video_id": video_id, "reason": f"teaching:{reason}", "query": query})
                    continue
                reason = non_observational_reason(search, info)
                if reason:
                    rejected.append({"video_id": video_id, "reason": f"non_observational:{reason}", "query": query})
                    continue
                screened = screen_video(info)
                if screened.get("verdict") == "reject":
                    rejected.append({"video_id": video_id, "reason": "native_screen_reject", "query": query})
                    continue
                caption_path = fetch_auto_captions(video_id, SEARCH_CAPTIONS)
                if caption_path is None:
                    rejected.append({"video_id": video_id, "reason": "english_caption_unavailable", "query": query})
                    continue
                windows = score_family_caption(caption_path, family)
                if not windows:
                    rejected.append({"video_id": video_id, "reason": "no_adjacent_exchange", "query": query})
                    continue
                hit = {
                    "video_id": video_id,
                    "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                    "title": info.get("title", ""),
                    "channel": info.get("channel", ""),
                    "text": f"{windows[0]['request_text']} >> {windows[0]['response_text']}",
                    "start": windows[0]["request_start_seconds"],
                    "dialogue_evidence": {
                        "adjacent_sequence": windows[0],
                    },
                }
                record = _evidence_record(
                    "youtube_search",
                    search,
                    hit,
                    "caption_adjacent_turns",
                    {
                        "video_id": video_id,
                        "url": info.get("webpage_url", ""),
                        "title": info.get("title", ""),
                        "channel": info.get("channel", ""),
                        **screened,
                    },
                )
                record["caption_path"] = str(caption_path)
                record["interaction_window"] = windows[0]
                evidence_by_scene[scene_id].append(record)

    scenes = []
    for scene_id, family in families.items():
        evidence = evidence_by_scene[scene_id]
        if not evidence:
            continue
        scenes.append({
            "scene_id": scene_id,
            "label": family.get("label", scene_id),
            "status": "research_candidate",
            "observed_evidence_count": len(evidence),
            "distinct_video_count": len({item["video_id"] for item in evidence if item["video_id"]}),
            "evidence": evidence,
            "native_speaker_verified": False,
            "rights": "research_pending",
            "runtime_replacement": {
                "eligible": False,
                "reason": "requires independent native-speaker, rights, and scene review",
            },
        })
    scenes.sort(key=lambda item: (-item["distinct_video_count"], item["scene_id"]))
    return {
        "schema_version": 1,
        "mode": "source_first_youtube_search",
        "policy": scene_spec.get("policy", {}),
        "search_requests": search_requests,
        "scenes": scenes,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build research-only scene candidates from local video reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract")
    extract.add_argument("inputs", nargs="+", type=Path)
    extract.add_argument(
        "--metadata",
        action="append",
        default=[],
        type=Path,
        help="Optional native_speaker_screener report(s) keyed by video_id.",
    )
    extract.add_argument("--output", required=True, type=Path)
    template = subparsers.add_parser("review-template")
    template.add_argument("candidate_report", type=Path)
    template.add_argument("--output", required=True, type=Path)
    search = subparsers.add_parser("search", help="Search YouTube and screen source-first dialogue candidates")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--families", type=int, default=6)
    search.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "extract":
        result = discover_scene_candidates(
            [path.resolve() for path in args.inputs],
            metadata_paths=[path.resolve() for path in args.metadata],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "scenes": len(result["scenes"]),
            "rejected": len(result["rejected"]),
            "output": str(args.output),
        }))
        return 0
    if args.command == "review-template":
        candidate_report = json.loads(args.candidate_report.read_text(encoding="utf-8"))
        result = review_template(candidate_report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "scenes": len(result["reviews"]),
            "output": str(args.output),
        }))
        return 0
    if args.command == "search":
        result = discover_youtube_scene_candidates(args.limit, args.families)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "scenes": len(result["scenes"]),
            "rejected": len(result["rejected"]),
            "output": str(args.output),
        }))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
