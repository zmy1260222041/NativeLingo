"""Rank YouTube videos as native-English research candidates.

The target variety is American English. British, Irish, Australian, New
Zealand, and Canadian sources stay out of ``candidate``. A US on-location
vlog can qualify without being a news org. This module never marks
``native_speaker_verified``. Host-channel evidence is not evidence about a
second speaker in the clip.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from corpus_pipeline import (  # noqa: E402
    NON_DIALOGUE_TITLE_MARKERS,
    NON_REAL_LIFE_MARKERS,
    load_queries,
    matching_scenarios,
)


SCREENER_VERSION = 3
CANDIDATE_MIN_SCORE = 40
PENDING_MIN_SCORE = 20
TARGET_VARIETY = "american"
VLOG_CATEGORIES = {"people & blogs", "travel & events", "entertainment"}

US_NEWS = (
    "abc news",
    "abc7",
    "associated press",
    "cbs news",
    "denver7",
    "good morning america",
    "kshb",
    "nbc news",
    "npr",
    "pbs",
    "wpri",
)
NON_US_NEWS = (
    "bbc",
    "bbc news",
    "cbc news",
    "channel 4 news",
    "channel 9",
    "citynews",
    "ctv news",
    "global news",
    "itv news",
    "rte news",
    "sbs news",
    "sky news",
    "the guardian",
    "tvnz",
    "7 news",
    "7news",
    "9 news",
    "9news",
)
US_PLACES = (
    "united states",
    "america",
    "u.s.",
    "texas",
    "california",
    "illinois",
    "oregon",
    "nebraska",
    "florida",
    "ohio",
    "new york",
    "nyc",
    "chicago",
    "boston",
    "seattle",
    "denver",
    "hawaii",
)
NON_US_PLACES = (
    "england",
    "scotland",
    "wales",
    "ireland",
    "britain",
    "uk",
    "united kingdom",
    "canada",
    "australia",
    "new zealand",
    "london",
    "manchester",
    "sydney",
    "melbourne",
    "toronto",
    "vancouver",
    "dublin",
    "auckland",
)
L2_SELF_ID_MARKERS = (
    "english is not my first language",
    "english isn't my first language",
    "non-native speaker",
    "non native speaker",
    "as an esl",
    "learn english with me",
    "i'm from china",
    "i am chinese",
    "native chinese",
    "as a chinese",
    "as a korean",
    "as a japanese speaker",
    "my second language",
    "english learner",
)
EXPAT_MARKERS = ("expat", "expats", "digital nomad", "retired abroad")
NON_LATIN_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0600-\u06ff]")
US_CALLSIGN_RE = re.compile(r"\b[KW][A-Z]{2,3}\b")
US_BIO_RES = (
    re.compile(
        r"\bborn in (?:the )?(united states|america|usa|texas|california|illinois|"
        r"oregon|nebraska|florida|ohio|new york|chicago|boston|seattle|denver|hawaii)\b",
        re.I,
    ),
    re.compile(r"\b(?:i(?:'m| am)|we(?:'re| are)) american\b", re.I),
    re.compile(
        r"\bgrew up in (?:the )?(united states|america|usa|texas|california|illinois|"
        r"oregon|nebraska|florida|ohio|new york|chicago|boston|seattle|denver|hawaii)\b",
        re.I,
    ),
    re.compile(
        r"\bfrom (texas|california|illinois|oregon|nebraska|florida|ohio|new york|"
        r"chicago|boston|seattle|denver|hawaii)\b",
        re.I,
    ),
)
NON_US_BIO_RES = (
    re.compile(
        r"\bborn in (?:the )?(england|scotland|wales|ireland|australia|new zealand|"
        r"canada|britain|uk|united kingdom|london|manchester|sydney|melbourne|"
        r"toronto|vancouver|dublin|auckland)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:i(?:'m| am)|we(?:'re| are)) (british|english|australian|canadian|"
        r"irish|kiwi|scottish|welsh)\b",
        re.I,
    ),
)
FILENAME_SCENARIOS = (
    ("food", "food_ask_bread"),
    ("water", "water_ask_clean_water"),
    ("warmth", "warmth_ask_blanket"),
    ("shelter", "shelter_ask_sit_inside"),
    ("belonging", "belonging_small_talk_waiting_line"),
)


def compact_video_info(raw: dict) -> dict:
    autos = raw.get("automatic_captions") or {}
    manuals = raw.get("subtitles") or {}
    tags = raw.get("tags") or []
    categories = raw.get("categories") or []
    return {
        "id": raw.get("id") or "",
        "title": raw.get("title") or "",
        "channel": raw.get("channel") or raw.get("uploader") or "",
        "uploader": raw.get("uploader") or "",
        "description": raw.get("description") or "",
        "tags": [str(tag) for tag in tags] if isinstance(tags, list) else [],
        "categories": [str(item) for item in categories] if isinstance(categories, list) else [],
        "language": raw.get("language") or "",
        "location": raw.get("location") or "",
        "channel_is_verified": bool(raw.get("channel_is_verified")),
        "webpage_url": raw.get("webpage_url") or raw.get("original_url") or "",
        "duration": raw.get("duration"),
        "automatic_caption_langs": sorted(str(key) for key in autos),
        "subtitle_langs": sorted(str(key) for key in manuals),
    }


def load_info_json(path: Path) -> dict:
    return compact_video_info(json.loads(path.read_text(encoding="utf-8")))


def original_caption_languages(info: dict) -> list[str]:
    langs = info.get("automatic_caption_langs") or info.get("automatic_captions") or []
    if isinstance(langs, dict):
        langs = langs.keys()
    return sorted({str(lang).lower() for lang in langs if "orig" in str(lang).lower()})


def _is_english_orig(lang: str) -> bool:
    value = lang.lower().replace("_", "-")
    return value == "en-orig" or (value.startswith("en-") and value.endswith("-orig"))


def searchable_text(info: dict) -> str:
    parts = [
        info.get("title", ""),
        info.get("channel", ""),
        info.get("uploader", ""),
        info.get("description", ""),
        info.get("location", ""),
        " ".join(info.get("tags") or []),
        " ".join(info.get("categories") or []),
    ]
    return " ".join(str(part) for part in parts).casefold()


def _contains_any(text: str, markers: tuple[str, ...] | list[str]) -> str:
    for marker in markers:
        if marker.casefold() in text:
            return marker
    return ""


def _channel_blob(info: dict) -> str:
    return f"{info.get('channel', '')} {info.get('uploader', '')} {info.get('title', '')}".casefold()


def us_news_org_match(info: dict) -> str:
    blob = _channel_blob(info)
    for name in US_NEWS:
        if name in blob:
            return name
    channel = str(info.get("channel", ""))
    categories = [item.casefold() for item in info.get("categories") or []]
    if US_CALLSIGN_RE.search(channel) and (
        "news" in channel.casefold() or "news & politics" in categories
    ):
        return channel
    return ""


def non_us_news_org_match(info: dict) -> str:
    blob = _channel_blob(info)
    for name in NON_US_NEWS:
        if name in blob:
            return name
    return ""


def us_biography_match(text: str) -> str:
    for pattern in US_BIO_RES:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def non_us_biography_match(text: str) -> str:
    for pattern in NON_US_BIO_RES:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def _place_match(info: dict, places: tuple[str, ...]) -> str:
    blob = searchable_text(info)
    for place in places:
        if re.search(rf"\b{re.escape(place)}\b", blob):
            return place
    return ""


def us_place_match(info: dict) -> str:
    return _place_match(info, US_PLACES)


def non_us_place_match(info: dict) -> str:
    return _place_match(info, NON_US_PLACES)


def scenario_hints(info: dict, path: Path | None = None) -> list[str]:
    queries = load_queries()
    text = f"{info.get('title', '')} {info.get('description', '')}"
    hints = matching_scenarios(text, queries, list(queries))
    if path is not None:
        name = path.name.casefold()
        for token, scenario_id in FILENAME_SCENARIOS:
            if token in name and scenario_id not in hints:
                hints.append(scenario_id)
    return hints


def screen_video(info: dict, source_path: str | Path | None = None) -> dict:
    compact = compact_video_info(info) if "automatic_captions" in info else dict(info)
    path = Path(source_path) if source_path else None
    text = searchable_text(compact)
    title = str(compact.get("title", "")).casefold()
    identity_text = " ".join(
        str(compact.get(field, ""))
        for field in ("title", "channel", "uploader", "description")
    ).casefold()
    orig_langs = original_caption_languages(compact)
    english_orig = [lang for lang in orig_langs if _is_english_orig(lang)]
    non_english_orig = [lang for lang in orig_langs if not _is_english_orig(lang)]
    reasons: list[str] = []
    evidence: list[str] = []
    score = 0
    verdict = "pending"
    native_scope = "unknown_speakers"
    response_status = "not_evidenced"

    teaching = _contains_any(identity_text, NON_REAL_LIFE_MARKERS)
    if teaching:
        reasons.append(f"language_teaching_or_scripted:{teaching}")
    advice = _contains_any(title, NON_DIALOGUE_TITLE_MARKERS)
    if advice:
        reasons.append(f"narrated_advice_or_review:{advice}")
    l2_self = _contains_any(text, L2_SELF_ID_MARKERS)
    if l2_self:
        reasons.append(f"l2_self_identification:{l2_self}")
    if NON_LATIN_RE.search(f"{compact.get('title', '')} {compact.get('channel', '')}"):
        reasons.append("non_latin_title_or_channel")
    if non_english_orig:
        reasons.append(f"non_english_original_audio:{','.join(non_english_orig)}")
    if any(marker in text for marker in EXPAT_MARKERS) and (
        advice or "how to" in title or "the truth about" in title or "what you need to know" in title
    ):
        reasons.append("expat_advice_monologue")

    if reasons:
        return _result(
            compact,
            path,
            verdict="reject",
            native_scope="none",
            score=0,
            response_status="unknown",
            reasons=reasons,
            evidence=evidence,
            orig_langs=orig_langs,
        )

    if english_orig and not non_english_orig:
        score += 20
        evidence.append(f"original_captions:{','.join(english_orig)}")
    elif not orig_langs:
        reasons.append("original_caption_language_missing")

    identity = f"{compact.get('description', '')} {compact.get('title', '')}"
    us_news = us_news_org_match(compact)
    non_us_news = non_us_news_org_match(compact)
    us_bio = us_biography_match(identity)
    non_us_bio = non_us_biography_match(identity)
    us_place = us_place_match(compact)
    non_us_place = non_us_place_match(compact)
    if non_us_news or non_us_bio or (non_us_place and not us_news and not us_bio and not us_place):
        reasons.append("non_american_english_variety")
        return _result(
            compact,
            path,
            verdict="pending",
            native_scope="host_only" if (non_us_news or non_us_bio or non_us_place) else "unknown_speakers",
            score=20,
            response_status="not_evidenced",
            reasons=reasons,
            evidence=[
                item
                for item in (
                    f"non_us_news_org:{non_us_news}" if non_us_news else "",
                    f"non_us_self_identification:{non_us_bio}" if non_us_bio else "",
                    f"non_us_place:{non_us_place}" if non_us_place else "",
                )
                if item
            ],
            orig_langs=orig_langs,
        )
    if us_news:
        score += 40
        native_scope = "channel_org"
        evidence.append(f"us_news_org:{us_news}")
    if us_bio:
        score += 40
        if native_scope == "unknown_speakers":
            native_scope = "host_only"
        evidence.append(f"us_self_identification:{us_bio}")
    if us_place:
        score += 25
        evidence.append(f"us_place:{us_place}")
        if native_scope == "unknown_speakers":
            native_scope = "host_only"
    categories = [item.casefold() for item in compact.get("categories") or []]
    personal_vlog = any(category in VLOG_CATEGORIES for category in categories)
    if personal_vlog and (us_place or us_bio) and not us_news:
        score += 10
        evidence.append("us_personal_vlog")
    if compact.get("channel_is_verified") and "news & politics" in categories and us_news:
        score += 15
        evidence.append("verified_us_news_channel")

    if _contains_any(" ".join(compact.get("tags") or []), ("learn english", "esl", "english lesson")):
        score -= 5
        reasons.append("learn_english_tag")
    if any(marker in text for marker in EXPAT_MARKERS) and not us_news:
        score -= 25
        reasons.append("expat_channel_without_news_org")
    if any(lang.lower().startswith("ja") for lang in compact.get("subtitle_langs") or []) and not us_news:
        score -= 10
        reasons.append("japanese_manual_subtitles")

    score = max(0, min(100, score))
    if score >= CANDIDATE_MIN_SCORE:
        verdict = "candidate"
    elif score < PENDING_MIN_SCORE:
        reasons.append("insufficient_native_evidence")
        native_scope = "unknown_speakers"
    if native_scope in {"host_only", "channel_org"}:
        response_status = "not_evidenced"
    return _result(
        compact,
        path,
        verdict=verdict,
        native_scope=native_scope,
        score=score,
        response_status=response_status,
        reasons=reasons,
        evidence=evidence,
        orig_langs=orig_langs,
    )


def _result(
    info: dict,
    path: Path | None,
    *,
    verdict: str,
    native_scope: str,
    score: int,
    response_status: str,
    reasons: list[str],
    evidence: list[str],
    orig_langs: list[str],
) -> dict:
    video_id = str(info.get("id") or (path.stem if path else "")).strip()
    url = str(info.get("webpage_url") or "")
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "screener_version": SCREENER_VERSION,
        "video_id": video_id,
        "title": info.get("title", ""),
        "channel": info.get("channel", ""),
        "url": url,
        "source_path": str(path) if path else "",
        "verdict": verdict,
        "native_scope": native_scope,
        "host_native_score": score,
        "response_speaker_status": response_status,
        "can_auto_verify": False,
        "reasons": reasons,
        "evidence": evidence,
        "original_caption_langs": orig_langs,
        "scenario_hints": scenario_hints(info, path),
        "native_speaker_verified": False,
        "native_speaker_evidence": "; ".join(evidence) if evidence else "",
    }


def screen_info_json(path: Path) -> dict:
    return screen_video(load_info_json(path), path)


def screen_directory(directory: Path) -> list[dict]:
    results = [screen_info_json(path) for path in sorted(directory.glob("*.info.json"))]
    return rank_screens(results)


def rank_screens(results: list[dict]) -> list[dict]:
    rank = {"candidate": 0, "pending": 1, "reject": 2}
    return sorted(
        results,
        key=lambda item: (
            rank.get(item.get("verdict"), 9),
            -int(item.get("host_native_score") or 0),
            str(item.get("channel") or ""),
            str(item.get("video_id") or ""),
        ),
    )


def summarize(results: list[dict]) -> dict:
    counts = {"candidate": 0, "pending": 0, "reject": 0}
    for item in results:
        verdict = str(item.get("verdict") or "")
        if verdict in counts:
            counts[verdict] += 1
    return {
        "screener_version": SCREENER_VERSION,
        "total": len(results),
        **counts,
        "auto_verified": 0,
        "note": (
            "candidate means the host looks like American English: a US news org, "
            "an American self-identification, or a US on-location vlog. British and "
            "other non-US inner-circle sources are kept pending. It never sets "
            "native_speaker_verified."
        ),
    }
