"""Video handling via PyAV (``av``), the Python binding to FFmpeg's libraries.

Responsibilities:
* list available videos under the videos/ directory
* probe duration
* extract audio (optionally a [start, end] time range) to a 16 kHz mono float32
  array, which is exactly the format the analysis pipeline expects

We decode in-process via PyAV rather than shelling out to the ffmpeg/ffprobe
CLIs. PyAV is already pulled in as a faster-whisper dependency (its wheels ship
the libav* libs, LGPL), so this needs **no separate ffmpeg binary** — a bundled
app runs on a clean machine with zero extra download, and the distributable
stays small. Decoding/resampling goes through the same libavcodec/libswresample
the CLI uses, so output matches.
"""
from __future__ import annotations

import io
import os

import av
import numpy as np


class FFmpegError(RuntimeError):
    pass


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


def videos_dir(root: str | None = None) -> str:
    """Absolute path to the videos/ directory (created if missing).

    In a bundled app the Tauri shell sets ``NATIVELINGO_DATA_DIR`` to a user
    data dir (~/Library/Application Support/com.nativelingo.app); fall back to
    the source-tree-relative path for dev (two levels up from backend/core/)."""
    if root is None:
        root = os.environ.get("NATIVELINGO_DATA_DIR")
    if root is None:
        # desktop/backend/core/video.py -> repo root is three levels up.
        # (Bundled app sets NATIVELINGO_DATA_DIR and never reaches here.)
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    d = os.path.join(root, "videos")
    os.makedirs(d, exist_ok=True)
    return d


def list_videos(root: str | None = None) -> list[dict]:
    """List video files in the videos/ directory with basic metadata."""
    d = videos_dir(root)
    out = []
    for name in sorted(os.listdir(d)):
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTS:
            path = os.path.join(d, name)
            out.append(
                {
                    "name": name,
                    "size_mb": round(os.path.getsize(path) / 1e6, 1),
                }
            )
    return out


def resolve_video(name: str, root: str | None = None) -> str:
    """Resolve a video name to an absolute path, guarding against traversal."""
    d = videos_dir(root)
    # only allow a bare filename inside the videos dir
    safe = os.path.basename(name)
    path = os.path.join(d, safe)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"video not found: {safe}")
    return path


def _decode_audio(
    container: "av.container.InputContainer",
    target_sr: int,
    start: float | None,
    end: float | None,
) -> np.ndarray:
    """Decode (a [start, end]s slice of) a container's first audio stream to a
    target-SR mono float32 numpy array via libswresample."""
    stream = next((s for s in container.streams if s.type == "audio"), None)
    if stream is None:
        raise FFmpegError("no audio stream in container")
    if start:
        # seek to nearest keyframe at/before `start` (time_base units)
        container.seek(int(start / stream.time_base), stream=stream)
    resampler = av.AudioResampler(format="flt", layout="mono", rate=target_sr)
    chunks: list[np.ndarray] = []
    try:
        for frame in container.decode(stream):
            if end is not None and frame.time is not None and frame.time > end:
                break
            for rf in resampler.resample(frame):
                chunks.append(np.asarray(rf.to_ndarray()).reshape(-1))
        for rf in resampler.resample(None):  # flush trailing samples
            chunks.append(np.asarray(rf.to_ndarray()).reshape(-1))
    except av.AVError as e:  # noqa: PERF203
        raise FFmpegError(f"audio decode failed: {e}") from e
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def probe_duration(video_path: str) -> float:
    """Container duration in seconds."""
    try:
        with av.open(video_path) as container:
            if container.duration is None:
                raise FFmpegError("container has no duration metadata")
            return container.duration / 1_000_000.0  # AV_TIME_BASE = microseconds
    except av.AVError as e:
        raise FFmpegError(f"could not probe duration: {e}") from e


def decode_audio_bytes(raw: bytes, target_sr: int = 16000) -> np.ndarray:
    """Decode arbitrary encoded audio bytes (e.g. browser webm/opus) into a
    target-SR mono float32 array. Robust for any container PyAV/ffmpeg reads."""
    try:
        with av.open(io.BytesIO(raw)) as container:
            return _decode_audio(container, target_sr, None, None)
    except av.AVError as e:
        raise FFmpegError(f"audio decode failed: {e}") from e


def extract_audio(
    video_path: str,
    start: float | None = None,
    end: float | None = None,
    target_sr: int = 16000,
) -> np.ndarray:
    """Extract audio (optionally a [start, end]s slice) as a target-SR mono
    float32 numpy array. Seeking lands on the keyframe at/before `start`; any
    pre-start samples decoded are kept (sentence clips pad either way)."""
    try:
        with av.open(video_path) as container:
            return _decode_audio(container, target_sr, start, end)
    except av.AVError as e:
        raise FFmpegError(f"audio extraction failed: {e}") from e
