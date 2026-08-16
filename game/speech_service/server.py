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
        "greeting": "Hey, little one. Come to the market. No need to be afraid.",
        "social_greeting": "Good morning. Did you sleep well?",
        "social_reply_food": "Of course. Take two portions.",
    },
    "rowan": {
        "greeting": "You look tired. Find water and warmth first.",
        "social_reply_water": "I am thirsty too. Bring me water, please.",
        "social_ask_help": "I cannot walk far. Could you bring me water?",
    },
    "tavi": {
        "greeting": "Hungry? Tell me once you are settled.",
        "social_reply_greeting": "I slept. Are you hungry?",
        "social_ask_food": "Can I have some food, please?",
    },
    "vesh": {
        "greeting": "Cold nights are coming. Ask me for alloy parts.",
        "social_ask_scrap": "The heater needs two alloy parts. Do you have any?",
    },
    "ori": {
        "greeting": "I keep the water. Ask me when you need it.",
        "social_reply_scrap": "I have one. Ask Tavi for the other.",
        "social_ask_water": "I need a canteen of water.",
        "social_reply_help": "I will ask the little one to help.",
    },
}

QWEN_TTS_MODEL = os.environ.get("QWEN_TTS_MODEL", "qwen-audio-3.0-tts-plus")
QWEN_TTS_VOICE = os.environ.get("QWEN_TTS_VOICE", "Cherry")
QWEN_TTS_BASE_URL = os.environ.get(
    "QWEN_TTS_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/audio/speech",
)
QWEN_TTS_API_KEY = os.environ.get("QWEN_TTS_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
_TTS_CACHE: dict[str, bytes] = {}
_TTS_CACHE_LOCK = threading.Lock()
_TTS_MAX_BYTES = 2 * 1024 * 1024


def _tts_key(npc_id: str, line_id: str, voice: str) -> str:
    return f"{npc_id}/{line_id}/{voice}"


def synthesize_npc_line(npc_id: str, line_id: str, voice: str = "") -> bytes:
    """Synthesize one server-known NPC line with the configured Qwen TTS model.

    ``QWEN_TTS_API_KEY`` (or ``DASHSCOPE_API_KEY``) is read from the environment
    and never returns to the caller. Missing key / upstream failure raises
    ``RuntimeError`` so the HTTP boundary can return 503 without exposing the
    provider detail to the game.
    """
    profile = NPC_LINES.get(npc_id or "")
    if not profile or line_id not in profile:
        raise KeyError(f"unknown npc line: {npc_id}/{line_id}")
    if not QWEN_TTS_API_KEY:
        raise RuntimeError("qwen tts is not configured")
    selected_voice = voice.strip() or QWEN_TTS_VOICE
    key = _tts_key(npc_id, line_id, selected_voice)
    with _TTS_CACHE_LOCK:
        cached = _TTS_CACHE.get(key)
    if cached is not None:
        return cached
    payload = {
        "model": QWEN_TTS_MODEL,
        "input": profile[line_id],
        "voice": selected_voice,
        "response_format": "wav",
    }
    request = urllib.request.Request(
        QWEN_TTS_BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + QWEN_TTS_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            body = raw
            # DashScope may answer with a JSON job descriptor containing a
            # presigned audio URL instead of raw WAV bytes. Accept both shapes;
            # the game still only ever receives audio/wav.
            if raw.lstrip().startswith(b"{"):
                descriptor = json.loads(raw.decode("utf-8", "replace"))
                audio_url = (
                    ((descriptor.get("output") or {}).get("audio") or {}).get("url")
                    or descriptor.get("audio_url")
                )
                if not audio_url:
                    raise RuntimeError("qwen tts returned json without audio url")
                with urllib.request.urlopen(str(audio_url), timeout=30) as audio_response:
                    body = audio_response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(256).decode("utf-8", "replace")
        except OSError:
            pass
        print(f"[speech] qwen tts rejected line={npc_id}/{line_id} status={exc.code} {detail[:120]}")
        raise RuntimeError("qwen tts request failed") from exc
    except OSError as exc:
        print(f"[speech] qwen tts unreachable line={npc_id}/{line_id}: {type(exc).__name__}")
        raise RuntimeError("qwen tts request failed") from exc
    if len(body) < 44 or len(body) > _TTS_MAX_BYTES:
        raise RuntimeError("qwen tts returned invalid audio size")
    with _TTS_CACHE_LOCK:
        if len(_TTS_CACHE) >= 64:
            _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
        _TTS_CACHE[key] = body
    return body

_model = None
_model_lock = threading.Lock()

# Reference scoring (optional, heavy): the desktop SSL+DTW stack is imported
# lazily and only when this interpreter can see it. Failures degrade to the
# Whisper-confidence proxy and are cached so we only probe once per process.
_ref_lock = threading.Lock()
_ref_ready: bool | None = None
_ref_cache: dict = {}
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
        if npc_id not in NPC_LINES or line_id not in NPC_LINES[npc_id]:
            self._json(404, {"ok": False, "reason": "VOICE_REASON_RESULT_INVALID"})
            return
        try:
            wav_body = synthesize_npc_line(npc_id, line_id, voice)
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
