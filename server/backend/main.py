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
import os
import re
import shutil
import tempfile
import threading
import time
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


# ── upload / abuse guards (cloud variant) ───────────────────────────────────
# The deploy box has 40 GB disk (94% used) and 4 CPU cores — a single oversized
# upload or a burst of analyses can take it down. These are simple, in-process
# limits: fine for one server, replace with nginx/Caddy-level limits if the
# box ever fronts more than a handful of devices.
_MAX_VIDEO_BYTES = 1_500_000_000   # 1.5 GB — a course video is ~90 MB
_MAX_LEARNER_BYTES = 100_000_000   # 100 MB — a take is seconds of 16 kHz wav
_MIN_FREE_DISK_BYTES = 1_000_000_000  # refuse uploads when < 1 GB free

_RATE_WINDOW_S = 60.0
_RATE_BUDGETS = {  # requests per window per client IP
    "/analyze_video": 10,
    "/videos": 3,
    "/register": 5,
    "/default": 60,
}
_RATE_HITS: dict[str, list[float]] = {}
_RATE_LOCK = threading.Lock()


def _rate_limit(request: Request, budget_key: str = "/default") -> None:
    """Sliding-window in-memory rate limit keyed by client IP."""
    key = request.client.host if request.client else "?"
    budget = _RATE_BUDGETS.get(budget_key, _RATE_BUDGETS["/default"])
    now = time.time()
    with _RATE_LOCK:
        hits = _RATE_HITS.setdefault(key, [])
        hits[:] = [t for t in hits if t > now - _RATE_WINDOW_S]
        if len(hits) >= budget:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        hits.append(now)


def _disk_ok() -> None:
    """Refuse uploads when the disk is nearly full (39/40 GB used already)."""
    free = shutil.disk_usage(videomod.videos_dir()).free
    if free < _MIN_FREE_DISK_BYTES:
        raise HTTPException(
            status_code=507,
            detail=f"服务器磁盘空间不足（剩余 {free // (1024**3)} GB），请稍后再试",
        )


def _check_upload_size(file: UploadFile, limit: int) -> None:
    """Reject an upload whose declared size exceeds [limit]."""
    if file.size is not None and file.size > limit:
        raise HTTPException(status_code=413, detail="上传文件过大")


@asynccontextmanager
async def _lifespan(_app):
    # Prefetch the heavy analysis models (MMS ~1.2GB + phoneme ~2.4GB) in the
    # background so the first /analyze_video doesn't block on download. Progress
    # is exposed via /warmup. Best-effort; analyze still works if it fails.
    from backend.core import warmup

    # Stale scratch dirs from earlier runs (the desktop's /recordings store was
    # removed in the cloud variant; anything left behind is dead biometric
    # data with no retention policy — delete on boot).
    _clean_stale_scratch("nativelingo_recordings_")
    _clean_stale_scratch("nativelingo_photos_")

    warmup.start()
    try:
        yield
    finally:
        # llama.cpp Metal must be released before interpreter/dylib teardown;
        # otherwise an exceptional request followed by app exit can trip a
        # ggml-metal resource-set assertion.
        from backend.core import memorize_warmup
        memorize_warmup.release()


def _clean_stale_scratch(prefix: str, max_age_s: float = 7 * 24 * 3600) -> None:
    """Delete scratch dirs from previous processes older than [max_age_s].

    tempfile.mkdtemp() creates a NEW directory per process and never reuses
    old ones — without this, every restart of the old desktop stack leaked a
    recordings/ photos directory forever."""
    tmp = tempfile.gettempdir()
    now = time.time()
    try:
        for name in os.listdir(tmp):
            if not name.startswith(prefix):
                continue
            p = os.path.join(tmp, name)
            try:
                if now - os.path.getmtime(p) > max_age_s:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


app = FastAPI(title="NativeLingo Backend", version="0.1.0", lifespan=_lifespan)

# Desktop Tauri webview origins. The Android client is a native HTTP client
# (no Origin header) — the wildcard used to sit here for it, but CORS only
# matters for browsers, and a wildcard would let any website call the API
# once it has a token, so it is gone.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "tauri://localhost"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_TOKEN = os.environ.get("NATIVELINGO_TOKEN")


def require_token(authorization: str | None = Header(default=None)):
    """Enforce authentication. Accepts either the operator token
    (NATIVELINGO_TOKEN — the server-side admin credential, never shipped in
    any APK) or a registered device token (per-device, revocable; see
    backend/core/devices.py). If no operator token is configured (local dev),
    auth is skipped."""
    from backend.core import devices

    if devices.admin_token() is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    raw = authorization.removeprefix("Bearer ").strip()
    if devices.is_admin_token(raw) or devices.is_device_token(raw) is not None:
        return
    raise HTTPException(
        status_code=401,
        detail="令牌无效或已失效，请在应用中重新激活设备",
    )


def require_admin_token(authorization: str | None = Header(default=None)):
    """Operator-only: endpoints the Android app never calls (desktop web
    frontend features — recordings store, Memorizing, clientlog). A leaked
    device token must not be able to grow the server's disk or burn CPU."""
    from backend.core import devices

    if devices.admin_token() is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    raw = authorization.removeprefix("Bearer ").strip()
    if devices.is_admin_token(raw):
        return
    raise HTTPException(status_code=401, detail="需要管理员令牌")


def check_admin_token_value(token: str | None):
    """Operator-only variant for query-param endpoints (streams, TTS)."""
    from backend.core import devices

    if devices.admin_token() is None:
        return
    if not token or not devices.is_admin_token(token):
        raise HTTPException(status_code=401, detail="需要管理员令牌")


def check_token_value(token: str | None):
    """Token check for endpoints that can't send an Authorization header (e.g.
    a <video src> stream), which pass the token as a query parameter instead."""
    from backend.core import devices

    if devices.admin_token() is None:
        return
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    if devices.is_admin_token(token) or devices.is_device_token(token) is not None:
        return
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


@app.post("/register")
def register_device(
    request: Request,
    device_id: str = Form(...),
    code: str = Form(...),
):
    """Device activation: exchange a one-time registration code (issued on the
    server, valid 24 h, burned on use) for a per-device token.

    Public by design — the code IS the credential, which is exactly why the
    APK can ship with no key baked in (OWASP Mobile Top 10 M1). The operator
    issues codes with ``python -m backend.core.devices code``."""
    _rate_limit(request, "/register")
    from backend.core import devices

    token = devices.register(device_id.strip(), code.strip())
    if token is None:
        raise HTTPException(status_code=401, detail="无效或已过期的激活码")
    return {"token": token, "device_id": device_id.strip()}


@app.get("/devices")
def list_devices(_=Depends(require_admin_token)):
    """Operator-only: registered devices + last-seen audit trail."""
    from backend.core import devices

    return {"devices": devices.list_devices()}


@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, _=Depends(require_admin_token)):
    """Operator-only: revoke a device's token immediately."""
    from backend.core import devices

    if not devices.revoke(device_id):
        raise HTTPException(status_code=404, detail="unknown device")
    return {"revoked": device_id}


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
async def clientlog(request: Request, _=Depends(require_admin_token)):
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



@app.post("/videos")
def upload_video(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
    _=Depends(require_token),
):
    """Upload a reference video to the server's videos/ dir (cloud Speaking track).

    The Android thin client pushes its local video here so /analyze_video can
    server-side decode the reference clip. The video is saved under
    ``videomod.videos_dir()`` and transcribed+sentence-segmented immediately
    (cached to <name>.sentences.json) — the same contract as
    POST /videos/{name}/process, so the client gets sentences back in one call.

    Security: the name is sanitized through ``videomod.resolve_video``'s
    traversal guard on the next read; here we also reject path separators.
    Uploads are size-limited and refused when the disk is nearly full.
    """
    _rate_limit(request, "/videos")
    _disk_ok()
    _check_upload_size(file, _MAX_VIDEO_BYTES)
    if "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="invalid video name")
    d = videomod.videos_dir()
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, name)
    with open(dest, "wb") as out:
        while True:
            chunk = file.file.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    try:
        return transcribe_sentences(name, force=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"transcription failed: {exc}")


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
    check_admin_token_value(token)
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
    check_admin_token_value(token)
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
    request: Request,
    video: str = Form(...),
    start_index: int = Form(...),
    end_index: int = Form(...),
    learner: UploadFile = File(...),
    _=Depends(require_token),
):
    """Shadow a sentence range [start_index, end_index] of a video.

    We clip the reference audio for that range straight from the video, decode
    the learner recording, and run the full analysis pipeline.

    Privacy: the learner recording is decoded in memory and never written to
    disk — the analysis is immediate and the bytes die with the request
    (this server deliberately has no recordings store).
    """
    _rate_limit(request, "/analyze_video")
    _check_upload_size(learner, _MAX_LEARNER_BYTES)
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
# Learner recording store — REMOVED in the cloud variant.
# --------------------------------------------------------------------------- #
# The desktop's /recordings store kept learner takes as WAV files for
# sample-accurate replay. The cloud server deliberately has NO recordings
# store: /analyze_video decodes the learner upload in memory and returns the
# result, and the Android app replays A/B clips from its own local samples
# (FR-8). Persisting voice recordings here would create biometric data with
# no retention policy (PIPL Art. 19/47) — the absence is the feature.
# The desktop frontend talks to its own local sidecar, so nothing depends on
# these endpoints on this server.


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
def memorize_analyze(photo: UploadFile = File(...), _=Depends(require_admin_token)):
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
def memorize_parts(req: PartsReq, _=Depends(require_admin_token)):
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
def memorize_scenario(req: ScenarioReq, _=Depends(require_admin_token)):
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
def memorize_status(_=Depends(require_admin_token)):
    """Memorize-model prefetch progress (yolo -> llm -> florence). The frontend polls
    this on tab-enter to show staged download progress instead of a blind wait."""
    from backend.core import memorize_warmup
    return memorize_warmup.status()


@app.post("/memorize/warmup")
def memorize_warmup_start(_=Depends(require_admin_token)):
    """Kick the on-demand model prefetch (called when the user enters the
    Memorize tab). Idempotent."""
    from backend.core import memorize_warmup
    memorize_warmup.start()
    return memorize_warmup.status()


@app.post("/memorize/release")
def memorize_release(_=Depends(require_admin_token)):
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
    check_admin_token_value(token)
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
def memorize_pronounce_status(_=Depends(require_admin_token)):
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
    _=Depends(require_admin_token),
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
