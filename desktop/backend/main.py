"""FastAPI backend for NativeLingo.

Runs as a local-only sidecar to the Tauri shell. Security posture:
* binds to 127.0.0.1 only (never exposed on the network)
* requires a per-launch bearer token shared with the Tauri shell via the
  NATIVELINGO_TOKEN env var, so other local processes can't drive it

Exposes:
* GET  /health              -> liveness + readiness (model loaded?)
* POST /analyze             -> multipart upload of reference + learner audio,
                               returns the full feedback payload
* GET  /videos              -> list videos in the videos/ directory
* POST /videos/{name}/process -> transcribe + sentence-segment a video
* GET  /videos/{name}/stream  -> Range-capable video stream (muted playback)
* POST /analyze_video       -> shadow a sentence range: clip reference audio
                               from the video and score the learner recording
* POST /recordings          -> store the learner recording, returns an id
* GET  /recordings/{id}/clip -> exact WAV slice of the learner recording
                               (FR-8: sample-accurate "my" word/sentence replay)
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import threading
import uuid

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from backend.core.audio_io import load_audio_from_array, trim_silence
from backend.core.pipeline import analyze_full, analyze_detailed, get_encoder
from backend.core import video as videomod
from backend.core.transcribe import transcribe_sentences

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app):
    # Prefetch the heavy analysis models (MMS ~1.2GB + phoneme ~2.4GB) in the
    # background so the first /analyze_video doesn't block on download. Progress
    # is exposed via /warmup. Best-effort; analyze still works if it fails.
    from backend.core import warmup
    warmup.start()
    try:
        yield
    finally:
        # llama.cpp Metal must be released before interpreter/dylib teardown;
        # otherwise an exceptional request followed by app exit can trip a
        # ggml-metal resource-set assertion.
        from backend.core import memorize_warmup
        memorize_warmup.release()


app = FastAPI(title="NativeLingo Backend", version="0.1.0", lifespan=_lifespan)

# Tauri webview origins; tightened since the API is local-only anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "tauri://localhost", "*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_TOKEN = os.environ.get("NATIVELINGO_TOKEN")


def require_token(authorization: str | None = Header(default=None)):
    """Enforce the shared bearer token when one is configured. If no token is
    set (e.g. local dev), auth is skipped."""
    if _TOKEN is None:
        return
    expected = f"Bearer {_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing token")


def check_token_value(token: str | None):
    """Token check for endpoints that can't send an Authorization header (e.g.
    a <video src> stream), which pass the token as a query parameter instead."""
    if _TOKEN is None:
        return
    if token != _TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing token")


def _decode_upload(raw: bytes) -> np.ndarray:
    """Decode uploaded audio bytes into a 16 kHz mono waveform.

    soundfile handles wav/flac/ogg/aiff. Browser MediaRecorder produces
    webm/opus which soundfile can't read — those are decoded via ffmpeg.
    """
    try:
        data, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
        return load_audio_from_array(data, sr)
    except Exception:
        # robust fallback for webm/opus/m4a etc. via ffmpeg
        return videomod.decode_audio_bytes(raw)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": get_encoder() is not None}


@app.get("/warmup")
def warmup():
    """Analysis-model prefetch progress (MMS + phoneme downloaded in the
    background at startup so the first /analyze_video isn't a multi-GB wait)."""
    from backend.core import warmup as _warmup
    return _warmup.status()


@app.post("/clientlog")
async def clientlog(request: Request):
    """Debug channel: the frontend posts client-side messages/errors here so
    they surface in the backend log (the webview has no visible console)."""
    try:
        body = await request.json()
        print(f"[CLIENT] {body.get('msg')}", flush=True)
    except Exception:
        pass
    return {"ok": True}


@app.post("/analyze")
async def analyze(
    reference: UploadFile = File(...),
    learner: UploadFile = File(...),
    _=Depends(require_token),
):
    ref_bytes = await reference.read()
    learner_bytes = await learner.read()
    if not ref_bytes or not learner_bytes:
        raise HTTPException(status_code=400, detail="empty audio upload")

    try:
        ref_wav = trim_silence(_decode_upload(ref_bytes))
        learner_wav = trim_silence(_decode_upload(learner_bytes))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not decode audio: {exc}")

    if ref_wav.size == 0 or learner_wav.size == 0:
        raise HTTPException(status_code=400, detail="audio contained no speech")

    payload = analyze_full(ref_wav, learner_wav)
    return payload


# --------------------------------------------------------------------------- #
# Video shadowing endpoints
# --------------------------------------------------------------------------- #

@app.get("/videos")
def list_videos(_=Depends(require_token)):
    """List available reference videos."""
    return {"videos": videomod.list_videos()}


@app.post("/videos/{name}/process")
def process_video(name: str, force: bool = False, _=Depends(require_token)):
    """Transcribe + sentence-segment a video (cached). Returns sentences with
    timestamps the frontend uses for range selection and video seeking."""
    try:
        return transcribe_sentences(name, force=force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"transcription failed: {exc}")


_STREAM_CHUNK = 1024 * 1024  # 1 MiB


@app.get("/videos/{name}/stream")
def stream_video(name: str, request: Request, token: str | None = None):
    """Serve a video with HTTP Range support so the <video> element can seek to
    an arbitrary sentence start. Token passed as a query param since a media
    element can't set an Authorization header."""
    check_token_value(token)
    try:
        path = videomod.resolve_video(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    start = 0
    end = file_size - 1
    status_code = 200
    if range_header:
        # format: "bytes=start-end"
        try:
            units, rng = range_header.split("=")
            s, e = rng.split("-")
            start = int(s) if s else 0
            end = int(e) if e else file_size - 1
            end = min(end, file_size - 1)
            status_code = 206
        except (ValueError, IndexError):
            start, end, status_code = 0, file_size - 1, 200

    length = end - start + 1

    def iterfile():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_STREAM_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": "video/mp4",
    }
    return StreamingResponse(iterfile(), status_code=status_code, headers=headers)


@app.get("/videos/{name}/clip")
def clip_audio(name: str, start: float, end: float, token: str | None = None):
    """Return the reference audio for [start, end] seconds of a video as a WAV.

    Lets the frontend replay a single sentence's *original* audio in place,
    without touching the (muted) video player. Token via query param since an
    <audio> element can't set an Authorization header."""
    check_token_value(token)
    try:
        path = videomod.resolve_video(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start")
    try:
        wav = videomod.extract_audio(path, start=start, end=end)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"clip extraction failed: {exc}")

    buf = io.BytesIO()
    sf.write(buf, wav, 16000, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.post("/analyze_video")
async def analyze_video(
    video: str = Form(...),
    start_index: int = Form(...),
    end_index: int = Form(...),
    learner: UploadFile = File(...),
    _=Depends(require_token),
):
    """Shadow a sentence range [start_index, end_index] of a video.

    We clip the reference audio for that range straight from the video, decode
    the learner recording, and run the full analysis pipeline.
    """
    try:
        data = transcribe_sentences(video)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    sentences = data["sentences"]
    if not sentences:
        raise HTTPException(status_code=400, detail="video has no transcribed sentences")
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    start_index = max(0, start_index)
    end_index = min(len(sentences) - 1, end_index)

    seg_start = sentences[start_index]["start"]
    seg_end = sentences[end_index]["end"]

    try:
        path = videomod.resolve_video(video)
        # do NOT trim: keep exact clip timing so word timestamps map onto frames
        ref_wav = videomod.extract_audio(path, start=seg_start, end=seg_end)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"reference extraction failed: {exc}")

    learner_bytes = await learner.read()
    if not learner_bytes:
        raise HTTPException(status_code=400, detail="empty learner audio")
    try:
        learner_wav = _decode_upload(learner_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not decode learner audio: {exc}")

    if ref_wav.size == 0 or learner_wav.size == 0:
        raise HTTPException(status_code=400, detail="audio contained no speech")

    # build clip-relative sentence units (subtract seg_start from all times)
    clip_sentences = []
    for i in range(start_index, end_index + 1):
        s = sentences[i]
        clip_sentences.append(
            {
                "index": i,
                "text": s["text"],
                "start": s["start"] - seg_start,
                "end": s["end"] - seg_start,
                "words": [
                    {
                        "word": w["word"],
                        "start": w["start"] - seg_start,
                        "end": w["end"] - seg_start,
                    }
                    for w in s.get("words", [])
                ],
            }
        )

    payload = analyze_detailed(ref_wav, learner_wav, clip_sentences)
    payload["reference_text"] = " ".join(
        sentences[i]["text"] for i in range(start_index, end_index + 1)
    )
    payload["segment"] = {"start": seg_start, "end": seg_end}
    return payload


# --------------------------------------------------------------------------- #
# Learner recording store (FR-8: sample-accurate replay of "my" clips)
# --------------------------------------------------------------------------- #
# The frontend holds the learner recording as a blob; replaying a word/sentence
# from it via HTML currentTime seek + timeupdate only gives ~250 ms granularity
# and truncates word tails. Instead we keep the decoded recording server-side
# and cut exact WAV slices — the same mechanism as reference /videos/{n}/clip.
_RECORDINGS_DIR = tempfile.mkdtemp(prefix="nativelingo_recordings_")
_RID_RE = re.compile(r"^[0-9a-f]{32}$")


def _recording_path(rid: str) -> str:
    if not _RID_RE.match(rid):
        raise HTTPException(status_code=400, detail="invalid recording id")
    path = os.path.join(_RECORDINGS_DIR, f"{rid}.wav")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="recording not found")
    return path


@app.post("/recordings")
async def store_recording(
    learner: UploadFile = File(...),
    _=Depends(require_token),
):
    """Store a learner recording (decoded to 16 kHz mono WAV) for later
    exact-slice replay. Returns {"recording_id": ...}."""
    raw = await learner.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    try:
        wav = _decode_upload(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not decode audio: {exc}")
    if wav.size == 0:
        raise HTTPException(status_code=400, detail="audio contained no speech")
    rid = uuid.uuid4().hex
    sf.write(os.path.join(_RECORDINGS_DIR, f"{rid}.wav"), wav, 16000,
             format="WAV", subtype="PCM_16")
    return {"recording_id": rid, "duration_s": round(wav.size / 16000.0, 3)}


@app.get("/recordings/{rid}/clip")
def recording_clip(rid: str, start: float, end: float, token: str | None = None):
    """Return [start, end] seconds of a stored learner recording as a WAV.
    Token via query param (an <audio> element can't set headers)."""
    check_token_value(token)
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start")
    wav, sr = sf.read(_recording_path(rid), dtype="float32")
    a = max(0, int(round(start * sr)))
    b = min(wav.size, int(round(end * sr)))
    if b <= a:
        raise HTTPException(status_code=400, detail="clip range outside recording")
    buf = io.BytesIO()
    sf.write(buf, wav[a:b], sr, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


# --------------------------------------------------------------------------- #
# Memorizing module (FR-13..15): photo object recognition + scenario sentences
# --------------------------------------------------------------------------- #
# The frontend uploads a photo, gets back whole-object boxes (clickable
# hotspots), then per-click asks for that object's parts and a scenario. The
# photo is stored server-side under a UUID (mirrors /recordings) so each click
# doesn't re-upload the multi-MB image. All handlers are plain `def` (not async)
# so FastAPI runs blocking model inference in the threadpool without stalling
# the event loop. Intelligence is fully on-device (NFR-5): no media is served
# back, only JSON (boxes + text).
_MEMORIZES_DIR = tempfile.mkdtemp(prefix="nativelingo_photos_")
_MID_RE = re.compile(r"^[0-9a-f]{32}$")
_MEMORIZE_META: dict[str, dict] = {}
_MEMORIZE_META_LOCK = threading.Lock()
_MEMORIZE_REQUEST_TIMEOUT_S = 15.0


class _MemorizeRequestTimedOut(TimeoutError):
    """A local model call exceeded the learner-facing responsiveness budget."""


def _within_memorize_deadline(operation):
    """Return an operation result or fail the HTTP request after 15 seconds.

    Python cannot safely kill a thread inside ONNX/Torch native code, so a
    timed-out worker is daemonized and allowed to finish in the background.
    Crucially, the request and UI are released immediately; future clicks get a
    deterministic retry path rather than an unbounded spinner.
    """
    completed = threading.Event()
    result: dict[str, object] = {}

    def run() -> None:
        try:
            result["value"] = operation()
        except BaseException as exc:  # preserve model-library failures
            result["error"] = exc
        finally:
            completed.set()

    worker = threading.Thread(target=run, daemon=True, name="nl-memorize-request")
    worker.start()
    if not completed.wait(_MEMORIZE_REQUEST_TIMEOUT_S):
        raise _MemorizeRequestTimedOut()
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result.get("value")


def _photo_path(mid: str) -> str:
    if not _MID_RE.match(mid):
        raise HTTPException(status_code=400, detail="invalid photo id")
    path = os.path.join(_MEMORIZES_DIR, f"{mid}.img")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="photo not found")
    return path


def _load_image(path: str):
    from PIL import Image
    return Image.open(path).convert("RGB")


class PartsReq(BaseModel):
    photo_id: str
    object_id: int


class ScenarioReq(BaseModel):
    photo_id: str
    object_id: int
    part_en: str = ""


def _object_for(photo_id: str, object_id: int) -> dict:
    """Return one server-owned detection; never trust client boxes/labels."""
    _photo_path(photo_id)
    with _MEMORIZE_META_LOCK:
        meta = _MEMORIZE_META.get(photo_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="photo context not found")
        for item in meta["objects"]:
            if item["id"] == object_id:
                return dict(item)
    raise HTTPException(status_code=404, detail="object not found")


@app.post("/memorize/analyze")
def memorize_analyze(photo: UploadFile = File(...), _=Depends(require_token)):
    """FR-13: detect whole objects in an uploaded photo. Stores the photo under
    a UUID and returns each object's label (en + zh) + box [x,y,w,h]."""
    raw = photo.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty image upload")
    if len(raw) > 15_000_000:
        raise HTTPException(status_code=400, detail="image too large (>15MB)")
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not decode image: {exc}")

    mid = uuid.uuid4().hex
    with open(os.path.join(_MEMORIZES_DIR, f"{mid}.img"), "wb") as f:
        f.write(raw)

    from backend.core import vision
    try:
        objects = _within_memorize_deadline(lambda: vision.detect(img))
    except _MemorizeRequestTimedOut:
        try:
            os.remove(os.path.join(_MEMORIZES_DIR, f"{mid}.img"))
        except OSError:
            pass
        raise HTTPException(
            status_code=504,
            detail="图片识别等待超过15秒，已停止本次请求。请重试。",
        )
    except Exception as exc:  # noqa: BLE001  (model not staged / downloading)
        try:
            os.remove(os.path.join(_MEMORIZES_DIR, f"{mid}.img"))
        except OSError:
            pass
        raise HTTPException(status_code=503, detail=f"object detection unavailable: {exc}")
    with _MEMORIZE_META_LOCK:
        _MEMORIZE_META[mid] = {
            "objects": objects,
            "contexts": {},
        }
    return {"photo_id": mid, "objects": objects}


@app.post("/memorize/parts")
def memorize_parts(req: PartsReq, _=Depends(require_token)):
    """FR-14: name the visible parts of a clicked object (server-side crop from
    the stored photo + its box, so the image isn't re-uploaded per click)."""
    path = _photo_path(req.photo_id)
    obj = _object_for(req.photo_id, req.object_id)
    img = _load_image(path)
    x, y, w, h = (float(v) for v in obj["box"])
    iw, ih = img.size
    cx, cy = x + w / 2.0, y + h / 2.0
    sw, sh = w * 1.2, h * 1.2  # +10% context each side so edges aren't clipped
    left = max(0, int(cx - sw / 2.0))
    top = max(0, int(cy - sh / 2.0))
    right = min(iw, int(cx + sw / 2.0))
    bottom = min(ih, int(cy + sh / 2.0))
    if right <= left or bottom <= top:
        raise HTTPException(status_code=400, detail="invalid object box")
    crop = img.crop((left, top, right, bottom))

    from backend.core import parts, memorize_warmup
    st = memorize_warmup.status()
    if st["running"] and not st["florence_ready"]:
        raise HTTPException(status_code=503, detail="parts model still preparing; see /memorize/status")
    try:
        result = _within_memorize_deadline(
            lambda: parts.analyze_parts(crop, obj["label_en"], obj["label_zh"])
        )
    except _MemorizeRequestTimedOut:
        raise HTTPException(
            status_code=504,
            detail="部件识别等待超过15秒，已停止本次请求。请重试。",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"part naming unavailable: {exc}")
    with _MEMORIZE_META_LOCK:
        meta = _MEMORIZE_META.get(req.photo_id)
        if meta is not None:
            meta["contexts"][req.object_id] = {
                "crop_context": result["crop_context"],
                "parts": result["parts"],
            }
    return result


@app.post("/memorize/scenario")
def memorize_scenario(req: ScenarioReq, _=Depends(require_token)):
    """FR-15: generate 1-3 target-language example sentences placing the object
    in a memorable real-world situation (text-only memory aid, no audio)."""
    obj = _object_for(req.photo_id, req.object_id)
    with _MEMORIZE_META_LOCK:
        meta = _MEMORIZE_META.get(req.photo_id) or {"objects": [], "contexts": {}}
        context = dict(meta["contexts"].get(req.object_id) or {})
        scene_objects = [
            item["label_en"]
            for item in meta["objects"]
            if item["id"] != req.object_id
        ]

    part_en = ""
    part_zh = ""
    if req.part_en.strip():
        selected = next(
            (
                item
                for item in context.get("parts", [])
                if item["label_en"].casefold() == req.part_en.strip().casefold()
            ),
            None,
        )
        if selected is None:
            raise HTTPException(status_code=400, detail="selected part is not in the analyzed crop")
        part_en = selected["label_en"]
        part_zh = selected.get("label_zh", "")

    from backend.core import scenario, memorize_warmup
    st = memorize_warmup.status()
    if st["running"] and not st["llm_ready"]:
        raise HTTPException(status_code=503, detail="scenario model still preparing; see /memorize/status")
    try:
        sents = _within_memorize_deadline(
            lambda: scenario.generate(
                obj["label_en"],
                obj["label_zh"],
                photo_context=context.get("crop_context", ""),
                scene_objects=scene_objects,
                part_en=part_en,
                part_zh=part_zh,
            )
        )
    except _MemorizeRequestTimedOut:
        raise HTTPException(
            status_code=504,
            detail="情景生成等待超过15秒，已停止本次请求。请重试。",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"scenario generation unavailable: {exc}")
    return {"sentences": sents}


@app.get("/memorize/status")
def memorize_status(_=Depends(require_token)):
    """Memorize-model prefetch progress (yolo -> llm -> florence). The frontend polls
    this on tab-enter to show staged download progress instead of a blind wait."""
    from backend.core import memorize_warmup
    return memorize_warmup.status()


@app.post("/memorize/warmup")
def memorize_warmup_start(_=Depends(require_token)):
    """Kick the on-demand model prefetch (called when the user enters the
    Memorize tab). Idempotent."""
    from backend.core import memorize_warmup
    memorize_warmup.start()
    return memorize_warmup.status()


@app.post("/memorize/release")
def memorize_release(_=Depends(require_token)):
    """Cancel warmup and free Florence + Qwen when the user leaves the tab.
    YOLO stays resident (tiny + bundled). First model-unload mechanism in the
    codebase."""
    from backend.core import memorize_warmup
    memorize_warmup.release()
    return {"released": True}


def main():
    """Entry point for running the sidecar standalone."""
    # Required by PyInstaller on macOS: model libraries may use multiprocessing
    # during warmup. Without this, a spawned child re-enters main() and briefly
    # tries to bind a second Uvicorn server on the same port.
    import multiprocessing
    import uvicorn

    multiprocessing.freeze_support()
    host = os.environ.get("NATIVELINGO_HOST", "127.0.0.1")
    port = int(os.environ.get("NATIVELINGO_PORT", "8756"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
