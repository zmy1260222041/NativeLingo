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
* GET  /memorize/tts        -> Piper TTS WAV of a word/phrase (FR-17 playback)
* POST /memorize/pronounce  -> score a learner's word recording vs Piper ref
"""
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone

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
# Memorizing module (FR-13..15): photo recognition + one-level detail + dialogue
# --------------------------------------------------------------------------- #
# The frontend uploads a photo, gets back whole-object boxes (clickable
# hotspots), then per-click asks for that object's parts, optional container
# contents, and a scenario. Container contents remain server-owned leaf
# selections and can never become recursively analyzable whole objects. The
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
    from backend.core import memorize_image
    try:
        img, canonical_bytes = memorize_image.canonicalize_upload(raw)
    except memorize_image.ImageUploadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mid = uuid.uuid4().hex
    with open(os.path.join(_MEMORIZES_DIR, f"{mid}.img"), "wb") as f:
        f.write(canonical_bytes)

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
    return {
        "photo_id": mid,
        "image_size": list(img.size),
        "preprocessing": memorize_image.CONTRACT_VERSION,
        "objects": objects,
    }


@app.post("/memorize/parts")
def memorize_parts(req: PartsReq, _=Depends(require_token)):
    """FR-14: name visible parts and one-level contents of a clicked object."""
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
    object_box = [
        round(x - left, 1),
        round(y - top, 1),
        round(x + w - left, 1),
        round(y + h - top, 1),
    ]

    from backend.core import parts, memorize_warmup
    st = memorize_warmup.status()
    if st["running"] and not st["florence_ready"]:
        raise HTTPException(status_code=503, detail="parts model still preparing; see /memorize/status")
    try:
        result = _within_memorize_deadline(
            lambda: parts.analyze_parts(
                crop,
                obj["label_en"],
                obj["label_zh"],
                object_box=object_box,
            )
        )
    except _MemorizeRequestTimedOut:
        raise HTTPException(
            status_code=504,
            detail="部件识别等待超过15秒，已停止本次请求。请重试。",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"part naming unavailable: {exc}")
    result = dict(result)
    relation = parts.container_relation(obj["label_en"])
    result["contents"] = [
        {
            **item,
            "kind": "content",
            "parent_id": req.object_id,
            "relation": relation,
            "depth": 1,
        }
        for item in result.get("contents", [])
    ]
    with _MEMORIZE_META_LOCK:
        meta = _MEMORIZE_META.get(req.photo_id)
        if meta is not None:
            meta["contexts"][req.object_id] = {
                "crop_context": result["crop_context"],
                "parts": result["parts"],
                "contents": result["contents"],
            }
    # Florence boxes are xyxy coordinates relative to this context-expanded
    # crop. Return its exact geometry so the frontend can display the same
    # pixels and place part labels without guessing or coordinate drift.
    return {
        **result,
        "crop_box": [left, top, right - left, bottom - top],
        "crop_size": [right - left, bottom - top],
    }


@app.post("/memorize/scenario")
def memorize_scenario(req: ScenarioReq, _=Depends(require_token)):
    """FR-15: generate a short everyday multi-role dialogue placing the object in
    a memorable real-world situation (text-only memory aid, no audio)."""
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
        selectable = [
            *context.get("parts", []),
            *context.get("contents", []),
        ]
        selected = next(
            (
                item
                for item in selectable
                if item["label_en"].casefold() == req.part_en.strip().casefold()
            ),
            None,
        )
        if selected is None:
            raise HTTPException(
                status_code=400,
                detail="selected detail is not in the analyzed crop",
            )
        part_en = selected["label_en"]
        part_zh = selected.get("label_zh", "")

    from backend.core import scenario, memorize_warmup
    st = memorize_warmup.status()
    if st["running"] and not st["llm_ready"]:
        raise HTTPException(status_code=503, detail="scenario model still preparing; see /memorize/status")
    try:
        dialogue = _within_memorize_deadline(
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
    return dialogue


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


# ---------------------------------------------------------------------------
# FR-17: word pronunciation — Piper TTS playback + optional shadow scoring.
# Reference audio is synthesized on-device (never uploaded); the learner
# recording is scored with the same SSL+DTW Track B pipeline as Speaking.
# ---------------------------------------------------------------------------
_MAX_TTS_TEXT = 200
_TTS_TEXT_RE = re.compile(r"^[A-Za-z0-9 .,'!?&:/()-]+$")


def _valid_tts_text(text: str) -> str:
    """Normalize + validate a pronunciation target word/phrase."""
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > _MAX_TTS_TEXT:
        raise HTTPException(
            status_code=400,
            detail=f"text too long (max {_MAX_TTS_TEXT} characters)",
        )
    if not _TTS_TEXT_RE.match(text):
        raise HTTPException(
            status_code=400,
            detail="text contains unsupported characters",
        )
    return text


_PIPER_LAZY_LOCK = threading.Lock()


def _ensure_piper_ready() -> None:
    """Best-effort lazy-load Piper if warmup didn't complete the piper stage.

    The model is already in the HF cache once any warmup attempt has been made;
    this just verifies + loads (~1 s), protected by a lock so concurrent TTS /
    pronounce requests can't double-construct the ONNX session.
    """
    from backend.core import piper_tts

    if piper_tts.is_loaded():
        return
    with _PIPER_LAZY_LOCK:
        if piper_tts.is_loaded():
            return
        if piper_tts.uses_system_voice():
            piper_tts.load("")
            return
        from backend.core import model_assets

        onnx = model_assets.download_verified(
            model_assets.PIPER_REPO,
            model_assets.PIPER_FILENAME,
            model_assets.PIPER_REVISION,
            model_assets.PIPER_SIZE,
            model_assets.PIPER_SHA256,
        )
        import os

        if not os.path.exists(onnx + ".json"):
            from huggingface_hub import hf_hub_download

            hf_hub_download(
                model_assets.PIPER_REPO,
                model_assets.PIPER_CONFIG_FILENAME,
                revision=model_assets.PIPER_REVISION,
            )
        piper_tts.load(onnx)


@app.get("/memorize/tts")
def memorize_tts(text: str, token: str | None = None):
    """FR-17: return a 16 kHz PCM_16 WAV of ``text`` spoken by Piper neural TTS.

    Token via query param since an <audio> element can't set an Authorization
    header (same pattern as the Speaking clip endpoints)."""
    check_token_value(token)
    text = _valid_tts_text(text)
    from backend.core import piper_tts

    try:
        _ensure_piper_ready()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"pronunciation model still preparing: {exc}",
        )
    try:
        wav = _within_memorize_deadline(lambda: piper_tts.synth_wav(text))
    except _MemorizeRequestTimedOut:
        raise HTTPException(
            status_code=504,
            detail="语音合成等待超过15秒，已停止本次请求。请重试。",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"speech synthesis unavailable: {exc}")
    if wav.size == 0:
        raise HTTPException(status_code=400, detail="synthesis produced no audio")
    buf = io.BytesIO()
    sf.write(buf, wav, 16000, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/memorize/pronounce/status")
def memorize_pronounce_status(_=Depends(require_token)):
    """Lightweight liveness/readiness check for pronunciation scoring.

    Unlike the general /health endpoint, this never lazy-loads the SSL encoder,
    so the UI can use it with a short timeout before uploading a recording.
    """
    from backend.core import memorize_warmup, piper_tts, pipeline

    warmup = memorize_warmup.status()
    tts_ready = piper_tts.is_loaded()
    scorer_ready = pipeline.is_encoder_loaded()
    return {
        "status": "ok",
        "ready": tts_ready and scorer_ready,
        "tts_ready": tts_ready,
        "scorer_ready": scorer_ready,
        "warmup_stage": warmup.get("stage", "idle"),
    }


@app.post("/memorize/pronounce")
async def memorize_pronounce(
    text: str = Form(...),
    learner: UploadFile = File(...),
    _=Depends(require_token),
):
    """FR-17: score a learner's pronunciation of a single word/phrase.

    The reference is synthesized on-device with Piper; the learner recording is
    decoded, trimmed, and scored via the existing Track B pipeline. Word-level
    input needs no sentence/word segmentation, so the result is just the score
    triplet."""
    text = _valid_tts_text(text)
    raw = learner.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")

    from backend.core import piper_tts, pipeline

    try:
        _ensure_piper_ready()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"pronunciation model still preparing: {exc}",
        )

    def _score():
        ref_wav = trim_silence(piper_tts.synth_wav(text))
        if ref_wav.size == 0:
            raise ValueError("synthesis produced no audio")
        learner_wav = trim_silence(_decode_upload(raw))
        if learner_wav.size == 0:
            raise ValueError("learner audio contained no speech")
        return pipeline.analyze_arrays(ref_wav, learner_wav)

    try:
        result = _within_memorize_deadline(_score)
    except _MemorizeRequestTimedOut:
        raise HTTPException(
            status_code=504,
            detail="发音评分等待超过15秒，已停止本次请求。请重试。",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"pronunciation scoring unavailable: {exc}")
    return {
        "accuracy": round(float(result.accuracy), 1),
        "fluency": round(float(result.fluency), 1),
        "speech_rate_ratio": round(float(result.speech_rate_ratio), 3),
    }


# --------------------------------------------------------------------------- #
# Survival module — internal-beta collection build (FR-22/25/27, R-14 G1/G2)
# --------------------------------------------------------------------------- #
# This build exists to PRODUCE the corpus G1 and G2 need, not to ship the game:
# R-14 requires >=200 labelled responses transcribed through the production path
# and >=8 L2 speakers, neither of which can exist before there is something to
# speak into. Scope is a closed list — scenario fetch, record, transcribe, slot
# match, NPC reply, minimal supplies, correction entry, on-device persistence.
# NOT here, deliberately: /game/review (FR-23 cloud judging), photo vocabulary
# expansion (FR-24), the full supply economy and needs-tier progression (FR-26).
# Consequence worth stating: the beta build makes ZERO outbound requests, so
# NFR-6's whitelist surface is empty for this round.
#
# No fluency / naturalness / 地道度 is computed or returned. `delivery` is the
# deterministic slot-hit rate — it is G1's criterion itself — and is the only
# number the learner sees. Every other dimension's threshold is unfixed until
# G7; emitting one now would dress an uncalibrated number as a finished score.
_GAME_SERVED: dict[str, set[str]] = {}
_GAME_SERVED_LOCK = threading.Lock()


def _utc_now() -> str:
    """UTC ISO-8601 timestamp. Attempts sort by this in the export, so it must
    be timezone-explicit — a collection session spanning a DST change would
    otherwise reorder itself."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GameCorrectReq(BaseModel):
    corrected_text: str
    # The learner's own claim about what they said. Recorded, never used as the
    # `well_pronounced` annotation: self-assessment is systematically optimistic
    # (only those who believe they were right will tap), which is exactly the
    # (A)/(B) conflation the G2 criterion revision exists to separate.
    learner_claims_correct: bool = False
    note: str = ""


def _game_scenarios() -> dict:
    from backend.core import game_scenario

    scenarios, notes = game_scenario.load_scenarios()
    if not scenarios:
        raise HTTPException(
            status_code=503,
            detail=f"scenario library unavailable: {'; '.join(notes) or 'empty'}",
        )
    return scenarios


@app.get("/game/scenario")
def game_scenario_next(tier: str = "toddler", session: str = "default",
                       _=Depends(require_token)):
    """One scenario for the given tier.

    Beta behaviour is random-without-repeat inside a session, NOT the needs-tier
    progression of FR-26: progression would bias which scenarios get recorded,
    and the corpus needs even coverage across the library more than it needs a
    game arc. `situation.en` is withheld — the learner must produce the English
    from a Chinese situation, so shipping the English would leak the answer.
    """
    scenarios = _game_scenarios()
    pool = [s for s in scenarios.values() if str(s.get("tier") or "") == tier]
    if not pool:
        raise HTTPException(status_code=404, detail=f"no scenario for tier {tier!r}")
    with _GAME_SERVED_LOCK:
        served = _GAME_SERVED.setdefault(session, set())
        fresh = [s for s in pool if s.get("id") not in served]
        if not fresh:  # exhausted the tier — start the cycle over
            served.clear()
            fresh = pool
        pick = fresh[uuid.uuid4().int % len(fresh)]
        served.add(pick.get("id"))
    npc = pick.get("npc") or {}
    return {
        "id": pick.get("id"),
        "tier": pick.get("tier"),
        "need": pick.get("need"),
        "maslow_level": pick.get("maslow_level"),
        "situation_zh": (pick.get("situation") or {}).get("zh", ""),
        "npc_greeting": npc.get("greeting", ""),
        "npc_persona": npc.get("persona", ""),
        "slot_hints": [
            {"key": s.get("key"), "required": bool(s.get("required")),
             "zh_hint": s.get("zh_hint", "")}
            for s in (pick.get("slots") or [])
        ],
        "remaining_in_tier": max(0, len(pool) - len(_GAME_SERVED.get(session, ())))
    }


@app.post("/game/attempt")
async def game_attempt(
    scenario_id: str = Form(...),
    learner: UploadFile = File(...),
    speaker: str = Form(""),
    _=Depends(require_token),
):
    """Learner recording -> transcript -> slot match -> NPC reply + supplies.

    The audio and the judgement are persisted under NATIVELINGO_DATA_DIR (not a
    temp dir — a restart must not erase collected corpus), and the decode
    settings are stored alongside because a clip transcribed under different
    settings is a different measurement.
    """
    from backend.core import game_scenario as game_scenario_mod
    from backend.core import game_store, game_transcribe

    scenarios = _game_scenarios()
    scenario = scenarios.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"unknown scenario {scenario_id!r}")

    raw = await learner.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    try:
        wav = _decode_upload(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not decode audio: {exc}")
    if wav.size == 0:
        raise HTTPException(status_code=400, detail="audio contained no speech")

    def _run():
        return game_transcribe.transcribe_utterance(wav, scenario)

    try:
        asr = _within_memorize_deadline(_run)
    except _MemorizeRequestTimedOut:
        raise HTTPException(status_code=504, detail="转写等待超过15秒，已停止本次请求。请重试。")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"transcription unavailable: {exc}")

    aid = game_store.new_attempt_id()
    result = game_scenario_mod.judge(scenario, asr["text"], seed=uuid.uuid4().int)
    sf.write(game_store.attempt_wav_path(aid), wav, 16000,
             format="WAV", subtype="PCM_16")
    game_store.save_attempt(aid, {
        "created_at": _utc_now(),
        "scenario_id": scenario_id,
        "tier": scenario.get("tier"),
        "speaker": (speaker or "").strip()[:64],
        "transcript": result["transcript"],
        "words": asr["words"],
        "avg_logprob": asr["avg_logprob"],
        "no_speech_prob": asr["no_speech_prob"],
        "low_confidence": asr["low_confidence"],
        "decode": asr["decode"],
        "slots": result["slots"],
        "delivery": result["delivery"],
        "delivered": result["delivered"],
        "duration_s": round(wav.size / 16000.0, 3),
    })
    return {
        "attempt_id": aid,
        "transcript": result["transcript"],
        "low_confidence": asr["low_confidence"],
        "slots": [{"key": s["key"], "required": s["required"], "hit": s["hit"],
                   "matched": s["matched"]} for s in result["slots"]],
        "delivery": result["delivery"],
        "delivered": result["delivered"],
        "npc": result["npc"],
        "reward": result["reward"],
        "new_words": result["new_words"],
    }


@app.post("/game/attempt/{aid}/correct")
def game_attempt_correct(aid: str, req: GameCorrectReq, _=Depends(require_token)):
    """FR-27: the learner says the transcript got their words wrong.

    Re-judges against the corrected text and stores the correction in its own
    file — the attempt keeps what the instrument heard, the correction keeps what
    the human says was said, and merging them would destroy the distinction the
    corpus is being collected to measure. Costs no attempt (§5.4 retries are
    free), which is also why precision is G1's asymmetric side.
    """
    from backend.core import game_scenario as game_scenario_mod
    from backend.core import game_store

    try:
        attempt = game_store.load_attempt(aid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="attempt not found")

    corrected = game_scenario_mod.normalise(req.corrected_text)
    if not corrected:
        raise HTTPException(status_code=400, detail="corrected_text is empty")

    scenario = _game_scenarios().get(attempt.get("scenario_id"))
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario for this attempt is gone")

    result = game_scenario_mod.judge(scenario, corrected, seed=uuid.uuid4().int)
    game_store.save_correction(aid, {
        "created_at": _utc_now(),
        "scenario_id": attempt.get("scenario_id"),
        "asr_text": attempt.get("transcript") or "",
        "corrected_text": corrected,
        "learner_claims_correct": bool(req.learner_claims_correct),
        "note": (req.note or "").strip()[:500],
        "delivery_before": attempt.get("delivery"),
        "delivery_after": result["delivery"],
        "delivered_after": result["delivered"],
        # A correction that raises delivery means the instrument probably lost a
        # word the learner said — the (B) case G2 measures. One that does not is
        # more likely (A), and routes to the Speaking module instead.
        "triage_hint": "asr_miss" if result["delivery"] > (attempt.get("delivery") or 0)
                       else "pronunciation",
    })
    return {
        "attempt_id": aid,
        "transcript": corrected,
        "slots": [{"key": s["key"], "required": s["required"], "hit": s["hit"],
                   "matched": s["matched"]} for s in result["slots"]],
        "delivery": result["delivery"],
        "delivered": result["delivered"],
        "npc": result["npc"],
        "reward": result["reward"],
        "retry_free": True,
    }


@app.get("/game/export")
def game_export(_=Depends(require_token)):
    """The collection, shaped as the two gate harnesses read it.

    Human-judgement columns come back EMPTY on purpose: `delivered` (G1 truth),
    `expected_keywords` and `well_pronounced` (G2) are made by listening to the
    audio. Prefilling them from the transcript would have each gate grade its
    own homework. Audio stays on disk under `clips_dir` — it contains
    identifiable voices and is never returned over HTTP or committed.
    """
    from backend.core import game_store

    return game_store.export_rows()


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
