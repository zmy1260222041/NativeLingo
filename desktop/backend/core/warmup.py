"""Background prefetch of the heavy analysis models.

The frozen app lazily downloads the models it needs. The encoder (wav2vec2,
~360MB) loads on first ``/health`` (the frontend polls it at startup). The
other two — MMS forced alignment (~1.2GB) and the phoneme CTC model (~2.4GB) —
are only touched on the first ``/analyze_video``, which is why the first
"分析发音" blocks for minutes on a network download.

This module front-loads those two in a daemon thread right after startup, so
by the time the user has picked a video and shadowed a sentence, the models
are usually already cached. ``/warmup`` exposes the progress so the frontend
can show what's happening instead of a blind spinner.

Prefetch is best-effort: if it fails (no network, etc.) the analyze path still
works — it just downloads on demand as before.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_status: dict = {
    "running": False,
    "stage": "idle",  # idle | encoder | mms | phoneme | done | error
    "encoder_ready": False,
    "mms_ready": False,
    "phoneme_ready": False,
    "error": None,
}


def status() -> dict:
    """Snapshot of prefetch progress for the /warmup endpoint."""
    with _lock:
        return dict(_status)


def _set(**kw) -> None:
    with _lock:
        _status.update(kw)


def _run() -> None:
    try:
        _set(running=True, stage="encoder")
        from backend.core.pipeline import get_encoder
        get_encoder()                       # wav2vec2-base-960h (~360MB)
        _set(encoder_ready=True, stage="mms")
        from backend.core import forced_align
        forced_align._get_state()           # torchaudio MMS_FA (~1.2GB)
        _set(mms_ready=True, stage="phoneme")
        from backend.core import phoneme
        phoneme._load()                     # wav2vec2 espeak-cv-ft (~2.4GB)
        _set(phoneme_ready=True, stage="done", running=False)
    except Exception as e:  # noqa: BLE001 — prefetch must never break the app
        _set(stage="error", running=False, error=str(e))


def start() -> None:
    """Start the background prefetch once. Idempotent; no-op if already done
    or running under pytest (avoids a multi-GB download + races with tests)."""
    import sys
    if "pytest" in sys.modules:
        _status["stage"] = "done"  # pretend ready so the frontend doesn't wait
        return
    with _lock:
        if _status["running"] or _status["stage"] in ("done", "error"):
            return
        _status["running"] = True
    threading.Thread(target=_run, daemon=True, name="nl-warmup").start()
