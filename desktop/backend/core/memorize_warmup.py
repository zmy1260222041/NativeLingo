"""On-demand lifecycle for the Memorizing models (FR-13..15, NFR-5).

Loading runs yolo -> Qwen GGUF -> Florence only after the user enters the
module.  A generation token makes tab exit safe even while a large model is
still downloading/loading: stale workers unload what they just acquired rather
than repopulating caches after ``release()``.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_generation = 0


def _initial_status() -> dict:
    return {
        "running": False,
        "stage": "idle",  # idle | yolo | llm | florence | done | error
        "yolo_ready": False,
        "llm_ready": False,
        "florence_ready": False,
        "error": None,
    }


_status = _initial_status()


def status() -> dict:
    with _lock:
        return dict(_status)


def _advance(token: int, **updates) -> bool:
    with _lock:
        if token != _generation:
            return False
        _status.update(updates)
        return True


def _run(token: int) -> None:
    try:
        from backend.core import vision

        vision._load()
        if not _advance(token, yolo_ready=True, stage="llm"):
            return

        from backend.core import scenario

        scenario._load()
        if not _advance(token, llm_ready=True, stage="florence"):
            scenario.unload()
            return

        from backend.core import parts

        parts._load()
        if not _advance(
            token,
            florence_ready=True,
            stage="done",
            running=False,
            error=None,
        ):
            parts.unload()
            scenario.unload()
    except Exception as exc:  # noqa: BLE001 -- prefetch must not crash the app
        _advance(token, stage="error", running=False, error=str(exc))


def start() -> None:
    """Start or retry the staged warmup. Calls are idempotent while active."""
    global _generation
    with _lock:
        if _status["running"] or _status["stage"] == "done":
            return
        _generation += 1
        token = _generation
        _status.clear()
        _status.update(_initial_status())
        _status.update(running=True, stage="yolo")
    threading.Thread(
        target=_run,
        args=(token,),
        daemon=True,
        name=f"nl-memorize-warmup-{token}",
    ).start()


def release() -> None:
    """Cancel the active generation and unload Florence + Qwen."""
    global _generation
    with _lock:
        _generation += 1
        _status.clear()
        _status.update(_initial_status())

    # Do not hold the lifecycle lock while destructors/Metal cleanup run.
    from backend.core import parts, scenario

    parts.unload()
    scenario.unload()
