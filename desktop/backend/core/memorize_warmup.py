"""On-demand prefetch of the Memorizing module's models (FR-13..15, NFR-5).

Unlike the Speaking path (warmup.py, which runs at process startup), the
Memorizing models -- a ~6GB VLM and a small LLM -- are only loaded when the user
actually opens the Memorize tab, so cold-start memory and a multi-GB download
never penalize a user who only does shadowing. The frontend calls
``POST /memorize/warmup`` on tab-enter and polls ``GET /memorize/status``; on
tab-leave it calls ``POST /memorize/release`` to free the big models.

Structural clone of warmup.py: module-level lock + status dict, idempotent
``start()`` (no-op under pytest), best-effort daemon thread. Stage order is
yolo (tiny, bundled, instant) -> llm (cheap scenario win) -> vlm (largest).
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_status: dict = {
    "running": False,
    "stage": "idle",  # idle | yolo | llm | vlm | done | error
    "yolo_ready": False,
    "llm_ready": False,
    "vlm_ready": False,
    "error": None,
}


def status() -> dict:
    with _lock:
        return dict(_status)


def _set(**kw) -> None:
    with _lock:
        _status.update(kw)


def _run() -> None:
    try:
        _set(running=True, stage="yolo")
        from backend.core import vision
        vision._load()                 # yolov8n-onnx (~12MB, bundled -> instant)
        _set(yolo_ready=True, stage="llm")
        from backend.core import scenario
        scenario._load()               # Qwen2.5-Instruct (~1-3GB)
        _set(llm_ready=True, stage="vlm")
        from backend.core import parts
        parts._load()                  # Qwen2.5-VL-3B (~6GB)
        _set(vlm_ready=True, stage="done", running=False)
    except Exception as e:  # noqa: BLE001 -- prefetch must never break the app
        _set(stage="error", running=False, error=str(e))


def start() -> None:
    """Start the on-demand prefetch once. Idempotent; no-op if already done or
    running under pytest (avoids a multi-GB download + races with tests)."""
    import sys
    if "pytest" in sys.modules:
        _status["stage"] = "done"
        return
    with _lock:
        if _status["running"] or _status["stage"] in ("done", "error"):
            return
        _status["running"] = True
    threading.Thread(target=_run, daemon=True, name="nl-memorize-warmup").start()
