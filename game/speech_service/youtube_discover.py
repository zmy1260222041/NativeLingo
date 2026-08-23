"""Find and rank native-English YouTube research candidates.

Local screening needs only already-downloaded ``*.info.json`` files. Live
search is optional and uses yt-dlp when installed. Nothing here promotes a
source into Godot or sets ``native_speaker_verified``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from corpus_pipeline import load_queries, write_json  # noqa: E402
from native_speaker_screener import (  # noqa: E402
    compact_video_info,
    rank_screens,
    screen_directory,
    screen_video,
    summarize,
)
from scenario_search import planned_queries, score_caption_file, search_queries  # noqa: E402


RAW_CAPTIONS = _SERVICE_DIR / "raw_captions"
CORPUS_WORK = _SERVICE_DIR / "corpus_work"
SEARCH_CAPTIONS = CORPUS_WORK / "search_captions"
DEFAULT_REPORT = CORPUS_WORK / "native_speaker_screen.json"
DEFAULT_SEARCH_LIMIT = 6
MAX_CAPTION_CHECKS = 30


def _yt_dlp_command() -> list[str] | None:
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return None
    return [sys.executable, "-m", "yt_dlp"]


def fetch_search_metadata(query: str, limit: int) -> list[dict]:
    command = _yt_dlp_command()
    if command is None:
        raise RuntimeError(
            "yt-dlp is not installed. Local screening still works. "
            "Install with: .venv/bin/pip install yt-dlp"
        )
    completed = subprocess.run(
        [
            *command,
            "--skip-download",
            "--dump-json",
            "--no-warnings",
            "--ignore-no-formats-error",
            "--playlist-end",
            str(limit),
            f"ytsearch{limit}:{query}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not completed.stdout.strip():
        raise RuntimeError(completed.stderr.strip() or "yt-dlp search failed")
    results: list[dict] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(compact_video_info(json.loads(line)))
        except json.JSONDecodeError:
            continue
    return results


def fetch_auto_captions(video_id: str, dest_dir: Path = SEARCH_CAPTIONS) -> Path | None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(dest_dir.glob(f"{video_id}*.vtt"))
    if existing:
        return existing[0]
    command = _yt_dlp_command()
    if command is None:
        return None
    completed = subprocess.run(
        [
            *command,
            "--skip-download",
            "--write-auto-sub",
            "--sub-langs", "en.*,en",
            "--sub-format", "vtt",
            "--convert-subs", "vtt",
            "--no-warnings",
            "-o", str(dest_dir / "%(id)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    found = sorted(dest_dir.glob(f"{video_id}*.vtt"))
    if found:
        return found[0]
    if completed.returncode != 0:
        return None
    return None


def attach_dialogue_fit(result: dict) -> dict:
    video_id = str(result.get("video_id") or "")
    hints = result.get("scenario_hints") or []
    scenario_id = hints[0] if hints else ""
    if not video_id or not scenario_id:
        result["dialogue_fit"] = False
        return result
    caption = fetch_auto_captions(video_id)
    if caption is None:
        result["dialogue_fit"] = False
        result["dialogue_fit_reason"] = "captions_unavailable"
        return result
    scored = score_caption_file(caption, scenario_id)
    result["dialogue_fit"] = bool(scored.get("dialogue_fit"))
    result["dialogue_exchange_count"] = scored.get("exchange_count", 0)
    result["best_exchange"] = scored.get("best_exchange")
    result["caption_path"] = str(caption)
    return result


def discover_search(limit: int = DEFAULT_SEARCH_LIMIT, families_per_scenario: int = 4) -> list[dict]:
    seen: set[str] = set()
    screens: list[dict] = []
    for item in planned_queries(families_per_scenario):
        scenario_id = item["scenario_id"]
        query = item["query"]
        for info in fetch_search_metadata(query, limit):
            video_id = str(info.get("id") or "")
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            result = screen_video(info)
            if scenario_id not in result["scenario_hints"]:
                result["scenario_hints"] = [scenario_id, *result["scenario_hints"]]
            result["search_query"] = query
            result["search_family"] = item.get("family", "")
            screens.append(result)
    caption_checks = 0
    for result in screens:
        if result.get("verdict") == "reject":
            result["dialogue_fit"] = False
            continue
        if caption_checks >= MAX_CAPTION_CHECKS:
            result["dialogue_fit"] = False
            result["dialogue_fit_reason"] = "caption_budget_exhausted"
            continue
        attach_dialogue_fit(result)
        caption_checks += 1
    ranked = rank_screens(screens)
    return sorted(
        ranked,
        key=lambda item: (
            0 if item.get("dialogue_fit") else 1,
            0 if item.get("verdict") == "candidate" else 1 if item.get("verdict") == "pending" else 2,
            -int(item.get("host_native_score") or 0),
            str(item.get("channel") or ""),
        ),
    )


def research_stubs(results: list[dict]) -> dict:
    sources = []
    for item in results:
        if item.get("verdict") != "candidate":
            continue
        hints = item.get("scenario_hints") or list(load_queries())
        sources.append({
            "source_id": f"youtube-{item['video_id']}",
            "source_url": item.get("url", ""),
            "transcript_path": "",
            "rights": "research_pending",
            "research_only": True,
            "source_title": item.get("title", ""),
            "source_description": "",
            "channel": item.get("channel", ""),
            "source_kind": (
                "field_news_interview"
                if item.get("native_scope") == "channel_org"
                else "on_location_personal_vlog"
            ),
            "native_speaker_verified": False,
            "native_speaker_evidence": item.get("native_speaker_evidence", ""),
            "native_speaker_screen": {
                "verdict": item.get("verdict"),
                "native_scope": item.get("native_scope"),
                "host_native_score": item.get("host_native_score"),
                "response_speaker_status": item.get("response_speaker_status"),
                "can_auto_verify": False,
                "evidence": item.get("evidence", []),
                "reasons": item.get("reasons", []),
            },
            "scenario_ids": hints,
        })
    return {
        "schema_version": 2,
        "screening_policy": (
            "Automatic native-speaker discovery only ranks research candidates. "
            "native_speaker_verified stays false until an editor independently "
            "confirms the response speaker."
        ),
        "sources": sources,
    }


def build_report(results: list[dict], mode: str) -> dict:
    return {
        "schema_version": 1,
        "mode": mode,
        "summary": summarize(results),
        "results": results,
    }


def format_table(results: list[dict]) -> str:
    lines = [
        f"{'verdict':<10} {'dlg':<4} {'score':>5} {'scope':<16} {'channel':<24} title",
        "-" * 100,
    ]
    for item in results:
        lines.append(
            f"{item.get('verdict', ''):<10} "
            f"{'yes' if item.get('dialogue_fit') else 'no':<4} "
            f"{int(item.get('host_native_score') or 0):>5} "
            f"{str(item.get('native_scope') or ''):<16} "
            f"{str(item.get('channel') or '')[:24]:<24} "
            f"{item.get('title', '')}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    screen = sub.add_parser("screen", help="Score local yt-dlp info.json files")
    screen.add_argument("--input", type=Path, default=RAW_CAPTIONS)
    screen.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    discover = sub.add_parser("search", help="Search YouTube with yt-dlp and rank hits")
    discover.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    discover.add_argument("--families", type=int, default=4)
    discover.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.command == "screen":
        results = screen_directory(args.input.resolve())
        report = build_report(results, "local_info_json")
    else:
        results = discover_search(args.limit, args.families)
        report = build_report(results, "youtube_search")
    write_json(args.output, report)
    stubs = research_stubs(results)
    stub_path = args.output.with_name(args.output.stem + "_research_stubs.json")
    write_json(stub_path, stubs)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print()
    print(format_table(results))
    print(f"\nWrote {args.output}")
    print(f"Wrote {stub_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
