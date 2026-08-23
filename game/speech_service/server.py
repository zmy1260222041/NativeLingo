"""Offline localhost speech adapter for Stranger's voice-gated social intents.

The service now returns a graded expression verdict per utterance:

* ``delivery`` (0-100)  -- deterministic slot matching: did the meaning get
  across? Required slots drive the verdict; optional slots (politeness) only
  refine the band. Grammar is never checked (FR-22 / FR-28 body).
* ``pronunciation`` (0-100) -- reference-anchored SSL+DTW when the desktop
  scoring stack is importable in this interpreter; otherwise a Whisper
  acoustic-confidence proxy. The source is always reported and the proxy is
  never labelled as reference scoring.
* ``score`` = 0.5 * pronunciation + 0.5 * delivery; the reward band follows
  monotonically: >= 70 generous, 40-69 sparse, < 40 none (retry is free).

The service does not own or mutate game state; it only turns one WAV into a
verdict. It listens on 127.0.0.1 only.
"""
from __future__ import annotations

import base64
import contextlib
import csv
import hashlib
import json
import math
import os
import queue
import re
import time
import subprocess
import sys
import tempfile
import threading
import uuid
import urllib.error
import urllib.request
import wave
from collections import deque
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:  # keep the service importable (urllib fallback) in deployments without it
    import requests
except ImportError:  # pragma: no cover - depends on deployment env
    requests = None  # type: ignore[assignment]

HOST = "127.0.0.1"
PORT = 17831
MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "whisper-base.en"
REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = Path(__file__).resolve().parent / "reference_audio"
DIALOGUE_ROOT = REPO_ROOT / "game" / "data" / "dialogue"
DIALOGUE_SCENARIO_DIR = DIALOGUE_ROOT / "scenarios"
DIALOGUE_PROFILE_DIR = DIALOGUE_ROOT / "npc_profiles"
DIALOGUE_PATTERN_DIR = DIALOGUE_ROOT / "response_patterns"

_DIALOGUE_SCENARIOS: dict[str, dict] = {}
_DIALOGUE_PROFILES: dict[str, dict] = {}
_DIALOGUE_PATTERNS: dict[str, dict] = {}
_DYNAMIC_REPLIES: dict[str, dict] = {}


def _load_dialogue_assets() -> None:
    _DIALOGUE_SCENARIOS.clear()
    _DIALOGUE_PROFILES.clear()
    _DIALOGUE_PATTERNS.clear()
    for path in sorted(DIALOGUE_SCENARIO_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scenario_id = str(data.get("godot_scenario_id", "")).strip().lower()
        if scenario_id:
            _DIALOGUE_SCENARIOS[scenario_id] = data
    for path in sorted(DIALOGUE_PROFILE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        npc_id = str(data.get("npc_id", "")).strip().lower()
        if npc_id:
            _DIALOGUE_PROFILES[npc_id] = data
    for path in sorted(DIALOGUE_PATTERN_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for pattern in data.get("patterns", []) if isinstance(data, dict) else []:
            if isinstance(pattern, dict) and str(pattern.get("id", "")).strip():
                _DIALOGUE_PATTERNS[str(pattern["id"]).strip()] = pattern


_load_dialogue_assets()

# Reward bands are owned by the game (FR-28): monotonic, below-minimum costs
# nothing and can be retried immediately.
SCORE_GENEROUS_MIN = 70.0
SCORE_SPARSE_MIN = 40.0

# Whisper-confidence fallback calibration (documented, deliberate proxy).
_LOGP_FLOOR = -1.4
_LOGP_CEIL = 0.0
_NSP_FLOOR = 0.0
_NSP_CEIL = 0.8

INTENTS = {
    "mira": {
        "label": "greeting",
        "reference": "Hello Mira, it is good to meet you.",
        "slots": [
            {
                "key": "greeting",
                "required": True,
                "accept": [
                    "hello",
                    "hi",
                    "good morning",
                    "good evening",
                    "hey",
                    "morning",
                    "nice to meet you",
                    "friend",
                    "mira",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
    "tavi": {
        "label": "food request",
        "reference": "Can I have some food please?",
        "slots": [
            {
                "key": "request_act",
                "required": True,
                "accept": [
                    "want",
                    "need",
                    "can i",
                    "may i",
                    "could i",
                    "give me",
                    "please give",
                    "i would like",
                    "i'd like",
                    "do you have",
                    "some",
                ],
            },
            {
                "key": "food_object",
                "required": True,
                "accept": [
                    "food",
                    "something to eat",
                    "anything to eat",
                    "berries",
                    "duskberries",
                    "duskberry",
                    "fruit",
                    "meal",
                    "snack",
                    "eat",
                    "hungry",
                    "bread",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
    "vesh": {
        "label": "scrap request",
        "reference": "I need two alloy parts for the heater.",
        "slots": [
            {
                "key": "request_act",
                "required": True,
                "accept": [
                    "want",
                    "need",
                    "can i",
                    "may i",
                    "could i",
                    "give me",
                    "please give",
                    "i would like",
                    "i'd like",
                    "do you have",
                    "some",
                ],
            },
            {
                "key": "scrap_object",
                "required": True,
                "accept": [
                    "scrap",
                    "parts",
                    "part",
                    "alloy",
                    "metal",
                    "pieces",
                    "patches",
                    "patch",
                    "for the heater",
                    "heater",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
    "ori": {
        "label": "water request",
        "reference": "May I have some water please?",
        "slots": [
            {
                "key": "request_act",
                "required": True,
                "accept": [
                    "want",
                    "need",
                    "can i",
                    "may i",
                    "could i",
                    "give me",
                    "please give",
                    "i would like",
                    "i'd like",
                    "do you have",
                    "some",
                ],
            },
            {
                "key": "water_object",
                "required": True,
                "accept": [
                    "water",
                    "some water",
                    "a drink",
                    "drink",
                    "jug",
                    "canteen",
                    "something to drink",
                    "anything to drink",
                    "thirsty",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
    "rowan": {
        "label": "water delivery",
        "reference": "Here is water for you. Let me help you.",
        "slots": [
            {
                "key": "offer_act",
                "required": True,
                "accept": [
                    "here",
                    "take",
                    "help",
                    "i can help",
                    "let me",
                    "for you",
                    "brought",
                    "bring",
                ],
            },
            {
                "key": "water_object",
                "required": True,
                "accept": [
                    "water",
                    "some water",
                    "a drink",
                    "drink",
                    "jug",
                    "canteen",
                    "thirsty",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
}

# --------------------------------------------------------------------------- #
# NPC voice (FR-32): fixed line catalog for Qwen TTS. The local service only
# synthesizes server-known lines; it never accepts free text from the game.
# --------------------------------------------------------------------------- #

NPC_LINES = {
    "mira": {
        "word_practice_ask": "",
        "greeting": "Hey, little one. Come to the market. No need to be afraid.",
        "greet_reply": "Welcome, stranger.",
        "clarify": "Sorry? Say it again, little one.",
        "hint_food": "Tavi shares food with the hungry. Ask her in English.",
        "hint_heat": "Nights get cold. Vesh keeps the old alloy. Ask him in English.",
        "hint_rowan": "Rowan needs water today. Ask Ori for a canteen first.",
        "remembers": "You came yesterday. The stall still keeps your place.",
        "social_greeting": "Good morning. Did you sleep well?",
        "social_reply_food": "Of course. Take two portions.",
    },
    "rowan": {
        "word_practice_ask": "",
        "greeting": "You look tired. Find water and warmth first.",
        "clarify": "Hmm? What do you need?",
        "needs_water": "I cannot walk that far. Ask Ori for water first.",
        "remembers": "You brought water. I will not forget.",
        "thanks": "You came back. Thank you.",
        "social_reply_water": "I am thirsty too. Bring me water, please.",
        "social_ask_help": "I cannot walk far. Could you bring me water?",
    },
    "tavi": {
        "word_practice_ask": "",
        "greeting": "Hungry? Tell me once you are settled.",
        "clarify": "Sorry? I did not hear you. Try again.",
        "hint_food": "I can share food. Tell me in English.",
        "settled": "You have enough fruit. Go rest.",
        "reward": "Here you go. Eat well, little one.",
        "social_reply_greeting": "I slept. Are you hungry?",
        "social_ask_food": "Can I have some food, please?",
    },
    "vesh": {
        "word_practice_ask": "",
        "greeting": "Cold nights are coming. Ask me for alloy parts.",
        "clarify": "Sorry? Say it once more.",
        "hint_scrap": "The heater needs alloy parts. Ask me in English.",
        "settled": "You have the parts. Go to the furnace.",
        "reward": "Here are the alloy parts.",
        "social_ask_scrap": "The heater needs two alloy parts. Do you have any?",
    },
    "ori": {
        "word_practice_ask": "",
        "greeting": "I keep the water. Ask me when you need it.",
        "clarify": "Hmm? Say it again, please.",
        "hint_water": "I keep the reservoir. Ask me for water in English.",
        "settled": "The water is already with you. Go to Rowan.",
        "reward": "Here is your canteen of water.",
        "social_reply_scrap": "I have one. Ask Tavi for the other.",
        "social_ask_water": "I need a canteen of water.",
        "social_reply_help": "I will ask the little one to help.",
    },
}

QWEN_TTS_MODEL = os.environ.get("QWEN_TTS_MODEL", "qwen-audio-3.0-tts-plus")
QWEN_TTS_VOICE = os.environ.get("QWEN_TTS_VOICE", "")
## The dedicated deployment only answers on the WebSocket inference route; the
## OpenAI-compatible host in the CSV has no /audio/speech path (probed 404).
QWEN_TTS_WS_URL = os.environ.get("QWEN_TTS_WS_URL", "")
QWEN_TTS_API_KEY = os.environ.get("QWEN_TTS_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
## qwen-audio-3.0-tts-plus ships exactly two system voices (voice list doc):
## longanlingxin (female) and longanlufeng (male). Qwen3-TTS names such as
## "Cherry" are rejected with InvalidParameter by this model family.
NPC_TTS_VOICES = {
    "mira": "longanlingxin",
    "tavi": "longanlingxin",
    "ori": "longanlingxin",
    "rowan": "longanlufeng",
    "vesh": "longanlufeng",
}
_TTS_CACHE: dict[str, bytes] = {}
_TTS_CACHE_LOCK = threading.Lock()
_TTS_FETCH_LOCKS: dict[str, threading.Lock] = {}
_TTS_MAX_BYTES = 2 * 1024 * 1024
_TTS_PREFETCH_ENABLED = True


def _load_tts_credentials() -> None:
    """Load operator TTS credentials from TTS.csv (key,value rows).

    Precedence: explicit environment variables, then ``QWEN_TTS_CSV`` path,
    then ``TTS.csv`` beside this service, then the repo-root ``TTS.csv``.
    Credentials never enter logs or responses. The CSV's ``apiHost`` value is
    the dedicated WebSocket host; the inference route is appended unless the
    environment already pinned a full ``QWEN_TTS_WS_URL``.
    """
    global QWEN_TTS_API_KEY, QWEN_TTS_WS_URL
    if QWEN_TTS_API_KEY and QWEN_TTS_WS_URL:
        return
    candidates = [
        Path(os.environ["QWEN_TTS_CSV"]) if os.environ.get("QWEN_TTS_CSV") else None,
        Path(__file__).resolve().parent / "TTS.csv",
        REPO_ROOT / "TTS.csv",
    ]
    csv_path = next((path for path in candidates if path is not None and path.is_file()), None)
    if csv_path is None:
        return
    values: dict[str, str] = {}
    try:
        for raw in csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "," not in line:
                continue
            key, value = line.split(",", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return
    if not QWEN_TTS_API_KEY:
        QWEN_TTS_API_KEY = values.get("apiKey", "") or values.get("apikey", "")
    if not QWEN_TTS_WS_URL:
        api_host = values.get("apiHost", "").strip().rstrip("/")
        if api_host:
            QWEN_TTS_WS_URL = f"wss://{api_host}/api-ws/v1/inference"


_load_tts_credentials()


def _tts_key(npc_id: str, line_id: str, voice: str) -> str:
    return f"{npc_id}/{line_id}/{voice}"


def _tts_text_key(npc_id: str, voice: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"text/{npc_id}/{voice}/{digest}"


def _tts_fetch_lock(key: str) -> threading.Lock:
    with _TTS_CACHE_LOCK:
        return _TTS_FETCH_LOCKS.setdefault(key, threading.Lock())


def _cached_wav(keys: list[str]) -> bytes | None:
    with _TTS_CACHE_LOCK:
        for key in keys:
            cached = _TTS_CACHE.get(key)
            if cached is not None:
                for other in keys:
                    _TTS_CACHE[other] = cached
                return cached
    return None


def _store_wav(keys: list[str], body: bytes) -> bytes:
    with _TTS_CACHE_LOCK:
        for key in keys:
            if len(_TTS_CACHE) >= 64 and key not in _TTS_CACHE:
                _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
            _TTS_CACHE[key] = body
    return body


def word_practice_ask_text(options: list[str]) -> str:
    """Server-authored spoken question from catalog lexical IDs."""
    clean = [str(option).strip().lower() for option in options if str(option).strip()]
    if not clean:
        raise KeyError("empty word practice options")
    unknown = [option for option in clean if option not in WORD_LINES]
    if unknown:
        raise KeyError(f"unknown practice word: {unknown[0]}")
    if len(clean) == 1:
        return f"Do you want {clean[0]}?"
    if len(clean) == 2:
        return f"Do you want {clean[0]} or {clean[1]}?"
    return "Do you want " + ", ".join(clean[:-1]) + ", or " + clean[-1] + "?"


def _repair_wav_lengths(audio: bytes) -> bytes:
    """Rewrite RIFF/data size fields the streaming SDK leaves as placeholders.

    DashScope's WAV writer emits 0x7FFFFF.. placeholders instead of seeking
    back over the socket stream; Godot's AudioStreamWAV then logs seek errors
    and only plays because it falls back to the real byte count.
    """
    import struct

    if len(audio) < 44 or audio[0:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return audio
    offset = 12
    while offset + 8 <= len(audio):
        chunk_id = audio[offset:offset + 4]
        size = struct.unpack_from("<I", audio, offset + 4)[0]
        if chunk_id == b"data":
            data_size = len(audio) - (offset + 8)
            if size != data_size:
                audio = audio[:offset + 4] + struct.pack("<I", data_size) + audio[offset + 8:]
                audio = audio[:4] + struct.pack("<I", len(audio) - 8) + audio[8:]
            return audio
        if size == 0x7FFFFF00 or size > len(audio):
            break
        offset += 8 + size + (size & 1)
    return audio


def _dashscope_speech(text: str, voice: str) -> bytes:
    """Synthesize one utterance over the dedicated WebSocket inference route.

    Uses the DashScope SDK exactly as documented for this deployment:
    ``SpeechSynthesizer(model=qwen-audio-3.0-tts-plus).call(text)`` returning
    WAV bytes (24 kHz mono 16-bit). The SDK is imported lazily so the game
    service still starts (and returns 503 for TTS) without it.
    """
    try:
        import dashscope  # noqa: PLC0415
        from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on operator env
        raise RuntimeError("dashscope sdk is not installed") from exc
    dashscope.api_key = QWEN_TTS_API_KEY
    if QWEN_TTS_WS_URL:
        dashscope.base_websocket_api_url = QWEN_TTS_WS_URL
    synthesizer = SpeechSynthesizer(
        model=QWEN_TTS_MODEL,
        voice=voice,
        format=AudioFormat.WAV_24000HZ_MONO_16BIT,
    )
    audio = synthesizer.call(text)
    if not audio or len(audio) < 44:
        raise RuntimeError("qwen tts returned empty audio")
    return _repair_wav_lengths(bytes(audio))


_TTS_POOL = None
_TTS_POOL_LOCK = threading.Lock()
_TTS_STREAM_CHUNK_BYTES = 8192
_TTS_STREAM_QUEUE_TIMEOUT = 10.0


def _tts_pool():
    """SDK synthesizer pool: one pre-connected wss socket, auto-reconnected by
    the pool's own worker thread so per-turn websocket handshakes disappear."""
    global _TTS_POOL
    with _TTS_POOL_LOCK:
        if _TTS_POOL is None:
            import dashscope
            from dashscope.audio.tts_v2 import SpeechSynthesizerObjectPool
            dashscope.api_key = QWEN_TTS_API_KEY
            if QWEN_TTS_WS_URL:
                dashscope.base_websocket_api_url = QWEN_TTS_WS_URL
            # Constructed exactly once: the SDK pool is a process-wide singleton
            # and re-instantiating would reopen every pre-connected socket.
            _TTS_POOL = SpeechSynthesizerObjectPool(max_size=2, url=QWEN_TTS_WS_URL or None)
        return _TTS_POOL


def _prewarm_tts_pool() -> bool:
    if not QWEN_TTS_API_KEY:
        return False
    try:
        from dashscope.audio.tts_v2 import AudioFormat
        voice = QWEN_TTS_VOICE or next(iter(NPC_TTS_VOICES.values()), "")
        if not voice:
            return False
        synthesizer = _tts_pool().borrow_synthesizer(
            model=QWEN_TTS_MODEL, voice=voice, format=AudioFormat.WAV_24000HZ_MONO_16BIT
        )
        _tts_pool().return_synthesizer(synthesizer)
        return True
    except Exception as exc:  # noqa: BLE001 - prewarm is best effort
        print(f"[speech] tts pool prewarm failed: {type(exc).__name__}")
        return False


_TEACHING_MARKERS = (
    "learn english",
    "grammar",
    "your score",
    "pronunciation",
    "repeat after",
    "you should say",
    "as an english",
    "this is a lesson",
    "esl",
)
_REQUEST_PHRASES = (
    "can i get",
    "could i have",
    "i'll take",
    "i will take",
    "i want",
    "i need",
    "do you have",
    "where is",
    "please",
)
_FOLLOW_UP_PHRASES = (
    "to go",
    "for here",
    "here please",
    "that's all",
    "that is all",
    "that'll be all",
    "nothing else",
    "no thanks",
    "yeah",
    "yes",
    "no",
)


_XAI_DIALOGUE_MODEL = "grok-4.3"
_GROK_TIMEOUT_SECONDS = 1.0
_GROK_REASONING_EFFORT = "none"
_GEMINI_DIALOGUE_MODEL = "gemini-3.7-flash"
## Module-level defaults stay mutable: tests pin them directly. The adaptive
## helpers below override them from rolling P90 samples unless the operator
## pins GEMINI_SPEAK_SECONDS / GEMINI_TIMEOUT_SECONDS.
_GEMINI_TIMEOUT_SECONDS = 3.0
_GEMINI_SPEAK_SECONDS = 1.6
## gemini-3.7-flash rejects "minimal"/"none" (400) and ignores thinkingBudget=0
## (thought counts stay ~100+), so LOW is the accepted floor. The env override
## exists so a future model can drop the level without a code change.
_GEMINI_THINKING_LEVEL = "LOW"
_GEMINI_SPEAK_WINDOW_MIN = 1.6
_GEMINI_SPEAK_WINDOW_MAX = 2.6
_GEMINI_SPEAK_WINDOW_MARGIN = 0.35
_GEMINI_TIMEOUT_FLOOR = 3.0
_GEMINI_TIMEOUT_CEIL = 6.0
_GEMINI_TIMEOUT_MARGIN = 2.0
_GEMINI_LATENCY_SAMPLES = 12
_GEMINI_LATENCY_MIN_SAMPLES = 3
_GEMINI_CONSECUTIVE_MISS_RESET = 3
_FIRST_SENTENCE_WORDS = 12
_BACKCHANNEL_PHRASES = (
    "yeah",
    "yep",
    "yes",
    "ok",
    "okay",
    "uh huh",
    "uh-huh",
    "mmhmm",
    "mhm",
    "mm-hmm",
    "got it",
)


def _gemini_thinking_level() -> str:
    return os.environ.get("GEMINI_THINKING_LEVEL", _GEMINI_THINKING_LEVEL).strip() or _GEMINI_THINKING_LEVEL


_GEMINI_LATENCY_LOCK = threading.Lock()
_GEMINI_LATENCY: dict = {"first_ms": deque(maxlen=_GEMINI_LATENCY_SAMPLES), "misses": 0}
_GEMINI_ADAPTIVE_LAST: dict = {"speak": 0.0, "timeout": 0.0}


def _p90(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(0.9 * (len(ordered) - 1))))
    return ordered[index]


def _gemini_speak_window() -> float:
    pinned = os.environ.get("GEMINI_SPEAK_SECONDS", "").strip()
    if pinned:
        try:
            return max(0.05, float(pinned))
        except ValueError:
            pass
    with _GEMINI_LATENCY_LOCK:
        samples = list(_GEMINI_LATENCY["first_ms"])
    if len(samples) < _GEMINI_LATENCY_MIN_SAMPLES:
        return _GEMINI_SPEAK_SECONDS
    p90_s = _p90(samples) / 1000.0
    return min(_GEMINI_SPEAK_WINDOW_MAX, max(_GEMINI_SPEAK_WINDOW_MIN, p90_s + _GEMINI_SPEAK_WINDOW_MARGIN))


def _gemini_socket_timeout() -> float:
    pinned = os.environ.get("GEMINI_TIMEOUT_SECONDS", "").strip()
    if pinned:
        try:
            return max(0.5, float(pinned))
        except ValueError:
            pass
    with _GEMINI_LATENCY_LOCK:
        samples = list(_GEMINI_LATENCY["first_ms"])
    if len(samples) < _GEMINI_LATENCY_MIN_SAMPLES:
        return _GEMINI_TIMEOUT_SECONDS
    p90_s = _p90(samples) / 1000.0
    return min(_GEMINI_TIMEOUT_CEIL, max(_GEMINI_TIMEOUT_FLOOR, p90_s + _GEMINI_TIMEOUT_MARGIN))


def _record_gemini_first(first_ms: int) -> None:
    log: dict = {}
    with _GEMINI_LATENCY_LOCK:
        _GEMINI_LATENCY["first_ms"].append(max(0.0, float(first_ms)))
        _GEMINI_LATENCY["misses"] = 0
    window = _gemini_speak_window()
    timeout = _gemini_socket_timeout()
    with _GEMINI_LATENCY_LOCK:
        samples = len(_GEMINI_LATENCY["first_ms"])
    if abs(window - _GEMINI_ADAPTIVE_LAST["speak"]) >= 0.1 or abs(timeout - _GEMINI_ADAPTIVE_LAST["timeout"]) >= 0.1:
        _GEMINI_ADAPTIVE_LAST["speak"] = window
        _GEMINI_ADAPTIVE_LAST["timeout"] = timeout
        log = {"samples": samples}
    if log:
        _log_stage("gemini_adaptive", 0, speak=round(window, 2), timeout=round(timeout, 2), **log)


def _record_gemini_miss() -> None:
    with _GEMINI_LATENCY_LOCK:
        _GEMINI_LATENCY["misses"] = int(_GEMINI_LATENCY["misses"]) + 1
        if int(_GEMINI_LATENCY["misses"]) >= _GEMINI_CONSECUTIVE_MISS_RESET:
            # Network degraded: drop stale samples so the window falls back to
            # the short default and the stub opens fast again.
            _GEMINI_LATENCY["first_ms"].clear()
            _GEMINI_LATENCY["misses"] = 0


def _dialogue_model_name() -> str:
    if _gemini_api_key():
        return os.environ.get("GEMINI_DIALOGUE_MODEL", _GEMINI_DIALOGUE_MODEL).strip() or _GEMINI_DIALOGUE_MODEL
    return os.environ.get("XAI_DIALOGUE_MODEL", _XAI_DIALOGUE_MODEL).strip() or _XAI_DIALOGUE_MODEL


def _dialogue_reasoning_effort(model_name: str) -> str | None:
    if model_name.startswith("grok-4.3"):
        return _GROK_REASONING_EFFORT
    return None


def _dialogue_system_prompt() -> str:
    return (
        "You are one American service worker in a spoken language-learning game. "
        "Stay in character. Use natural everyday American English. "
        "Reply in at most two short sentences and 30 words. "
        "Never teach English, never correct grammar, never mention scores, "
        "lessons, or that you are an AI. Sell or help only with inventory "
        "and can_do. If the player asks for something off inventory, refuse "
        "in character and do not complete the transaction. "
        "Score the player's latest utterance for how idiomatic it is in this "
        "exact situation from 0 to 100. "
        "Write the spoken NPC reply first as one plain-text line (at most two "
        "short sentences). Then a blank line. Then JSON only with speech_act, "
        "emotion, next_state, and player_turn. Do not wrap the spoken line in "
        "JSON. If you must return JSON only, put the spoken reply in text. "
        "player_turn must include idiomaticity, progress, transaction_complete, "
        "and off_inventory. next_state must be awaiting_player, "
        "awaiting_follow_up, or closed. "
        "Set transaction_complete true only when you would actually hand over "
        "the item. After the player names an in-inventory item, you may ask "
        "here or to go once. When they answer, hand it over, do not upsell, "
        "and set transaction_complete true and next_state closed."
    )


def _looks_like_xai_key(value: str) -> bool:
    return value.startswith("xai-") and len(value) > 20


def _looks_like_gemini_key(value: str) -> bool:
    if len(value) < 24 or value.startswith("xai-"):
        return False
    return value.startswith("AIza") or value.startswith("AQ.")


def _xai_key_from_csv(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return ""
    header = [cell.strip() for cell in rows[0]]
    lowered = [cell.lower() for cell in header]
    if "apikey" in lowered or "api_key" in lowered:
        index = lowered.index("apikey") if "apikey" in lowered else lowered.index("api_key")
        for row in rows[1:]:
            if index < len(row) and row[index].strip():
                return row[index].strip()
    for row in rows:
        cells = [cell.strip() for cell in row if str(cell).strip()]
        if not cells:
            continue
        if cells[0].lower() in {"apikey", "api_key"} and len(cells) >= 2:
            return cells[1]
        for cell in cells:
            if _looks_like_xai_key(cell):
                return cell
    return ""


def _xai_key_from_xlsx(path: Path) -> str:
    import zipfile
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(path) as archive:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return ""
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    for node in root.findall("m:si", namespace):
        text = "".join(part.text or "" for part in node.findall(".//m:t", namespace)).strip()
        if _looks_like_xai_key(text):
            return text
    return ""


def _xai_api_key() -> str:
    if "XAI_API_KEY" in os.environ:
        return os.environ.get("XAI_API_KEY", "").strip()
    service_dir = Path(__file__).resolve().parent
    candidates = [service_dir / "XAI.csv", REPO_ROOT / "XAI.csv", service_dir / "XAI.xlsx"]
    candidates.extend(sorted(service_dir.glob("*.xlsx")))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        try:
            value = _xai_key_from_xlsx(candidate) if candidate.suffix.lower() == ".xlsx" else _xai_key_from_csv(candidate)
        except (OSError, csv.Error, KeyError, ValueError) as exc:
            print(f"[dialogue] ignored unreadable xAI credential file: {type(exc).__name__}")
            continue
        if value:
            return value
    return ""


def _gemini_api_key() -> str:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if name in os.environ:
            return os.environ.get(name, "").strip()
    service_dir = Path(__file__).resolve().parent
    for candidate in (service_dir / "GEMINI.csv", REPO_ROOT / "GEMINI.csv"):
        if not candidate.is_file():
            continue
        try:
            value = _xai_key_from_csv(candidate)
        except (OSError, csv.Error, KeyError, ValueError) as exc:
            print(f"[dialogue] ignored unreadable Gemini credential file: {type(exc).__name__}")
            continue
        if value and _looks_like_gemini_key(value):
            return value
        if value and len(value) >= 24 and not _looks_like_xai_key(value):
            return value
    return ""


def _dialogue_llm_configured() -> bool:
    return bool(_gemini_api_key() or _xai_api_key())


def _inventory_terms(scenario: dict) -> list[str]:
    terms: list[str] = []
    for raw in scenario.get("inventory") or []:
        term = normalise(str(raw)).lower()
        if term and term not in terms:
            terms.append(term)
    return terms


def _transcript_hits_inventory(scenario: dict, transcript: str) -> bool:
    text = normalise(transcript).lower()
    return any(term in text for term in _inventory_terms(scenario))


def _has_request_phrase(transcript: str, scenario: dict) -> bool:
    text = normalise(transcript).lower()
    cues = [normalise(str(item)).lower() for item in scenario.get("request_cues") or []]
    return any(phrase in text for phrase in (*_REQUEST_PHRASES, *cues) if phrase)


def _dialogue_transcript_relevant(scenario: dict, transcript: str, history: list) -> bool:
    text = normalise(transcript)
    if _transcript_hits_inventory(scenario, text) or _has_request_phrase(text, scenario) or _is_backchannel(text):
        return True
    has_npc_context = any(
        isinstance(turn, dict) and str(turn.get("role", "")) == "npc"
        for turn in history[-8:]
    )
    return has_npc_context and len(text.split()) <= 12


def _safe_gate_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) else 0.0


def _safe_idiomaticity(value: object) -> float:
    score = _safe_gate_score(value)
    return max(0.0, min(100.0, score))


def _contains_teaching_talk(text: str) -> bool:
    lowered = normalise(text).lower()
    return any(marker in lowered for marker in _TEACHING_MARKERS)


def _scene_card(scenario: dict, profile: dict) -> dict:
    return {
        "npc_id": profile.get("npc_id", ""),
        "occupation": profile.get("occupation", ""),
        "persona": profile.get("persona", ""),
        "location": scenario.get("location", ""),
        "role": scenario.get("role", ""),
        "inventory": list(scenario.get("inventory") or []),
        "can_do": list(scenario.get("can_do") or []),
        "cannot_do": list(scenario.get("cannot_do") or []),
        "allowed_speech_acts": list(scenario.get("allowed_speech_acts") or []),
    }


def _dialogue_gate(scenario: dict, text: str, speech_act: str) -> dict:
    clean = normalise(text)
    words = clean.split()
    violations: list[str] = []
    if not clean:
        violations.append("empty_reply")
    if len(words) > 30:
        violations.append("too_long")
    if sum(1 for char in clean if char in ".!?") > 2:
        violations.append("too_many_sentences")
    if speech_act not in (scenario.get("allowed_speech_acts") or []):
        violations.append("speech_act_not_allowed")
    if _contains_teaching_talk(clean):
        violations.append("teacher_talk")
    lowered = clean.lower()
    for marker in ["ignore previous", "system message", "as an ai", "```", "http://", "https://"]:
        if marker in lowered:
            violations.append("unsafe_or_prompt_injection_text")
            break
    for marker in ["fuck", "shit", "bitch", "kill yourself"]:
        if accept_pattern(marker).search(lowered):
            violations.append("unsafe_or_offensive_text")
            break
    return {
        "accepted": not violations,
        "violations": violations,
    }


def _history_hits_inventory(scenario: dict, history: list) -> bool:
    return any(_transcript_hits_inventory(scenario, str(turn.get("text", ""))) for turn in history)


def _is_service_follow_up(transcript: str) -> bool:
    text = normalise(transcript).lower()
    return any(phrase in text for phrase in _FOLLOW_UP_PHRASES)


def _is_backchannel(transcript: str) -> bool:
    text = normalise(transcript).lower().strip(" .,!?")
    if not text:
        return False
    if text in _BACKCHANNEL_PHRASES:
        return True
    return len(text.split()) <= 2 and text in _BACKCHANNEL_PHRASES


def _normalise_player_turn(raw: object, transcript: str, scenario: dict, history: list | None = None) -> dict:
    data = raw if isinstance(raw, dict) else {}
    history = history or []
    current_hit = _transcript_hits_inventory(scenario, transcript)
    known_item = current_hit or _history_hits_inventory(scenario, history)
    follow_up = _is_service_follow_up(transcript)
    asked_new_item = _has_request_phrase(transcript, scenario) and not current_hit and not follow_up
    off_inventory = bool(data.get("off_inventory", False))
    if asked_new_item:
        off_inventory = True
    if current_hit or (known_item and follow_up):
        off_inventory = False
    complete = (
        bool(data.get("transaction_complete", False))
        and not off_inventory
        and known_item
        and not asked_new_item
        and not (_is_backchannel(transcript) and not known_item)
    )
    idiomaticity = data.get("idiomaticity", 50)
    if idiomaticity <= 1:
        idiomaticity = float(idiomaticity) * 100.0
    return {
        "idiomaticity": _safe_idiomaticity(idiomaticity),
        "progress": str(data.get("progress", "ordering")).strip() or "ordering",
        "transaction_complete": complete,
        "off_inventory": off_inventory,
    }


def _stub_dialogue(body: dict, scenario: dict) -> dict:
    transcript = normalise(body.get("transcript", ""))
    retry_index = max(0, min(1, int(body.get("retry", 0) or 0)))
    hit = _transcript_hits_inventory(scenario, transcript)
    asked = _has_request_phrase(transcript, scenario)
    if hit and asked:
        closing = (
            "You got it."
            if retry_index == 0
            else "Coming right up."
        )
        return {
            "text": closing,
            "speech_act": "confirm_order",
            "emotion": "neutral",
            "next_state": "closed",
            "player_turn": {
                "idiomaticity": 82.0,
                "progress": "done",
                "transaction_complete": True,
                "off_inventory": False,
            },
        }
    if hit:
        return {
            "text": "Sure. For here or to go?",
            "speech_act": "offer_choice",
            "emotion": "neutral",
            "next_state": "awaiting_follow_up",
            "player_turn": {
                "idiomaticity": 58.0,
                "progress": "ordering",
                "transaction_complete": False,
                "off_inventory": False,
            },
        }
    if asked:
        return {
            "text": "I don't have that here.",
            "speech_act": "clarify_request",
            "emotion": "neutral",
            "next_state": "awaiting_follow_up",
            "player_turn": {
                "idiomaticity": 42.0,
                "progress": "clarifying",
                "transaction_complete": False,
                "off_inventory": True,
            },
        }
    return {
        "text": "Sorry, could you say that again?",
        "speech_act": "clarify_request",
        "emotion": "patient",
        "next_state": "awaiting_follow_up",
        "player_turn": {
            "idiomaticity": 36.0,
            "progress": "clarifying",
            "transaction_complete": False,
            "off_inventory": False,
        },
    }


def _parse_model_json(content: object) -> dict | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _gemini_request_url(model_name: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}"
        ":streamGenerateContent?alt=sse"
    )


_GEMINI_SESSION = None
_GEMINI_SESSION_LOCK = threading.Lock()


def _gemini_session():
    """Process-wide proxy-aware session so each turn reuses a warm TLS
    connection instead of paying ~0.6s of connect+handshake through the proxy.
    Falls back to None (per-request urllib) when requests is unavailable."""
    global _GEMINI_SESSION
    if requests is None:
        return None
    with _GEMINI_SESSION_LOCK:
        if _GEMINI_SESSION is None:
            _GEMINI_SESSION = requests.Session()
        return _GEMINI_SESSION


@contextlib.contextmanager
def _gemini_post_stream(url: str, headers: dict, body: bytes, timeout: float):
    """Yield an iterator of raw SSE response lines from one POST.

    Test seam: unit tests patch this function instead of urlopen. Raises
    urllib.error.HTTPError for non-200 responses so downstream failure
    classification (reason="HTTP <code>") is unchanged.
    """
    session = _gemini_session()
    if session is None:  # pragma: no cover - deployment without requests
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            yield _iter_response_lines(response)
        return
    response = None
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            response = session.post(url, headers=headers, data=body, timeout=timeout, stream=True)
            break
        except requests.exceptions.ConnectionError as exc:
            # Idle keep-alive connections dropped by the proxy: retry once on
            # a fresh connection (same policy as the dashscope SDK client).
            last_error = exc
    if response is None:
        raise urllib.error.URLError(f"connection failed: {last_error}")
    try:
        if response.status_code != 200:
            detail = ""
            try:
                detail = response.text[:200]
            except Exception:  # noqa: BLE001 - best-effort error detail
                pass
            raise urllib.error.HTTPError(url, response.status_code, f"HTTP {response.status_code}: {detail}", response.headers, None)  # type: ignore[arg-type]

        def _sse_lines():
            for line in response.iter_lines(chunk_size=None):
                if line:
                    yield line + b"\n"
                else:
                    yield b"\n"  # keep event separators visible to line parsers

        yield _sse_lines()
    finally:
        response.close()


def _read_response_bytes(response) -> bytes:
    return b"".join(_iter_response_lines(response))


def _iter_response_lines(response):
    """Yield HTTP body lines. Prefer readline so Gemini SSE can surface a first
    sentence before the model finishes the score JSON."""
    readline = getattr(response, "readline", None)
    reader = getattr(response, "read", None)
    use_readline = callable(readline) and (isinstance(response, HTTPResponse) or not callable(reader))
    if use_readline:
        while True:
            line = readline()
            if not line:
                break
            yield line if isinstance(line, bytes) else str(line).encode("utf-8")
        return
    if callable(reader):
        data = reader() or b""
        if not isinstance(data, bytes):
            data = str(data).encode("utf-8")
        for line in data.splitlines(True):
            yield line
        return
    for line in response:
        yield line if isinstance(line, bytes) else str(line).encode("utf-8")


def _gemini_text_from_payload(payload: dict) -> str:
    parts = ((((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or [])
    return "".join(str(part.get("text") or "") for part in parts)


def _gemini_content_from_body(raw: bytes) -> tuple[str, dict]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "", {}
    if text.startswith("data:") or "\ndata:" in text:
        assembled = ""
        meta: dict = {}
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            blob = line[5:].strip()
            if not blob or blob == "[DONE]":
                continue
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                continue
            assembled += _gemini_text_from_payload(payload)
            if isinstance(payload.get("usageMetadata"), dict):
                meta = payload["usageMetadata"]
        return assembled, meta
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, {}
    if isinstance(payload, dict):
        return _gemini_text_from_payload(payload), payload.get("usageMetadata") or {}
    return text, {}


def _parse_gemini_output(content: str) -> dict | None:
    parsed = _parse_model_json(content)
    if parsed is not None and str(parsed.get("text", "")).strip():
        return parsed
    stripped = (content or "").strip()
    if not stripped:
        return parsed
    if "\n" in stripped:
        spoken, rest = stripped.split("\n", 1)
        spoken = spoken.strip().strip("`").strip('"')
        json_part = _parse_model_json(rest.strip()) or {}
        if spoken and not spoken.startswith("{"):
            json_part["text"] = spoken
            return json_part
    if stripped.startswith("{"):
        return parsed
    return {
        "text": stripped.split("\n", 1)[0].strip(),
        "speech_act": "clarify_request",
        "emotion": "neutral",
        "next_state": "awaiting_follow_up",
        "player_turn": {
            "idiomaticity": 50.0,
            "progress": "ordering",
            "transaction_complete": False,
            "off_inventory": False,
        },
    }


def _first_spoken_sentence(text: str) -> str:
    clean = normalise(text)
    if not clean:
        return ""
    if clean.startswith("{"):
        match = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', clean)
        if match:
            clean = normalise(match.group(1).replace('\\"', '"'))
        else:
            return ""
    words = 0
    buf: list[str] = []
    for char in clean:
        buf.append(char)
        if char == " ":
            words += 1
        if char in ".?!" and words >= 1:
            return "".join(buf).strip()
        if words >= _FIRST_SENTENCE_WORDS:
            return "".join(buf).strip()
    return ""


def _read_gemini_stream(lines, on_partial=None, started=None) -> tuple[bytes, dict, int]:
    raw = b""
    usage: dict = {}
    first_ms = 0
    if started is None:
        started = time.perf_counter()
    for line in lines:
        raw += line
        content, meta = _gemini_content_from_body(raw)
        if isinstance(meta, dict) and meta:
            usage = meta
        if on_partial is not None and content:
            on_partial(content)
        if not first_ms:
            parsed = _parse_gemini_output(content)
            first = _first_spoken_sentence(str((parsed or {}).get("text") or content))
            if first:
                # Wall clock from request start: the speak window budget spends
                # the same proxy connect + header wait, so the sample must too.
                first_ms = int((time.perf_counter() - started) * 1000)
    return raw, usage, first_ms


def _spoken_sentences(text: str) -> list[str]:
    clean = normalise(text)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return [part.strip() for part in parts if part.strip()]


def _gemini_dialogue(body: dict, scenario: dict, profile: dict, on_partial=None) -> dict | None:
    api_key = _gemini_api_key()
    if not api_key:
        return None
    model_name = os.environ.get("GEMINI_DIALOGUE_MODEL", _GEMINI_DIALOGUE_MODEL).strip() or _GEMINI_DIALOGUE_MODEL
    user = {
        "scene": _scene_card(scenario, profile),
        "transcript": body.get("transcript", ""),
        "history": body.get("history", [])[-8:],
    }
    thinking_level = _gemini_thinking_level()
    request_body = {
        "systemInstruction": {"parts": [{"text": _dialogue_system_prompt()}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(user, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 256,
            "thinkingConfig": {"thinkingLevel": thinking_level},
        },
    }
    started = time.perf_counter()
    try:
        with _gemini_post_stream(
            _gemini_request_url(model_name),
            {"Content-Type": "application/json", "x-goog-api-key": api_key},
            json.dumps(request_body).encode("utf-8"),
            _gemini_socket_timeout(),
        ) as lines:
            raw, usage, first_ms = _read_gemini_stream(lines, on_partial, started)
        ms = int((time.perf_counter() - started) * 1000)
        if first_ms:
            _record_gemini_first(first_ms)
        content, usage = _gemini_content_from_body(raw)
        if not usage:
            usage = {}
        parsed = _parse_gemini_output(content)
        thoughts = usage.get("thoughtsTokenCount") if isinstance(usage, dict) else None
        first = _first_spoken_sentence(str((parsed or {}).get("text") or content))
        if not first_ms and first:
            first_ms = ms
            _record_gemini_first(first_ms)
        if parsed is None:
            _log_stage(
                "gemini",
                ms,
                source="none",
                reason="parse",
                model=model_name,
                thinking=thinking_level,
                thoughts=thoughts,
            )
            return None
        parsed["_provider"] = "gemini"
        parsed["_model"] = model_name
        parsed["_llm_ms"] = ms
        parsed["_first_ms"] = first_ms
        _log_stage(
            "gemini_first",
            first_ms,
            source="gemini",
            reason="ok" if first else "none",
            model=model_name,
            thinking=thinking_level,
            text=first or parsed.get("text", ""),
        )
        _log_stage(
            "gemini",
            ms,
            source="gemini",
            reason="ok",
            model=model_name,
            thinking=thinking_level,
            thoughts=thoughts,
            text=parsed.get("text", ""),
        )
        return parsed
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, TypeError, ValueError) as exc:
        ms = int((time.perf_counter() - started) * 1000)
        _record_gemini_miss()
        reason = _url_fail_reason(exc)
        _log_stage(
            "gemini",
            ms,
            source="none",
            reason=reason,
            model=model_name,
            thinking=thinking_level,
            timeout_s=_gemini_socket_timeout(),
        )
        return None


def _grok_dialogue(body: dict, scenario: dict, profile: dict) -> dict | None:
    api_key = _xai_api_key()
    if not api_key:
        return None
    model_name = os.environ.get("XAI_DIALOGUE_MODEL", _XAI_DIALOGUE_MODEL).strip() or _XAI_DIALOGUE_MODEL
    user = {
        "scene": _scene_card(scenario, profile),
        "transcript": body.get("transcript", ""),
        "history": body.get("history", [])[-8:],
    }
    request_body = {
        "model": model_name,
        "temperature": 0.3,
        "max_tokens": 80,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _dialogue_system_prompt()},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    }
    effort = _dialogue_reasoning_effort(model_name)
    if effort is not None:
        request_body["reasoning_effort"] = effort
    request = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=_GROK_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        ms = int((time.perf_counter() - started) * 1000)
        content = payload["choices"][0]["message"]["content"]
        parsed = _parse_model_json(content)
        if parsed is None:
            _log_stage(
                "grok",
                ms,
                source="none",
                reason="parse",
                model=model_name,
                reasoning=effort or "default",
            )
            return None
        parsed["_provider"] = "grok"
        parsed["_model"] = model_name
        parsed["_llm_ms"] = ms
        _log_stage(
            "grok",
            ms,
            source="grok",
            reason="ok",
            model=model_name,
            reasoning=effort or "default",
            text=parsed.get("text", ""),
        )
        return parsed
    except (OSError, urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError, TypeError, ValueError) as exc:
        ms = int((time.perf_counter() - started) * 1000)
        reason = _url_fail_reason(exc)
        _log_stage(
            "grok",
            ms,
            source="none",
            reason=reason,
            model=model_name,
            reasoning=effort or "default",
            timeout_s=_GROK_TIMEOUT_SECONDS,
        )
        return None


def _gemini_live(body: dict, scenario: dict, profile: dict) -> dict:
    """Run Gemini on a worker; expose accumulating text for T_speak."""
    state: dict = {
        "partial": "",
        "parsed": None,
        "done": False,
        "error": None,
        "started": time.perf_counter(),
    }

    def reader() -> None:
        try:
            def on_partial(content: str) -> None:
                state["partial"] = content
                parsed = _parse_gemini_output(content)
                if parsed is not None and str(parsed.get("text", "")).strip():
                    state["partial"] = str(parsed.get("text") or content)

            state["parsed"] = _gemini_dialogue(body, scenario, profile, on_partial)
            if state["parsed"] is not None:
                state["partial"] = str(state["parsed"].get("text") or state.get("partial") or "")
        except Exception as exc:  # provider detail stays in this worker
            state["error"] = exc
        finally:
            state["done"] = True

    thread = threading.Thread(target=reader, daemon=True, name="gemini-live")
    thread.start()
    state["thread"] = thread
    return state


def _wait_first_sentence(state: dict, speak_s: float) -> str:
    deadline = state["started"] + speak_s
    while time.perf_counter() < deadline:
        parsed = state.get("parsed")
        blob = str((parsed or {}).get("text") or state.get("partial") or "")
        first = _first_spoken_sentence(blob)
        if first:
            return first
        if blob and state["done"]:
            return normalise(blob)
        if state["done"]:
            return ""
        time.sleep(0.02)
    parsed = state.get("parsed")
    blob = str((parsed or {}).get("text") or state.get("partial") or "")
    return _first_spoken_sentence(blob)


def generate_dialogue_reply(body: dict) -> dict:
    npc_id = str(body.get("npc_id", "")).strip().lower()
    scenario_id = str(body.get("scenario_id", "")).strip().lower()
    transcript = normalise(str(body.get("transcript", "")))
    scenario = _DIALOGUE_SCENARIOS.get(scenario_id)
    profile = _DIALOGUE_PROFILES.get(npc_id)
    if not scenario or not profile or str(scenario.get("npc_id", "")).strip().lower() != npc_id:
        raise ValueError("unknown dialogue scenario")
    if not transcript or len(transcript) > 1000:
        raise ValueError("invalid transcript")
    _log_heard("dialogue", transcript, npc=npc_id, scenario=scenario_id)
    history = body.get("history", [])
    if not isinstance(history, list):
        raise ValueError("invalid dialogue history")
    clean_history: list[dict] = []
    for turn in history[-8:]:
        if not isinstance(turn, dict) or str(turn.get("role", "")) not in {"player", "npc"}:
            raise ValueError("invalid dialogue history")
        turn_text = normalise(str(turn.get("text", "")))
        if not turn_text or len(turn_text) > 1000:
            raise ValueError("invalid dialogue history")
        clean_history.append({"role": str(turn["role"]), "text": turn_text})
    body = {**body, "history": clean_history}
    llm_configured = _dialogue_llm_configured()
    if not llm_configured and not _dialogue_transcript_relevant(scenario, transcript, clean_history):
        raise ValueError("dialogue quality gate rejected irrelevant transcript")
    generated = None
    source = "stub"
    if _gemini_api_key():
        generated = _gemini_dialogue(body, scenario, profile)
        source = "gemini"
    elif _xai_api_key():
        generated = _grok_dialogue(body, scenario, profile)
        source = "grok"
    if generated is None:
        generated = _stub_dialogue(body, scenario)
        source = "stub"
    text = normalise(str(generated.get("text", "")))
    speech_act = str(generated.get("speech_act", "clarify_request")).strip()
    emotion = str(generated.get("emotion", "neutral")).strip() or "neutral"
    next_state = str(generated.get("next_state", "awaiting_follow_up")).strip()
    player_turn = _normalise_player_turn(generated.get("player_turn"), transcript, scenario, clean_history)
    if player_turn["transaction_complete"]:
        next_state = "closed"
    elif next_state == "closed":
        player_turn["transaction_complete"] = False
    gate = _dialogue_gate(scenario, text, speech_act)
    if next_state not in {"awaiting_player", "awaiting_follow_up", "closed"}:
        gate["violations"].append("next_state_not_allowed")
        gate["accepted"] = False
    if not gate["accepted"]:
        raise ValueError("dialogue quality gate rejected response")
    context = body.get("game_context", {})
    pronunciation = -1.0
    if isinstance(context, dict) and "pronunciation" in context:
        pronunciation = _safe_idiomaticity(context.get("pronunciation"))
    turn_score = None
    if pronunciation >= 0.0:
        turn_score = round(0.5 * pronunciation + 0.5 * player_turn["idiomaticity"], 1)
    reply_id = "reply-" + uuid.uuid4().hex[:20]
    if len(_DYNAMIC_REPLIES) >= 256:
        _DYNAMIC_REPLIES.pop(next(iter(_DYNAMIC_REPLIES)))
    _DYNAMIC_REPLIES[reply_id] = {
        "npc_id": npc_id,
        "text": text,
        "voice": NPC_TTS_VOICES.get(npc_id, ""),
    }
    llm_ms = generated.get("_llm_ms")
    first_ms = generated.get("_first_ms")
    _log_stage(
        "dialogue",
        int(llm_ms) if isinstance(llm_ms, int) else 0,
        source=source,
        model=generated.get("_model", "") if source != "stub" else "",
        npc=npc_id,
        speech_act=speech_act,
        complete=int(bool(player_turn["transaction_complete"])),
        text=text,
    )
    _log_stage(
        "first_audio",
        int(first_ms) if isinstance(first_ms, int) else (int(llm_ms) if isinstance(llm_ms, int) else 0),
        source=source,
        npc=npc_id,
        reply=reply_id,
    )
    if _TTS_PREFETCH_ENABLED:
        threading.Thread(
            target=_prefetch_dynamic_reply,
            args=(npc_id, reply_id),
            daemon=True,
            name=f"tts-prefetch-{reply_id}",
        ).start()
    return {
        "reply_id": reply_id,
        "npc_id": npc_id,
        "text": text,
        "speech_act": speech_act,
        "emotion": emotion,
        "next_state": next_state,
        "player_turn": player_turn,
        "session": {
            "turn_count": 1 + len([turn for turn in clean_history if turn["role"] == "player"]),
            "running_score": turn_score,
        },
        "gate": gate,
        "source": source,
        "model": generated.get("_model", "") if source in {"gemini", "grok"} else "",
    }


def _register_spoken_reply(npc_id: str, text: str, wait_tts: bool, prefetch: bool = True) -> str:
    reply_id = "reply-" + uuid.uuid4().hex[:20]
    if len(_DYNAMIC_REPLIES) >= 256:
        _DYNAMIC_REPLIES.pop(next(iter(_DYNAMIC_REPLIES)))
    _DYNAMIC_REPLIES[reply_id] = {
        "npc_id": npc_id,
        "text": text,
        "voice": NPC_TTS_VOICES.get(npc_id, ""),
    }
    if wait_tts and _TTS_PREFETCH_ENABLED:
        started = time.perf_counter()
        try:
            synthesize_dynamic_reply(npc_id, reply_id)
            _log_stage("tts_first", int((time.perf_counter() - started) * 1000), npc=npc_id, reply=reply_id)
        except Exception as exc:  # TTS failure must not block the spoken commitment
            print(f"[speech] tts first failed for {npc_id}/{reply_id}: {type(exc).__name__}")
    elif prefetch and _TTS_PREFETCH_ENABLED:
        threading.Thread(
            target=_prefetch_dynamic_reply,
            args=(npc_id, reply_id),
            daemon=True,
            name=f"tts-prefetch-{reply_id}",
        ).start()
    return reply_id


def _prepared_dialogue(body: dict) -> tuple[str, dict, dict, str, list[dict], dict]:
    npc_id = str(body.get("npc_id", "")).strip().lower()
    scenario_id = str(body.get("scenario_id", "")).strip().lower()
    transcript = normalise(str(body.get("transcript", "")))
    scenario = _DIALOGUE_SCENARIOS.get(scenario_id)
    profile = _DIALOGUE_PROFILES.get(npc_id)
    if not scenario or not profile or str(scenario.get("npc_id", "")).strip().lower() != npc_id:
        raise ValueError("unknown dialogue scenario")
    if not transcript or len(transcript) > 1000:
        raise ValueError("invalid transcript")
    history = body.get("history", [])
    if not isinstance(history, list):
        raise ValueError("invalid dialogue history")
    clean_history: list[dict] = []
    for turn in history[-8:]:
        if not isinstance(turn, dict) or str(turn.get("role", "")) not in {"player", "npc"}:
            raise ValueError("invalid dialogue history")
        turn_text = normalise(str(turn.get("text", "")))
        if not turn_text or len(turn_text) > 1000:
            raise ValueError("invalid dialogue history")
        clean_history.append({"role": str(turn["role"]), "text": turn_text})
    prepared = {**body, "history": clean_history}
    if not _dialogue_llm_configured() and not _dialogue_transcript_relevant(scenario, transcript, clean_history):
        raise ValueError("dialogue quality gate rejected irrelevant transcript")
    return npc_id, scenario, profile, transcript, clean_history, prepared


def iter_dialogue_events(body: dict):
    """Yield SSE-shaped dialogue events: speaking, then score, then done."""
    turn_started = time.perf_counter()
    npc_id, scenario, profile, transcript, clean_history, prepared = _prepared_dialogue(body)
    _log_heard("dialogue", transcript, npc=npc_id, scenario=str(body.get("scenario_id", "")))
    stub_fallback = _stub_dialogue(prepared, scenario)
    spoken_source = "stub"
    generated = stub_fallback
    first_text = ""
    live = None
    if _gemini_api_key():
        live = _gemini_live(prepared, scenario, profile)
        first_text = _wait_first_sentence(live, _gemini_speak_window())
        if first_text:
            spoken_source = "gemini"
            generated = {
                **stub_fallback,
                "text": first_text,
                "_provider": "gemini",
                "_model": _dialogue_model_name(),
            }
    elif _xai_api_key():
        grok_generated = _grok_dialogue(prepared, scenario, profile)
        if grok_generated is not None:
            spoken_source = "grok"
            generated = grok_generated
            first_text = _first_spoken_sentence(str(grok_generated.get("text") or "")) or normalise(str(grok_generated.get("text") or ""))
    if not first_text:
        generated = stub_fallback
        spoken_source = "stub"
        first_text = normalise(str(generated.get("text", "")))
    sentences = _spoken_sentences(first_text) or [first_text]
    primary = sentences[0]
    gate = _dialogue_gate(scenario, primary, str(generated.get("speech_act", "clarify_request")))
    if not gate["accepted"]:
        generated = _stub_dialogue(prepared, scenario)
        spoken_source = "stub"
        primary = normalise(str(generated.get("text", "")))
        sentences = [primary]
        gate = _dialogue_gate(scenario, primary, str(generated.get("speech_act", "clarify_request")))
        if not gate["accepted"]:
            raise ValueError("dialogue quality gate rejected response")
    first_reply = _register_spoken_reply(npc_id, primary, False, prefetch=False)
    yield {
        "event": "speaking",
        "data": {
            "reply_id": first_reply,
            "npc_id": npc_id,
            "text": primary,
            "source": spoken_source,
            "speech_act": str(generated.get("speech_act", "clarify_request")),
            "gate": gate,
        },
    }
    # Stream the spoken line inline so the desktop client starts playback
    # without a second HTTP round trip; JSON/web clients still use /game/tts.
    if QWEN_TTS_API_KEY and _TTS_PREFETCH_ENABLED:
        seq = 0
        total_pcm = 0
        audio_began = False
        try:
            for chunk in _stream_dynamic_reply_audio(npc_id, first_reply):
                if not audio_began:
                    audio_began = True
                    yield {
                        "event": "audio_begin",
                        "data": {
                            "reply_id": first_reply,
                            "npc_id": npc_id,
                            "sample_rate": 24000,
                            "channels": 1,
                            "bits": 16,
                        },
                    }
                total_pcm += len(chunk)
                yield {
                    "event": "audio",
                    "data": {
                        "reply_id": first_reply,
                        "npc_id": npc_id,
                        "seq": seq,
                        "pcm_b64": base64.b64encode(chunk).decode("ascii"),
                    },
                }
                seq += 1
        except Exception as exc:  # noqa: BLE001 - audio failure must not kill score/done
            _log_stage("tts_stream", 0, npc=npc_id, reply=first_reply, reason=type(exc).__name__)
            yield {
                "event": "audio_failed",
                "data": {"reply_id": first_reply, "npc_id": npc_id, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"},
            }
        else:
            if total_pcm > 0:
                yield {"event": "audio_end", "data": {"reply_id": first_reply, "npc_id": npc_id, "bytes": total_pcm}}
            else:
                yield {
                    "event": "audio_failed",
                    "data": {"reply_id": first_reply, "npc_id": npc_id, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"},
                }
    if live is not None:
        live["thread"].join(timeout=max(0.05, _gemini_socket_timeout()))
        if live.get("parsed"):
            generated = live["parsed"]
            if spoken_source == "stub":
                generated = {**generated, "text": primary}
            elif normalise(str(generated.get("text") or "")) and _first_spoken_sentence(str(generated.get("text") or "")):
                # Spoken text is already committed; keep scores only.
                generated = {**generated, "text": primary}
    text = primary
    speech_act = str(generated.get("speech_act", "clarify_request")).strip()
    emotion = str(generated.get("emotion", "neutral")).strip() or "neutral"
    next_state = str(generated.get("next_state", "awaiting_follow_up")).strip()
    player_turn = _normalise_player_turn(generated.get("player_turn"), transcript, scenario, clean_history)
    if player_turn["transaction_complete"]:
        next_state = "closed"
    elif next_state == "closed":
        player_turn["transaction_complete"] = False
    score_gate = _dialogue_gate(scenario, text, speech_act)
    if next_state not in {"awaiting_player", "awaiting_follow_up", "closed"}:
        score_gate["violations"].append("next_state_not_allowed")
        score_gate["accepted"] = False
    if not score_gate["accepted"]:
        stub = _stub_dialogue(prepared, scenario)
        speech_act = str(stub.get("speech_act", speech_act))
        emotion = str(stub.get("emotion", emotion))
        next_state = str(stub.get("next_state", next_state))
        player_turn = _normalise_player_turn(stub.get("player_turn"), transcript, scenario, clean_history)
        score_gate = _dialogue_gate(scenario, text, speech_act)
    context = prepared.get("game_context", {})
    pronunciation = -1.0
    if isinstance(context, dict) and "pronunciation" in context:
        pronunciation = _safe_idiomaticity(context.get("pronunciation"))
    turn_score = None
    if pronunciation >= 0.0:
        turn_score = round(0.5 * pronunciation + 0.5 * player_turn["idiomaticity"], 1)
    model_name = generated.get("_model", "") if spoken_source in {"gemini", "grok"} and generated.get("_provider") in {"gemini", "grok"} else ""
    if live is not None and live.get("parsed"):
        model_name = str(live["parsed"].get("_model") or model_name)
        spoken_log = "gemini" if live.get("parsed") and spoken_source != "stub" else spoken_source
    else:
        spoken_log = spoken_source
    _log_stage(
        "dialogue",
        int(generated.get("_llm_ms") or 0),
        source=spoken_log,
        model=model_name,
        npc=npc_id,
        speech_act=speech_act,
        complete=int(bool(player_turn["transaction_complete"])),
        text=text,
    )
    _log_stage(
        "first_audio",
        int((time.perf_counter() - turn_started) * 1000),
        source=spoken_source,
        npc=npc_id,
        reply=first_reply,
    )
    yield {
        "event": "score",
        "data": {
            "reply_id": first_reply,
            "npc_id": npc_id,
            "speech_act": speech_act,
            "emotion": emotion,
            "next_state": next_state,
            "player_turn": player_turn,
            "session": {
                "turn_count": 1 + len([turn for turn in clean_history if turn["role"] == "player"]),
                "running_score": turn_score,
            },
            "gate": score_gate,
            "source": spoken_source,
            "model": model_name,
        },
    }
    yield {
        "event": "done",
        "data": {
            "reply_id": first_reply,
            "npc_id": npc_id,
            "source": spoken_source,
            "model": model_name,
            "reply_ids": [first_reply],
        },
    }


def _prefetch_dynamic_reply(npc_id: str, reply_id: str) -> None:
    try:
        synthesize_dynamic_reply(npc_id, reply_id)
    except Exception as exc:  # provider detail stays server-side
        print(f"[speech] tts prefetch failed for {npc_id}/{reply_id}: {type(exc).__name__}")


def synthesize_dynamic_reply(npc_id: str, reply_id: str, voice: str = "") -> bytes:
    record = _DYNAMIC_REPLIES.get(reply_id)
    if not record or str(record.get("npc_id", "")) != npc_id:
        raise KeyError(f"unknown npc reply: {npc_id}/{reply_id}")
    if not QWEN_TTS_API_KEY:
        raise RuntimeError("qwen tts is not configured")
    selected_voice = voice.strip() or QWEN_TTS_VOICE or NPC_TTS_VOICES.get(npc_id, "")
    if not selected_voice:
        raise RuntimeError("qwen tts has no voice configured")
    text = str(record["text"])
    reply_key = _tts_key(npc_id, reply_id, selected_voice)
    text_key = _tts_text_key(npc_id, selected_voice, text)
    keys = [reply_key, text_key]
    started = time.perf_counter()
    cached = _cached_wav(keys)
    if cached is not None:
        _log_stage("tts", int((time.perf_counter() - started) * 1000), npc=npc_id, reply=reply_id, cache=1, bytes=len(cached))
        return cached
    with _tts_fetch_lock(text_key):
        cached = _cached_wav(keys)
        if cached is not None:
            _log_stage("tts", int((time.perf_counter() - started) * 1000), npc=npc_id, reply=reply_id, cache=1, bytes=len(cached))
            return cached
        body = _dashscope_speech(text, selected_voice)
        if len(body) < 44 or len(body) > _TTS_MAX_BYTES:
            raise RuntimeError("qwen tts returned invalid audio size")
        stored = _store_wav(keys, body)
        _log_stage("tts", int((time.perf_counter() - started) * 1000), npc=npc_id, reply=reply_id, cache=0, bytes=len(stored))
        return stored


def _stream_dynamic_reply_audio(npc_id: str, reply_id: str):
    """Stream one spoken reply as raw PCM chunks for SSE audio events.

    Yields header-stripped chunks (24 kHz mono 16-bit). On completion the full
    repaired WAV is stored in the TTS cache so the /game/tts fallback and the
    JSON path still work; failures raise so the caller can emit audio_failed.
    """
    from dashscope.audio.tts_v2 import AudioFormat, ResultCallback

    record = _DYNAMIC_REPLIES.get(reply_id)
    if not record or str(record.get("npc_id", "")) != npc_id:
        raise KeyError(f"unknown npc reply: {npc_id}/{reply_id}")
    if not QWEN_TTS_API_KEY:
        raise RuntimeError("qwen tts is not configured")
    text = str(record["text"])
    selected_voice = str(record.get("voice", "")).strip() or QWEN_TTS_VOICE
    if not selected_voice:
        raise RuntimeError("qwen tts has no voice configured")
    chunks: queue.Queue = queue.Queue()
    state = {"error": None}
    started = time.perf_counter()

    class _StreamingCallback(ResultCallback):
        def on_open(self) -> None:
            return

        def on_complete(self) -> None:
            chunks.put(None)

        def on_error(self, message: str) -> None:
            state["error"] = RuntimeError(f"qwen tts stream failed: {str(message)[:160]}")
            chunks.put(None)

        def on_close(self) -> None:
            return

        def on_event(self, message: str) -> None:
            return

        def on_data(self, data: bytes) -> None:
            chunks.put(data)

    synthesizer = _tts_pool().borrow_synthesizer(
        model=QWEN_TTS_MODEL,
        voice=selected_voice,
        format=AudioFormat.WAV_24000HZ_MONO_16BIT,
        callback=_StreamingCallback(),
    )
    full = bytearray()
    pcm_offset = -1
    emitted = 0
    try:
        synthesizer.streaming_call(text)
        synthesizer.async_streaming_complete()
        while True:
            item = chunks.get(timeout=_TTS_STREAM_QUEUE_TIMEOUT)
            if item is None:
                break
            full += item
            if len(full) > _TTS_MAX_BYTES:
                raise RuntimeError("qwen tts stream exceeded size cap")
            if pcm_offset < 0:
                # The first frame carries the RIFF header; find the data chunk
                # before any PCM is yielded so the client gets bare samples.
                marker = bytes(full).find(b"data")
                if 4 <= marker <= 512:
                    pcm_offset = marker + 8
                elif len(full) > 2048:  # pragma: no cover - nonstandard header
                    pcm_offset = 44
            if pcm_offset >= 0:
                available = len(full) - pcm_offset
                target = (available // _TTS_STREAM_CHUNK_BYTES) * _TTS_STREAM_CHUNK_BYTES
                if target > emitted:
                    yield bytes(full[pcm_offset + emitted : pcm_offset + target])
                    emitted = target
        if state["error"] is not None:
            raise state["error"]
        if pcm_offset < 0 or len(full) - pcm_offset < 32:
            raise RuntimeError("qwen tts stream returned empty audio")
        if emitted < len(full) - pcm_offset:
            yield bytes(full[pcm_offset + emitted :])
        repaired = _repair_wav_lengths(bytes(full))
        keys = [_tts_key(npc_id, reply_id, selected_voice), _tts_text_key(npc_id, selected_voice, text)]
        _store_wav(keys, repaired)
        _log_stage(
            "tts_stream",
            int((time.perf_counter() - started) * 1000),
            npc=npc_id,
            reply=reply_id,
            bytes=len(full),
        )
    finally:
        _tts_pool().return_synthesizer(synthesizer)


def synthesize_npc_line(npc_id: str, line_id: str, voice: str = "", options: list[str] | None = None) -> bytes:
    """Synthesize one server-known NPC line with the configured Qwen TTS model.

    ``QWEN_TTS_API_KEY`` (or ``DASHSCOPE_API_KEY``) is read from the environment
    or TTS.csv and never returns to the caller. Missing key / upstream failure
    raises ``RuntimeError`` so the HTTP boundary can return 503 without exposing
    the provider detail to the game.
    """
    profile = NPC_LINES.get(npc_id or "")
    if not profile or line_id not in profile:
        raise KeyError(f"unknown npc line: {npc_id}/{line_id}")
    if not QWEN_TTS_API_KEY:
        raise RuntimeError("qwen tts is not configured")
    selected_voice = voice.strip() or QWEN_TTS_VOICE or NPC_TTS_VOICES.get(npc_id, "")
    if not selected_voice:
        raise RuntimeError("qwen tts has no voice configured")
    line_text = word_practice_ask_text(options or []) if line_id == "word_practice_ask" else profile[line_id]
    key = _tts_key(npc_id, line_id, selected_voice) + "/" + ",".join(options or [])
    started = time.perf_counter()
    with _TTS_CACHE_LOCK:
        cached = _TTS_CACHE.get(key)
    if cached is not None:
        _log_stage("tts", int((time.perf_counter() - started) * 1000), npc=npc_id, line=line_id, cache=1, bytes=len(cached))
        return cached
    try:
        body = _dashscope_speech(line_text, selected_voice)
    except Exception as exc:  # noqa: BLE001 - provider detail stays server-side
        print(f"[speech] qwen tts rejected line={npc_id}/{line_id} voice={selected_voice}: {type(exc).__name__}: {str(exc)[:120]}")
        raise RuntimeError("qwen tts request failed") from exc
    if len(body) < 44 or len(body) > _TTS_MAX_BYTES:
        raise RuntimeError("qwen tts returned invalid audio size")
    _log_stage("tts", int((time.perf_counter() - started) * 1000), npc=npc_id, line=line_id, cache=0, bytes=len(body))
    with _TTS_CACHE_LOCK:
        if len(_TTS_CACHE) >= 64:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[key] = body
    return body

# Word-practice catalog (FR-36). The client sends only a lexical ID; the
# reference text is server-authored and never free-form user input.
WORD_LINES = {
    "morning": "morning",
    "sleep": "sleep",
    "hungry": "hungry",
    "food": "food",
    "please": "please",
    "portions": "portions",
    "heater": "heater",
    "alloy": "alloy",
    "parts": "parts",
    "canteen": "canteen",
    "water": "water",
    "thirsty": "thirsty",
    "help": "help",
    "bring": "bring",
}

_model = None
_model_lock = threading.Lock()

# Reference scoring (optional, heavy): the desktop SSL+DTW stack is imported
# lazily and only when this interpreter can see it. Failures degrade to the
# Whisper-confidence proxy and are cached so we only probe once per process.
_ref_lock = threading.Lock()
_ref_ready: bool | None = None
_ref_cache: dict = {}
_word_ref_cache: dict = {}
_pipeline = None
_audio_io = None


def model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from faster_whisper import WhisperModel

                source = str(MODEL_DIR) if MODEL_DIR.is_dir() else "base.en"
                _model = WhisperModel(source, device="cpu", compute_type="int8")
    return _model


# --------------------------------------------------------------------------- #
# deterministic delivery judgement (FR-22 / FR-28 body)
# --------------------------------------------------------------------------- #


def normalise(text: str) -> str:
    """Whitespace normalisation only; grammar is never repaired or checked."""
    return " ".join(str(text or "").replace("’", "'").replace("‘", "'").split())


_HEARD_LOG_LIMIT = 200


def _log_line(message: str) -> None:
    print(message, flush=True)


def _log_stage(stage: str, ms: int, **fields: object) -> None:
    parts = [f"[speech] stage={stage}", f"ms={ms}"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        if key == "text":
            parts.append(f"text={normalise(str(value))!r}")
        else:
            parts.append(f"{key}={value}")
    _log_line(" ".join(parts))


def _url_fail_reason(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    detail = str(exc).lower()
    if "timed out" in detail or "timeout" in detail:
        return "timeout"
    return type(exc).__name__


def _log_heard(channel: str, text: str, **fields: object) -> None:
    clean = normalise(str(text or "")).replace("\n", " ").strip()
    if len(clean) > _HEARD_LOG_LIMIT:
        clean = clean[:_HEARD_LOG_LIMIT] + "..."
    parts = [f"[speech] heard channel={channel}", f"text={clean!r}"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    _log_line(" ".join(parts))


def accept_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern for one accept entry (phrase-safe)."""
    tokens = [t for t in normalise(term).split(" ") if t]
    if not tokens:
        raise ValueError("empty accept term")
    body = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE)


def match_slot(slot: dict, text: str) -> tuple[bool, list[str]]:
    matched: list[str] = []
    for term in slot.get("accept") or []:
        try:
            pattern = accept_pattern(term)
        except ValueError:
            continue
        if pattern.search(text):
            matched.append(term)
    return bool(matched), matched


def delivery_score(profile: dict, text: str) -> dict:
    """Deterministic slot verdict for one transcript.

    delivery = 85 * required-hit-rate + 15 * optional-hit-rate, mirroring the
    desktop Survival matcher (`game_scenario.py`) so the two implementations
    stay comparable.
    """
    clean = normalise(text)
    slots = []
    for slot in profile.get("slots") or []:
        hit, matched = match_slot(slot, clean)
        slots.append(
            {
                "key": slot.get("key", "?"),
                "required": bool(slot.get("required")),
                "hit": hit,
                "matched": matched,
            }
        )
    required = [s for s in slots if s["required"]]
    optional = [s for s in slots if not s["required"]]
    required_rate = sum(1 for s in required if s["hit"]) / len(required) if required else 0.0
    optional_rate = sum(1 for s in optional if s["hit"]) / len(optional) if optional else 0.0
    return {
        "slots": slots,
        "required_rate": round(required_rate, 4),
        "optional_rate": round(optional_rate, 4),
        "delivery": round(85.0 * required_rate + 15.0 * optional_rate, 1),
    }


def band_for_score(score: float) -> str:
    if score >= SCORE_GENEROUS_MIN:
        return "generous"
    if score >= SCORE_SPARSE_MIN:
        return "sparse"
    return "none"


# --------------------------------------------------------------------------- #
# pronunciation dimension
# --------------------------------------------------------------------------- #


def whisper_pronunciation(metrics: dict) -> float:
    """Acoustic-confidence proxy from faster-whisper metrics (0-100).

    This is deliberately labelled `whisper_confidence`: it measures how
    confidently the decoder recognised clear speech, not distance to a
    reference pronunciation. Logprob carries 70%, no-speech probability 30%.
    """
    avg_logprob = metrics.get("avg_logprob")
    no_speech_prob = metrics.get("no_speech_prob")

    def _clamp01(value: float, floor: float, ceil: float) -> float:
        if value is None:
            return 0.5
        return max(0.0, min(1.0, (float(value) - floor) / max(1e-9, ceil - floor)))

    lp = _clamp01(avg_logprob, _LOGP_FLOOR, _LOGP_CEIL)
    nsp = 1.0 - _clamp01(no_speech_prob, _NSP_FLOOR, _NSP_CEIL)
    word_mean = metrics.get("word_probability_mean")
    if word_mean is not None:
        wp = max(0.0, min(1.0, float(word_mean)))
        confidence = 0.4 * lp + 0.4 * wp + 0.2 * nsp
    else:
        confidence = 0.7 * lp + 0.3 * nsp
    return round(100.0 * confidence, 1)


def _repo_on_sys_path() -> None:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _ensure_reference_scorer() -> bool:
    """Try to import the desktop SSL+DTW stack exactly once."""
    global _ref_ready, _pipeline, _audio_io
    if _ref_ready is not None:
        return _ref_ready
    with _ref_lock:
        if _ref_ready is not None:
            return _ref_ready
        try:
            _repo_on_sys_path()
            from desktop.backend.core import audio_io, pipeline, ssl_encoder  # noqa: PLC0415

            # The service scores inside ThreadingHTTPServer worker threads.
            # Keep the SSL encoder on CPU: MPS/CUDA use from worker threads is
            # the cause of hard-to-diagnose process crashes on some machines,
            # and short utterances are comfortably fast on CPU after warm-up.
            ssl_encoder._select_device = lambda: "cpu"
            _audio_io = audio_io
            _pipeline = pipeline
            _ref_ready = True
        except Exception as exc:  # noqa: BLE001 - degrade, never block the game
            print(f"[speech] reference scorer unavailable: {type(exc).__name__}")
            _ref_ready = False
    return _ref_ready


def _synthesize_reference(text: str):
    """Deterministic 16 kHz mono reference for one intent.

    macOS `say` is used first (offline, out-of-process). Piper is attempted
    when available; otherwise None and the caller uses the Whisper proxy.
    """
    if sys.platform == "darwin":
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            subprocess.run(
                [
                    "/usr/bin/say",
                    "-v",
                    "Samantha",
                    "--file-format=WAVE",
                    "--data-format=LEI16@16000",
                    "-o",
                    tmp_path,
                    text,
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            return _audio_io.load_audio(tmp_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[speech] say synthesis failed: {type(exc).__name__}")
        finally:
            try:
                os.unlink(tmp_path)
            except (OSError, UnboundLocalError):
                pass
        return None

    try:
        from desktop.backend.core import piper_tts  # noqa: PLC0415

        voice = REPO_ROOT / "models" / "piper-libritts" / "en_US-libritts_r-medium.onnx"
        config = Path(str(voice) + ".json")
        if not config.is_file():
            return None
        piper_tts.load(str(voice))
        return piper_tts.synth_wav(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[speech] piper synthesis failed: {type(exc).__name__}")
        return None


def reference_pronunciation(target: str, wav_path: str) -> float | None:
    """SSL+DTW accuracy (0-100) against the bundled intent reference audio.

    The same WAVs are deployed with the cloud /game/evaluate endpoint, so dev
    and production score against identical references (FR-29 / R-18 G3).
    """
    if not _ensure_reference_scorer():
        return None
    profile = INTENTS.get(target)
    if profile is None:
        return None
    with _ref_lock:
        if target not in _ref_cache:
            bundled = REFERENCE_DIR / f"{target}.wav"
            if bundled.is_file():
                ref = _audio_io.load_audio(str(bundled))
            else:
                ref = _synthesize_reference(profile["reference"])
            if ref is None or len(ref) == 0:
                _ref_cache[target] = None
            else:
                _ref_cache[target] = ref
        ref = _ref_cache.get(target)
    if ref is None:
        return None
    try:
        learner = _audio_io.trim_silence(_audio_io.load_audio(wav_path))
        if learner.size == 0:
            return None
        result = _pipeline.analyze_arrays(ref, learner)
        accuracy = float(getattr(result, "accuracy", 0.0))
        return round(max(0.0, min(100.0, accuracy)), 1)
    except Exception as exc:  # noqa: BLE001 - fall back, never fail the request
        print(f"[speech] reference scoring failed: {type(exc).__name__}")
        return None


def _synthesize_word_reference(text: str):
    """Piper reference first (same voice contract as the cloud endpoint), then
    the offline platform synth as a development convenience."""
    try:
        _repo_on_sys_path()
        from desktop.backend.core import piper_tts  # noqa: PLC0415
        return piper_tts.synth_wav(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[speech] piper word reference unavailable: {type(exc).__name__}")
    return _synthesize_reference(text)


def word_pronunciation(lexical_id: str, wav_path: str) -> float | None:
    """SSL+DTW accuracy (0-100) for one server-catalog practice word."""
    if lexical_id not in WORD_LINES or not _ensure_reference_scorer():
        return None
    with _ref_lock:
        if lexical_id not in _word_ref_cache:
            ref = _synthesize_word_reference(WORD_LINES[lexical_id])
            _word_ref_cache[lexical_id] = ref if ref is not None and len(ref) else None
        ref = _word_ref_cache.get(lexical_id)
    if ref is None:
        return None
    try:
        learner = _audio_io.trim_silence(_audio_io.load_audio(wav_path))
        if learner.size == 0:
            return None
        result = _pipeline.analyze_arrays(ref, learner)
        return round(max(0.0, min(100.0, float(getattr(result, "accuracy", 0.0)))), 1)
    except Exception as exc:  # noqa: BLE001 - fall back, never fail the request
        print(f"[speech] word scoring failed: {type(exc).__name__}")
        return None


def score_word(lexical_id: str, wav_path: str) -> dict:
    heard = ""
    try:
        heard, metrics = _transcribe_with_hotwords(wav_path, None)
    except Exception as exc:  # noqa: BLE001 - logging must not fail scoring
        print(f"[speech] heard-log transcribe failed: {type(exc).__name__}")
        metrics = {}
    _log_heard("score_word", heard, lexical_id=lexical_id)
    pronunciation = word_pronunciation(lexical_id, wav_path)
    source = "reference_dtw"
    if pronunciation is None:
        # Whisper-confidence proxy is explicitly labelled and is only used when
        # the local SSL stack cannot be imported (same contract as FR-28).
        clean = normalise(heard)
        pronunciation = 80.0 if clean == WORD_LINES.get(lexical_id, "") or clean.split() == WORD_LINES.get(lexical_id, "").split() else 20.0
        source = "whisper_confidence"
    score = pronunciation
    band = band_for_score(score)
    return {
        "accepted": band != "none",
        "text": WORD_LINES[lexical_id],
        "heard": heard,
        "reason": "VOICE_REASON_ACCEPTED" if band != "none" else "VOICE_REASON_SCORE_LOW",
        "pronunciation": pronunciation,
        "score": score,
        "pronunciation_source": source,
        "band": band,
    }


def match_word_choice(text: str, options: list[str]) -> str:
    """One spoken option from the transcript; ambiguous or missing is clarify."""
    clean = normalise(text)
    tokens = clean.split(" ")
    matches: list[str] = []
    for option in options:
        target = WORD_LINES.get(option, "").split(" ")
        if all(token in tokens for token in target):
            matches.append(option)
    if len(matches) != 1:
        return ""
    return matches[0]


def score_word_choice(options: list[str], wav_path: str) -> dict:
    clean_options = [option for option in options if option in WORD_LINES]
    if not clean_options:
        raise KeyError("empty practice options")
    text, _metrics = _transcribe_with_hotwords(wav_path, None)
    _log_heard("score_word_choice", text, options=",".join(clean_options))
    matched = match_word_choice(text, clean_options)
    if matched == "":
        return {
            "accepted": False,
            "text": text,
            "heard": text,
            "reason": "VOICE_REASON_CLARIFY",
            "lexical_id": "",
            "pronunciation": 0.0,
            "score": 0.0,
            "pronunciation_source": "none",
            "band": "none",
        }
    verdict = score_word(matched, wav_path)
    verdict["lexical_id"] = matched
    verdict["text"] = text
    verdict["heard"] = text
    return verdict


def judge(target: str, text: str, wav_path: str | None, metrics: dict | None) -> dict:
    profile = INTENTS.get(target, {})
    verdict = delivery_score(profile, text) if profile else {
        "slots": [],
        "required_rate": 0.0,
        "optional_rate": 0.0,
        "delivery": 0.0,
    }
    pronunciation = None
    source = "whisper_confidence"
    if wav_path:
        pronunciation = reference_pronunciation(target, wav_path)
        if pronunciation is not None:
            source = "reference_dtw"
    if pronunciation is None:
        pronunciation = whisper_pronunciation(metrics or {})
    delivery = float(verdict["delivery"])
    score = round(0.5 * pronunciation + 0.5 * delivery, 1)
    band = band_for_score(score)
    return {
        "pronunciation": pronunciation,
        "delivery": delivery,
        "score": score,
        "pronunciation_source": source,
        "band": band,
        **verdict,
    }


# --------------------------------------------------------------------------- #
# transcription
# --------------------------------------------------------------------------- #


def transcribe(wav_path: str) -> tuple[str, dict]:
    profile = None  # hotwords stay per-intent at the handler level
    return _transcribe_with_hotwords(wav_path, profile)


def _transcribe_with_hotwords(wav_path: str, target: str | None, fast: bool = False) -> tuple[str, dict]:
    profile = INTENTS.get(target or "", {})
    hotwords = None
    if profile:
        terms: list[str] = []
        for slot in profile.get("slots") or []:
            for term in slot.get("accept") or []:
                cleaned = normalise(term)
                if cleaned and cleaned not in terms:
                    terms.append(cleaned)
        hotwords = " ".join(terms) if terms else None
    segments, _info = model().transcribe(
        wav_path,
        language="en",
        beam_size=1 if fast else 5,
        vad_filter=False,
        condition_on_previous_text=False,
        word_timestamps=not fast,
        hotwords=hotwords or None,
    )
    parts: list[str] = []
    logprobs: list[float] = []
    no_speech: list[float] = []
    word_probs: list[float] = []
    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        if text:
            parts.append(text)
        lp = getattr(segment, "avg_logprob", None)
        if lp is not None:
            logprobs.append(float(lp))
        ns = getattr(segment, "no_speech_prob", None)
        if ns is not None:
            no_speech.append(float(ns))
        for word in getattr(segment, "words", None) or []:
            prob = getattr(word, "probability", None)
            if prob is not None:
                word_probs.append(float(prob))
    metrics = {
        "avg_logprob": round(sum(logprobs) / len(logprobs), 4) if logprobs else None,
        "no_speech_prob": round(max(no_speech), 4) if no_speech else None,
        "word_probability_mean": round(sum(word_probs) / len(word_probs), 4) if word_probs else None,
    }
    return " ".join(parts).strip(), metrics


# --------------------------------------------------------------------------- #
# HTTP boundary
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    server_version = "StrangerSpeech/2"

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self._json(200, {
            "ok": True,
            "model": str(MODEL_DIR),
            "protocol": 2,
            "dialogue_model": _dialogue_model_name(),
            "dialogue_configured": _dialogue_llm_configured(),
            "dialogue_provider": "gemini" if _gemini_api_key() else ("grok" if _xai_api_key() else "stub"),
        })

    def do_POST(self):
        if self.path == "/game/dialogue":
            self._handle_dialogue()
            return
        if self.path == "/game/prewarm":
            self._handle_prewarm()
            return
        if self.path in ("/tts", "/game/tts"):
            self._handle_tts()
            return
        if self.path in ("/score_word", "/game/score_word"):
            self._handle_word_score()
            return
        if self.path != "/transcribe":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 44 or length > 8 * 1024 * 1024:
            self._json(400, self._failure("VOICE_REASON_LENGTH"))
            return
        target = self.headers.get("X-Stranger-Target", "")
        fast = self.headers.get("X-Stranger-Fast", "").strip() == "1"
        payload = self.rfile.read(length)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
                temp.write(payload)
                temp_path = temp.name
            started = time.perf_counter()
            text, metrics = _transcribe_with_hotwords(temp_path, target, fast=fast)
            transcribe_ms = int((time.perf_counter() - started) * 1000)
            _log_stage("transcribe", transcribe_ms, fast=int(fast), target=target)
            _log_heard("transcribe", text, target=target, fast=int(fast), ms=transcribe_ms)
            if not normalise(text):
                self._json(200, {**self._failure("VOICE_REASON_CLARIFY"), "text": "", "heard": ""})
                return
            if fast:
                pronunciation = whisper_pronunciation(metrics)
                verdict = {
                    "pronunciation": pronunciation,
                    "delivery": 100.0,
                    "score": pronunciation,
                    "pronunciation_source": "whisper_confidence",
                    "band": band_for_score(pronunciation),
                    "slots": [],
                }
            else:
                verdict = judge(target, text, temp_path, metrics)
            accepted = verdict["band"] != "none"
            reason = "VOICE_REASON_ACCEPTED" if accepted else "VOICE_REASON_SCORE_LOW"
            self._json(
                200,
                {
                    "accepted": accepted,
                    "text": text,
                    "reason": reason,
                    "pronunciation": verdict["pronunciation"],
                    "delivery": verdict["delivery"],
                    "score": verdict["score"],
                    "pronunciation_source": verdict["pronunciation_source"],
                    "band": verdict["band"],
                    "slots": verdict["slots"],
                },
            )
        except Exception as exc:  # service boundary: log detail, return a localizable safe result
            print(f"[speech] transcription failed: {type(exc).__name__}")
            self._json(503, self._failure("VOICE_REASON_SERVICE_UNAVAILABLE"))
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def _wants_sse(self) -> bool:
        return "text/event-stream" in (self.headers.get("Accept") or "").lower()

    def _write_sse(self, event: str, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        block = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
        # Chunked framing: Godot's HTTP stack never completes a body that has
        # neither Content-Length nor Transfer-Encoding, so raw close-delimited
        # writes would leave the client stuck before the first event.
        self.wfile.write(b"%x\r\n%s\r\n" % (len(block), block))
        self.wfile.flush()

    def _end_sse(self) -> None:
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_dialogue(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 256 * 1024:
            self._json(400, {"ok": False, "reason": "VOICE_REASON_LENGTH"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("dialogue body must be an object")
            if self._wants_sse():
                self._sse_dialogue(body)
                return
            self._json(200, generate_dialogue_reply(body))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            reason = "VOICE_REASON_DIALOGUE_REJECTED" if "quality gate" in str(exc) else "VOICE_REASON_RESULT_INVALID"
            self._json(422 if reason == "VOICE_REASON_DIALOGUE_REJECTED" else 400, {"ok": False, "reason": reason})
        except Exception as exc:  # service boundary: provider detail never reaches Godot
            print(f"[dialogue] request failed: {type(exc).__name__}")
            self._json(503, {"ok": False, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"})

    def _sse_dialogue(self, body: dict) -> None:
        try:
            stream = iter_dialogue_events(body)
            first = next(stream)
        except ValueError as exc:
            reason = "VOICE_REASON_DIALOGUE_REJECTED" if "quality gate" in str(exc) else "VOICE_REASON_RESULT_INVALID"
            self._json(422 if reason == "VOICE_REASON_DIALOGUE_REJECTED" else 400, {"ok": False, "reason": reason})
            return
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.close_connection = True
        self._write_sse(first["event"], first["data"])
        try:
            for item in stream:
                self._write_sse(item["event"], item["data"])
        except Exception as exc:  # noqa: BLE001 — keep the Godot stream from hanging
            print(f"[dialogue] sse failed: {type(exc).__name__}")
            self._write_sse("error", {"ok": False, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"})
        finally:
            self._end_sse()

    def _handle_prewarm(self) -> None:
        """V-press prewarm: keep the TTS websocket pool warm while the player
        is still speaking. Fire-and-forget by contract; never fails hard."""
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 4096:
            self._json(400, {"ok": False, "reason": "VOICE_REASON_LENGTH"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        if body and not isinstance(body, dict):
            body = {}
        warmed = False
        try:
            warmed = _prewarm_tts_pool()
        except Exception as exc:  # noqa: BLE001 - prewarm stays best effort
            print(f"[speech] prewarm failed: {type(exc).__name__}")
        self._json(200, {"ok": True, "tts_pool": warmed})

    def _handle_word_score(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 44 or length > 8 * 1024 * 1024:
            self._json(400, self._word_failure("VOICE_REASON_LENGTH"))
            return
        lexical_header = self.headers.get("X-Stranger-Lexical", "").strip().lower()
        lexical_ids = [item.strip() for item in lexical_header.split(",") if item.strip()]
        if not lexical_ids or any(item not in WORD_LINES for item in lexical_ids):
            self._json(404, self._word_failure("VOICE_REASON_RESULT_INVALID"))
            return
        payload = self.rfile.read(length)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
                temp.write(payload)
                temp_path = temp.name
            if len(lexical_ids) == 1:
                verdict = score_word(lexical_ids[0], temp_path)
                verdict["lexical_id"] = lexical_ids[0]
            else:
                verdict = score_word_choice(lexical_ids, temp_path)
            self._json(200, verdict)
        except Exception as exc:  # service boundary: log detail, never expose provider detail
            print(f"[speech] word scoring failed: {type(exc).__name__}")
            self._json(503, self._word_failure("VOICE_REASON_SERVICE_UNAVAILABLE"))
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    @staticmethod
    def _word_failure(reason: str) -> dict:
        return {
            "accepted": False,
            "text": "",
            "reason": reason,
            "pronunciation": 0.0,
            "score": 0.0,
            "pronunciation_source": "none",
            "band": "none",
        }

    def _handle_tts(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 64 * 1024:
            self._json(400, {"ok": False, "reason": "VOICE_REASON_LENGTH"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
            return
        npc_id = str(body.get("npc_id", "")).strip().lower()
        reply_id = str(body.get("reply_id", "")).strip()
        line_id = str(body.get("line_id", "")).strip().lower()
        voice = str(body.get("voice", "")).strip()
        raw_options = body.get("options") or []
        options = [str(item).strip().lower() for item in raw_options if str(item).strip()]
        if reply_id:
            try:
                wav_body = synthesize_dynamic_reply(npc_id, reply_id, voice)
            except KeyError:
                print(f"[speech] tts unknown reply {npc_id}/{reply_id}", flush=True)
                self._json(404, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
                return
            except Exception as exc:  # provider key/network/format failure
                print(f"[speech] dynamic tts unavailable for {npc_id}/{reply_id}: {type(exc).__name__}")
                self._json(503, {"ok": False, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_body)))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.end_headers()
            self.wfile.write(wav_body)
            return
        if npc_id not in NPC_LINES or line_id not in NPC_LINES[npc_id]:
            self._json(404, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
            return
        if line_id == "word_practice_ask" and not options:
            self._json(400, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
            return
        try:
            wav_body = synthesize_npc_line(npc_id, line_id, voice, options)
        except KeyError:
            self._json(404, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
            return
        except Exception as exc:  # provider key/network/format failure: safe local fallback
            print(f"[speech] tts unavailable for {npc_id}/{line_id}: {type(exc).__name__}")
            self._json(503, {"ok": False, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_body)))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(wav_body)

    @staticmethod
    def _failure(reason: str) -> dict:
        return {
            "accepted": False,
            "text": "",
            "reason": reason,
            "pronunciation": 0.0,
            "delivery": 0.0,
            "score": 0.0,
            "pronunciation_source": "none",
            "band": "none",
            "slots": [],
        }

    def log_message(self, fmt: str, *args) -> None:
        print(f"[speech] {self.address_string()} {fmt % args}", flush=True)

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _prewarm() -> None:
    """Warm models off the request path so the first interaction is not a
    surprise 20-second wait. Failures only disable a dimension, never the
    service."""
    try:
        model()
        print("[speech] whisper ready", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[speech] whisper prewarm failed: {type(exc).__name__}", flush=True)
    try:
        if _ensure_reference_scorer():
            bundled = REFERENCE_DIR / "tavi.wav"
            ref = _audio_io.load_audio(str(bundled)) if bundled.is_file() else _synthesize_reference(INTENTS["tavi"]["reference"])
            if ref is not None and len(ref):
                _pipeline.analyze_arrays(ref, ref)
                print("[speech] reference scorer ready", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[speech] reference prewarm failed: {type(exc).__name__}", flush=True)
    try:
        if _prewarm_tts_pool():
            print("[speech] tts pool ready", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[speech] tts pool prewarm failed: {type(exc).__name__}", flush=True)


def _probe_gemini() -> None:
    """One startup reachability probe; also warms the shared session's proxy
    connection so the first real dialogue skips TCP+TLS setup."""
    if not _gemini_api_key():
        return
    session = _gemini_session()
    if session is None:  # pragma: no cover - deployment without requests
        return
    started = time.perf_counter()
    try:
        session.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": _gemini_api_key()},
            timeout=4.0,
        )
        _log_stage(
            "gemini_probe",
            int((time.perf_counter() - started) * 1000),
            proxy=os.environ.get("HTTPS_PROXY", ""),
        )
    except Exception as exc:  # noqa: BLE001 - probe failure is diagnostic only
        _log_stage("gemini_probe", 0, reason=_url_fail_reason(exc))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    print(f"Stranger speech service listening on http://{HOST}:{PORT}", flush=True)
    threading.Thread(target=_prewarm, daemon=True).start()
    threading.Thread(target=_probe_gemini, daemon=True).start()
    service = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        print("Stranger speech service stopped.")
    finally:
        service.server_close()
