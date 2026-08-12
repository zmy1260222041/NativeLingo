"""Offline localhost speech adapter for Stranger's key social intents."""
from __future__ import annotations

import json
import os
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 17831
MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "whisper-base.en"

INTENTS = {
    "mira": ({"hello", "hi", "morning", "friend", "mira"}, "greeting"),
    "rowan": ({"help", "water", "brought", "bring", "carry", "rowan"}, "help offer"),
}

_model = None


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        source = str(MODEL_DIR) if MODEL_DIR.is_dir() else "base.en"
        _model = WhisperModel(source, device="cpu", compute_type="int8")
    return _model


def transcribe(wav_path: str) -> str:
    segments, _info = model().transcribe(
        wav_path,
        language="en",
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
        word_timestamps=False,
        hotwords="hello hi help water bring friend",
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def classify(target: str, text: str) -> tuple[bool, str]:
    words = set(re.findall(r"[a-z']+", text.lower()))
    terms, _label = INTENTS.get(target, (set(), "social intent"))
    if words & terms:
        return True, "VOICE_REASON_ACCEPTED"
    return False, "VOICE_REASON_CLARIFY"


class Handler(BaseHTTPRequestHandler):
    server_version = "StrangerSpeech/1"

    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self._json(200, {"ok": True, "model": str(MODEL_DIR), "protocol": 1})

    def do_POST(self):
        if self.path != "/transcribe":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 44 or length > 8 * 1024 * 1024:
            self._json(400, {"accepted": False, "text": "", "reason": "VOICE_REASON_LENGTH"})
            return
        target = self.headers.get("X-Stranger-Target", "")
        payload = self.rfile.read(length)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
                temp.write(payload)
                temp_path = temp.name
            text = transcribe(temp_path)
            accepted, reason = classify(target, text)
            self._json(200, {"accepted": accepted, "text": text, "reason": reason})
        except Exception as exc:  # service boundary: log detail, return a localizable safe result
            print(f"[speech] transcription failed: {type(exc).__name__}")
            self._json(503, {"accepted": False, "text": "", "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"})
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def log_message(self, fmt: str, *args) -> None:
        print(f"[speech] {self.address_string()} {fmt % args}")

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Stranger speech service listening on http://{HOST}:{PORT}")
    service = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        print("Stranger speech service stopped.")
    finally:
        service.server_close()
