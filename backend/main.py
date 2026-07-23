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
import uuid

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

from backend.core.audio_io import load_audio_from_array, trim_silence
from backend.core.pipeline import analyze_full, analyze_detailed, get_encoder
from backend.core import video as videomod
from backend.core.transcribe import transcribe_sentences

app = FastAPI(title="NativeLingo Backend", version="0.1.0")

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


def main():
    """Entry point for running the sidecar standalone."""
    import uvicorn

    host = os.environ.get("NATIVELINGO_HOST", "127.0.0.1")
    port = int(os.environ.get("NATIVELINGO_PORT", "8756"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
