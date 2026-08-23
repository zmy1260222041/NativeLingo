"""Plan US on-location dialogue searches and score caption exchanges.

YouTube topic search returns reviews and monologues. This module asks for
American service talk first, then checks captions for an adjacent request
and response. It does not mark native_speaker_verified.

Filmot transcript search is a separate path: spoken phrases stay in the
query, and English-teaching titles are excluded with the title= field.
Minus terms in the transcript query are not used for teaching words,
because those words often appear only in the title.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from corpus_pipeline import QUERY_FILE, parse_captions, segment_turns  # noqa: E402


DEFAULT_EXCLUDES = (
    "learn english",
    "ESL",
    "roleplay",
    "english lesson",
    "conversation practice",
    "UK",
    "London",
    "British",
    "travel tip",
    "explained",
    "hotel tour",
    "entire menu",
)
DEFAULT_TITLE_EXCLUDES = (
    "learn",
    "lesson",
    "dialogue",
    "ESL",
    "frases",
    "ingles",
    "inglés",
    "shadowing",
    "pronunciation",
    "learn english",
    "english conversation",
    "english speaking",
    "english lesson",
    "conversation practice",
    "speak english",
)
LANGUAGE_TEACHING_TITLE_MARKERS = (
    "learn english",
    "english lesson",
    "english conversation",
    "conversation practice",
    "speaking practice",
    "listening practice",
    "daily dialogue",
    "dialogue practice",
    "dialogue collection",
    "dialogue one",
    "dialogue 1",
    "repeat after",
    "shadowing",
    "beginner english",
    "speak english",
    "english speaking",
    "english for daily",
    "frases",
    "ingles",
    "inglés",
    "aprender",
    "pronunciación",
    "easy english",
    "basic english",
    "english singsing",
    "boston english",
    "ingilizce",
    "kelime öğrenme",
)
LANGUAGE_TEACHING_CHANNEL_MARKERS = (
    "learn english",
    "english lesson",
    "english speaking",
    "easy english",
    "basic english",
    "best teacher",
    "english singsing",
    "boston english",
    "speak english",
)
LANGUAGE_TEACHING_SNIPPET_MARKERS = (
    "dialogue one",
    "dialogue 1",
    "dialogue two",
    "dialogue 2",
    "repeat after",
    "listen and repeat",
    "repeat after me",
)
_TEACHING_CHANNEL_WORDS = (
    "learn",
    "lesson",
    "speak",
    "teacher",
    "esl",
    "singsing",
    "practice",
    "centre",
    "center",
    "fluently",
)
_WORD_RE = re.compile(r"[a-z']+")
FILMOT_SEARCH_BASE = "https://filmot.com/search"
REQUEST_CUES = (
    "can i get",
    "can i have",
    "could i have",
    "excuse me",
    "i'll take",
    "i will take",
    "i need",
    "i want",
    "is there",
    "where can i",
    "do you have",
    "can we",
    "may i",
)
RESPONSE_CUES = (
    "sure",
    "yeah",
    "yep",
    "you bet",
    "of course",
    "no problem",
    "for here",
    "to go",
    "how many",
    "how much",
    "right over",
    "come on in",
    "come in",
    "absolutely",
    "here you go",
    "i can",
)
def load_search_spec() -> dict:
    return json.loads(QUERY_FILE.read_text(encoding="utf-8"))


def _exclude_suffix(excludes: list[str]) -> str:
    return " ".join(f'-"{term}"' for term in excludes if term)


def _minus_terms(terms: list[str] | tuple[str, ...]) -> str:
    parts: list[str] = []
    for term in terms:
        cleaned = str(term or "").strip()
        if not cleaned:
            continue
        if " " in cleaned:
            parts.append(f'-"{cleaned}"')
        else:
            parts.append(f"-{cleaned}")
    return " ".join(parts)


def title_exclude_terms(scenario: dict | None = None) -> list[str]:
    spec = load_search_spec()
    extra = spec.get("native_speaker_search") or {}
    terms = list(extra.get("title_exclude_terms") or DEFAULT_TITLE_EXCLUDES)
    if scenario:
        for term in scenario.get("title_exclude_terms") or []:
            if term not in terms:
                terms.append(term)
    return terms


def filmot_title_query(scenario: dict | None = None) -> str:
    return _minus_terms(title_exclude_terms(scenario))


def filmot_search_url(query: str, title_query: str = "", page: int = 1) -> str:
    path = quote(query.strip(), safe="")
    url = f"{FILMOT_SEARCH_BASE}/{path}/{page}?lang=en&country=217&gridView=1"
    if title_query.strip():
        url += f"&title={quote(title_query.strip(), safe='')}"
    return url


def planned_queries(limit_per_scenario: int = 4) -> list[dict]:
    spec = load_search_spec()
    extra = spec.get("native_speaker_search") or {}
    excludes = list(extra.get("exclude_terms") or DEFAULT_EXCLUDES)
    suffix = _exclude_suffix(excludes)
    planned: list[dict] = []
    for item in spec.get("queries") or []:
        scenario_id = str(item.get("scenario_id") or "")
        if not scenario_id:
            continue
        families = [entry for entry in (item.get("query_families") or []) if isinstance(entry, dict)]
        pairs = [
            (str(entry.get("family") or "custom"), str(entry.get("query") or "").strip())
            for entry in families
            if str(entry.get("query") or "").strip()
        ]
        if not pairs:
            pairs = [("legacy", str(term).strip()) for term in (item.get("search_terms") or []) if str(term).strip()]
        for family, query in pairs[:limit_per_scenario]:
            planned.append({
                "scenario_id": scenario_id,
                "family": family,
                "query": f"{query} {suffix}".strip(),
            })
    return planned


def planned_filmot_queries(limit_per_scenario: int = 3) -> list[dict]:
    spec = load_search_spec()
    planned: list[dict] = []
    for item in spec.get("queries") or []:
        scenario_id = str(item.get("scenario_id") or "")
        if not scenario_id:
            continue
        title_query = filmot_title_query(item)
        families = [entry for entry in (item.get("query_families") or []) if isinstance(entry, dict)]
        queries: list[tuple[str, str]] = []
        for entry in families:
            filmot_query = str(entry.get("filmot_query") or "").strip()
            if filmot_query:
                queries.append((str(entry.get("family") or "custom"), filmot_query))
        if not queries:
            for entry in families:
                query = str(entry.get("query") or "").strip()
                if query:
                    queries.append((str(entry.get("family") or "custom"), query))
        for family, query in queries[:limit_per_scenario]:
            planned.append({
                "scenario_id": scenario_id,
                "family": family,
                "query": query,
                "title_query": title_query,
                "filmot_url": filmot_search_url(query, title_query),
            })
    return planned


def _triple_repeated_phrase(text: str) -> str:
    words = _WORD_RE.findall(text.casefold())
    skip = {"the", "a", "an", "and", "to", "of", "in", "it", "is"}
    for length in (3, 4, 5):
        span = length * 3
        for index in range(0, len(words) - span + 1):
            first = words[index : index + length]
            if all(word in skip for word in first):
                continue
            if (
                first
                == words[index + length : index + length * 2]
                == words[index + length * 2 : index + span]
            ):
                return " ".join(first)
    return ""


def _fold(text: str) -> str:
    return text.casefold().replace("i̇", "i").replace("ı", "i")


def language_teaching_reason(text: str = "", title: str = "", channel: str = "") -> str:
    if "sort by filters" in _fold(f"{title} {text}"):
        return "card:filmot_chrome"
    title_l = _fold(title)
    channel_l = _fold(channel).replace("new england", " ")
    blob = _fold(" ".join(part for part in (title, channel, text) if part))
    blob = blob.replace("new england", " ")
    head = blob[:180]
    for marker in LANGUAGE_TEACHING_TITLE_MARKERS:
        if marker in title_l or marker in head:
            return f"title_or_card:{marker}"
    for marker in LANGUAGE_TEACHING_CHANNEL_MARKERS:
        if marker in channel_l or marker in head:
            return f"channel:{marker}"
    if re.search(r"\benglish\b", channel_l) or re.search(r"\benglish\b", head):
        return "channel:english"
    if re.search(r"\besl\b", blob) or re.search(r"\ba[12]\s*[-–]\s*b?[12]\b", blob):
        return "card:esl_or_cefr_level"
    for marker in LANGUAGE_TEACHING_SNIPPET_MARKERS:
        if marker in blob:
            return f"snippet:{marker}"
    repeated = _triple_repeated_phrase(blob)
    if repeated:
        return f"snippet:triple_phrase:{repeated}"
    return ""


def is_language_teaching(text: str = "", title: str = "", channel: str = "") -> bool:
    return bool(language_teaching_reason(text, title, channel))


def filter_language_teaching(hits: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    rejected: list[dict] = []
    for hit in hits:
        reason = language_teaching_reason(
            text=str(hit.get("text") or ""),
            title=str(hit.get("title") or ""),
            channel=str(hit.get("channel") or ""),
        )
        marked = dict(hit)
        if reason:
            marked["language_teaching"] = True
            marked["language_teaching_reason"] = reason
            rejected.append(marked)
        else:
            marked["language_teaching"] = False
            kept.append(marked)
    return kept, rejected


def search_queries(limit_per_scenario: int = 4) -> list[tuple[str, str]]:
    return [(item["scenario_id"], item["query"]) for item in planned_queries(limit_per_scenario)]


def _has_any(text: str, phrases: list[str] | tuple[str, ...]) -> str:
    lowered = text.casefold()
    for phrase in phrases:
        if phrase.casefold() in lowered:
            return phrase
    return ""


def score_caption_dialogue(turns: list[dict], scenario: dict) -> dict:
    required = [str(phrase) for phrase in scenario.get("required_phrases_any") or []]
    request_cues = list(scenario.get("request_cues") or REQUEST_CUES)
    response_cues = list(scenario.get("response_cues") or RESPONSE_CUES)
    windows: list[dict] = []
    for index, turn in enumerate(turns):
        request_text = str(turn.get("text") or "")
        request_hit = _has_any(request_text, request_cues) or ("?" in request_text)
        topic_hit = _has_any(request_text, required)
        if not request_hit or not topic_hit:
            continue
        for follow in turns[index + 1 : index + 3]:
            gap = float(follow.get("start") or 0) - float(turn.get("end") or 0)
            if gap > 8:
                break
            response_text = str(follow.get("text") or "")
            response_hit = _has_any(response_text, response_cues)
            same_speaker = (
                turn.get("speaker") not in {None, "", "unknown"}
                and turn.get("speaker") == follow.get("speaker")
            )
            if not response_hit or same_speaker:
                continue
            windows.append({
                "request_text": request_text,
                "response_text": response_text,
                "request_start_seconds": turn.get("start"),
                "response_start_seconds": follow.get("start"),
                "request_cue": request_hit if isinstance(request_hit, str) else "question",
                "response_cue": response_hit,
                "topic_phrase": topic_hit,
            })
            break
    return {
        "dialogue_fit": bool(windows),
        "exchange_count": len(windows),
        "best_exchange": windows[0] if windows else None,
    }


def score_caption_file(path: Path, scenario_id: str) -> dict:
    spec = load_queries_by_id()
    scenario = spec.get(scenario_id) or {}
    turns = segment_turns(parse_captions(path))
    result = score_caption_dialogue(turns, scenario)
    result["scenario_id"] = scenario_id
    result["caption_path"] = str(path)
    return result


def load_queries_by_id() -> dict[str, dict]:
    spec = load_search_spec()
    return {str(item["scenario_id"]): item for item in spec.get("queries") or [] if item.get("scenario_id")}
