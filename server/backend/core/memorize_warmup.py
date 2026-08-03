"""On-demand lifecycle for the Memorizing models (FR-13..17, NFR-5).

Loading runs yolo -> Qwen GGUF -> Florence -> Piper only after the user
enters the module.  A generation token makes tab exit safe even while a large
model is still downloading/loading: stale workers unload what they just
acquired rather than repopulating caches after ``release()``.
"""
from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_generation = 0


def _initial_status() -> dict:
    return {
        "running": False,
        "stage": "idle",  # idle | yolo | llm | florence | piper | done | error
        "yolo_ready": False,
        "llm_ready": False,
        "florence_ready": False,
        "piper_ready": False,
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
        if not _advance(token, florence_ready=True, stage="piper"):
            parts.unload()
            scenario.unload()
            return

        from backend.core import model_assets, piper_tts

        if piper_tts.uses_system_voice():
            piper_tts.load("")
        else:
            onnx_path = model_assets.download_verified(
                model_assets.PIPER_REPO,
                model_assets.PIPER_FILENAME,
                model_assets.PIPER_REVISION,
                model_assets.PIPER_SIZE,
                model_assets.PIPER_SHA256,
            )
            # The small .onnx.json config sits beside the weights in the same
            # snapshot dir; fetch it unverified (Piper loads it by suffix).
            if not os.path.exists(onnx_path + ".json"):
                from huggingface_hub import hf_hub_download

                hf_hub_download(
                    model_assets.PIPER_REPO,
                    model_assets.PIPER_CONFIG_FILENAME,
                    revision=model_assets.PIPER_REVISION,
                )
            piper_tts.load(onnx_path)
        if not _advance(token, piper_ready=True, stage="done", running=False, error=None):
            parts.unload()
            scenario.unload()
            piper_tts.unload()
            return

        # FR-17 shadow scoring reuses the Speaking SSL encoder. Warm it
        # best-effort so the first /memorize/pronounce call usually avoids the
        # 15s deadline on a cold ~360MB wav2vec2 load. get_encoder() is locked
        # + idempotent; a failure here must not regress the "done" status —
        # shadow scoring still works via the normal retry path.
        try:
            from backend.core import pipeline

            pipeline.get_encoder()
        except Exception:  # noqa: BLE001 -- best-effort warm-up
            pass
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
    """Cancel the active generation and unload Florence + Qwen + Piper."""
    global _generation
    with _lock:
        _generation += 1
        _status.clear()
        _status.update(_initial_status())

    # Do not hold the lifecycle lock while destructors/Metal cleanup run.
    from backend.core import parts, scenario, piper_tts

    parts.unload()
    scenario.unload()
    piper_tts.unload()
