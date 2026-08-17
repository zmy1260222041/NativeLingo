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

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 17831
MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "whisper-base.en"
REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = Path(__file__).resolve().parent / "reference_audio"

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
_TTS_MAX_BYTES = 2 * 1024 * 1024


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
    return audio


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
    with _TTS_CACHE_LOCK:
        cached = _TTS_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        body = _dashscope_speech(line_text, selected_voice)
    except Exception as exc:  # noqa: BLE001 - provider detail stays server-side
        print(f"[speech] qwen tts rejected line={npc_id}/{line_id} voice={selected_voice}: {type(exc).__name__}: {str(exc)[:120]}")
        raise RuntimeError("qwen tts request failed") from exc
    if len(body) < 44 or len(body) > _TTS_MAX_BYTES:
        raise RuntimeError("qwen tts returned invalid audio size")
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
    pronunciation = word_pronunciation(lexical_id, wav_path)
    source = "reference_dtw"
    if pronunciation is None:
        # Whisper-confidence proxy is explicitly labelled and is only used when
        # the local SSL stack cannot be imported (same contract as FR-28).
        text, metrics = _transcribe_with_hotwords(wav_path, None)
        clean = normalise(text)
        pronunciation = 80.0 if clean == WORD_LINES.get(lexical_id, "") or clean.split() == WORD_LINES.get(lexical_id, "").split() else 20.0
        source = "whisper_confidence"
    score = pronunciation
    band = band_for_score(score)
    return {
        "accepted": band != "none",
        "text": WORD_LINES[lexical_id],
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
    matched = match_word_choice(text, clean_options)
    if matched == "":
        return {
            "accepted": False,
            "text": text,
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


def _transcribe_with_hotwords(wav_path: str, target: str | None) -> tuple[str, dict]:
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
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
        word_timestamps=True,
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
        self._json(200, {"ok": True, "model": str(MODEL_DIR), "protocol": 2})

    def do_POST(self):
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
        payload = self.rfile.read(length)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
                temp.write(payload)
                temp_path = temp.name
            text, metrics = _transcribe_with_hotwords(temp_path, target)
            if not normalise(text):
                self._json(200, {**self._failure("VOICE_REASON_CLARIFY"), "text": ""})
                return
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
        line_id = str(body.get("line_id", "")).strip().lower()
        voice = str(body.get("voice", "")).strip()
        raw_options = body.get("options") or []
        options = [str(item).strip().lower() for item in raw_options if str(item).strip()]
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
        print(f"[speech] {self.address_string()} {fmt % args}")

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


if __name__ == "__main__":
    print(f"Stranger speech service listening on http://{HOST}:{PORT}", flush=True)
    threading.Thread(target=_prewarm, daemon=True).start()
    service = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        print("Stranger speech service stopped.")
    finally:
        service.server_close()
