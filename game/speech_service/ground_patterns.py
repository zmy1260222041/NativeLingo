"""Ground Godot NPC response patterns in observed YouTube research corpus.

Input is the versioned, curated ``grounding_evidence.json``: every entry is an
adjacent request-response exchange observed in a video that cleared an
American-variety screening tier, plus the normalized project-owned line derived
from one of its turns. Output is ``corpus_grounded_patterns.json`` in the Godot
response-pattern directory, plus refreshed ``response_pattern_ids`` and
provenance blocks in each scenario JSON. The source clips themselves stay
``research_pending``: nothing verbatim longer than a short functional phrase is
shipped, rights stay ``project_owned``, and every pattern keeps the evidence
link so later editorial review can retire or promote it.
"""
from __future__ import annotations

import argparse
import json
import re
import string
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from corpus_pipeline import AD_MARKERS, NON_REAL_LIFE_MARKERS, evidence_id  # noqa: E402

GAME_ROOT = _SERVICE_DIR.parent
DEFAULT_EVIDENCE = _SERVICE_DIR / "grounding_evidence.json"
SCENARIO_DIR = GAME_ROOT / "data" / "dialogue" / "scenarios"
PATTERN_DIR = GAME_ROOT / "data" / "dialogue" / "response_patterns"
OUTPUT_NAME = "corpus_grounded_patterns.json"
AUDIT_PATH = _SERVICE_DIR / "corpus_work" / "grounding_audit.json"
GROUNDED_ID_RE = re.compile(r"_yt_\d{2}$")
MAX_WORDS = 22
ALLOWED_TIERS = ("screened_candidate_us_news", "us_onlocation_vlog_oembed")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_line(text: str) -> str:
    value = re.sub(r">>", " ", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    value = value[0].upper() + value[1:]
    if value[-1] not in ".?!":
        value += "."
    return value


def load_scenarios() -> dict[str, dict]:
    scenarios: dict[str, dict] = {}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = load_json(path)
        scenario_id = str(data.get("godot_scenario_id", "")).strip().lower()
        if scenario_id:
            scenarios[scenario_id] = {"data": data, "path": path}
    return scenarios


def existing_pattern_texts(exclude_output: bool = True) -> tuple[set[str], list[dict]]:
    texts: set[str] = set()
    patterns: list[dict] = []
    for path in sorted(PATTERN_DIR.glob("*.json")):
        if exclude_output and path.name == OUTPUT_NAME:
            continue
        for pattern in load_json(path).get("patterns", []):
            if not isinstance(pattern, dict):
                continue
            patterns.append(pattern)
            text = normalize_line(str(pattern.get("text", "")))
            if text:
                texts.add(text.casefold())
    return texts, patterns


def validate_entry(entry: dict, scenarios: dict[str, dict]) -> str:
    scenario_id = str(entry.get("scenario_id", "")).strip().lower()
    if scenario_id not in scenarios:
        return "unknown_scenario"
    if str(entry.get("tier", "")) not in ALLOWED_TIERS:
        return "tier_not_allowed"
    if not str(entry.get("video_id", "")).strip():
        return "video_id_missing"
    if str(entry.get("video_id", "")) not in str(entry.get("source_url", "")):
        return "source_url_video_mismatch"
    anchor = entry.get("anchor_seconds")
    if not isinstance(anchor, (int, float)) or anchor < 0:
        return "anchor_seconds_invalid"
    exchange = entry.get("observed_exchange")
    if not isinstance(exchange, list) or len(exchange) < 2 or any(not str(turn).strip() for turn in exchange):
        return "observed_exchange_invalid"
    index = entry.get("grounded_turn_index")
    if not isinstance(index, int) or not 0 <= index < len(exchange):
        return "grounded_turn_index_out_of_range"
    grounded = normalize_line(str(entry.get("grounded_text", "")))
    if not grounded:
        return "grounded_text_empty"
    if len(grounded.split()) > MAX_WORDS:
        return "grounded_text_too_long"
    if not all(char in string.printable for char in grounded):
        return "grounded_text_not_printable_ascii"
    lowered = grounded.casefold()
    if any(marker in lowered for marker in NON_REAL_LIFE_MARKERS):
        return "grounded_text_hits_teaching_marker"
    if any(marker in lowered for marker in AD_MARKERS):
        return "grounded_text_hits_ad_marker"
    if "http" in lowered:
        return "grounded_text_contains_url"
    scenario = scenarios[scenario_id]["data"]
    if str(entry.get("speech_act", "")) not in (scenario.get("allowed_speech_acts") or []):
        return "speech_act_not_allowed"
    if not str(entry.get("emotion", "")).strip():
        return "emotion_missing"
    if not str(entry.get("speaker_role", "")).strip():
        return "speaker_role_missing"
    return ""


def build_pattern(entry: dict, ordinal: int) -> dict:
    scenario_id = str(entry["scenario_id"]).strip().lower()
    observed_turn = str(entry["observed_exchange"][int(entry["grounded_turn_index"])]).strip()
    item_evidence_id = evidence_id(str(entry["video_id"]), float(entry["anchor_seconds"]), observed_turn)
    return {
        "id": f"{scenario_id}_yt_{ordinal:02d}",
        "scenario_id": scenario_id,
        "text": normalize_line(str(entry["grounded_text"])),
        "speech_act": str(entry["speech_act"]),
        "emotion": str(entry["emotion"]),
        "evidence_ids": [item_evidence_id],
        "provenance": {
            "source_type": "corpus_grounded",
            "source_id": "youtube_caption_research_v1",
            "rights": "project_owned",
            "review_status": "automated_quality_gate_required",
            "source_timestamp_seconds": entry["anchor_seconds"],
            "grounding": {
                "evidence_id": item_evidence_id,
                "video_id": entry["video_id"],
                "source_url": entry["source_url"],
                "title": entry.get("title", ""),
                "channel": entry.get("channel", ""),
                "tier": entry["tier"],
                "speaker_role": entry.get("speaker_role", ""),
                "observed_exchange": entry["observed_exchange"],
                "grounded_turn_index": entry["grounded_turn_index"],
                "verification": entry.get("verification", {}),
                "rights_note": (
                    "Normalized project-owned line derived from research captions; "
                    "the source clip stays research_pending and is not shipped."
                ),
            },
        },
    }


def run(evidence_path: Path, audit_path: Path) -> int:
    evidence = load_json(evidence_path)
    scenarios = load_scenarios()
    taken_texts, _ = existing_pattern_texts()
    patterns: list[dict] = []
    skipped: list[dict] = []
    ordinals: dict[str, int] = {}
    for entry in evidence.get("exchanges", []):
        reason = validate_entry(entry, scenarios)
        scenario_id = str(entry.get("scenario_id", "")).strip().lower()
        text = normalize_line(str(entry.get("grounded_text", "")))
        if not reason and text.casefold() in taken_texts:
            reason = "duplicate_of_existing_pattern"
        if reason:
            skipped.append({"scenario_id": scenario_id, "video_id": entry.get("video_id", ""), "reason": reason})
            continue
        ordinals[scenario_id] = ordinals.get(scenario_id, 0) + 1
        pattern = build_pattern(entry, ordinals[scenario_id])
        patterns.append(pattern)
        taken_texts.add(text.casefold())
    write_json(PATTERN_DIR / OUTPUT_NAME, {"schema_version": 1, "patterns": patterns})
    per_scenario: dict[str, list[str]] = {}
    for pattern in patterns:
        per_scenario.setdefault(pattern["scenario_id"], []).append(pattern["id"])
    for scenario_id, scenario in scenarios.items():
        data = scenario["data"]
        current = [
            str(item).strip()
            for item in data.get("response_pattern_ids", [])
            if str(item).strip() and not GROUNDED_ID_RE.search(str(item))
        ]
        data["response_pattern_ids"] = current + per_scenario.get(scenario_id, [])
        provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
        provenance["corpus_grounded"] = {
            "pattern_count": len(per_scenario.get(scenario_id, [])),
            "evidence_file": "speech_service/grounding_evidence.json",
            "note": (
                "Observed American exchanges from the curated research corpus; lines are "
                "normalized and project-owned, source clips remain research_pending."
                if per_scenario.get(scenario_id)
                else "No screened natural exchange available for this scenario yet."
            ),
        }
        if per_scenario.get(scenario_id) and str(provenance.get("status", "")) == "provisional_source_first_pending":
            provenance["status"] = "corpus_grounded_provisional"
        data["provenance"] = provenance
        write_json(scenario["path"], data)
    write_json(audit_path, {
        "schema_version": 1,
        "evidence_file": str(evidence_path),
        "accepted": len(patterns),
        "skipped": skipped,
        "exclusions": evidence.get("exclusions", []),
        "per_scenario": {key: len(value) for key, value in sorted(per_scenario.items())},
    })
    print(f"grounded patterns: {len(patterns)}")
    for key in sorted(per_scenario):
        print(f"  {key}: +{len(per_scenario[key])}")
    for item in skipped:
        print(f"  SKIPPED {item['scenario_id']} {item['video_id']}: {item['reason']}")
    if skipped:
        print("curated evidence contained invalid entries; fix grounding_evidence.json")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    run_parser.add_argument("--audit", type=Path, default=AUDIT_PATH)
    args = parser.parse_args()
    if args.command == "run":
        return run(args.evidence.resolve(), args.audit.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
