"""Video handling via ffmpeg (we shell out to the ffmpeg/ffprobe CLIs).

Responsibilities:
* list available videos under the videos/ directory
* probe duration
* extract audio (optionally a [start, end] time range) to a 16 kHz mono wav,
  which is exactly the format the analysis pipeline expects

We deliberately drive ffmpeg as a subprocess rather than a python binding: it's
the most robust way to handle arbitrary container/codec combinations, and it's
what the goal asked for ("write code ourselves to operate the tool").
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

from .audio_io import load_audio

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


class FFmpegError(RuntimeError):
    pass


def _require_ffmpeg():
    if FFMPEG is None or FFPROBE is None:
        raise FFmpegError("ffmpeg/ffprobe not found on PATH")


def videos_dir(root: str | None = None) -> str:
    """Absolute path to the videos/ directory (created if missing)."""
    if root is None:
        # backend/core/video.py -> project root is two levels up from backend/
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, "..", ".."))
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


def probe_duration(video_path: str) -> float:
    _require_ffmpeg()
    res = subprocess.run(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        raise FFmpegError(f"could not probe duration: {res.stderr}")


def decode_audio_bytes(raw: bytes, target_sr: int = 16000) -> np.ndarray:
    """Decode arbitrary encoded audio bytes (e.g. browser webm/opus) into a
    16 kHz mono float32 array via ffmpeg. Robust for any container ffmpeg can
    read, and avoids librosa's deprecated audioread fallback."""
    _require_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tin:
        tin.write(raw)
        in_path = tin.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tout:
        out_path = tout.name
    try:
        cmd = [
            FFMPEG, "-y", "-v", "error", "-i", in_path,
            "-vn", "-ac", "1", "-ar", str(target_sr), "-f", "wav", out_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise FFmpegError(f"ffmpeg decode failed: {res.stderr}")
        return load_audio(out_path, target_sr=target_sr)
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                os.remove(p)


def extract_audio(
    video_path: str,
    start: float | None = None,
    end: float | None = None,
    target_sr: int = 16000,
) -> np.ndarray:
    """Extract audio (optionally a [start, end]s slice) as a 16 kHz mono float32
    numpy array. Uses accurate seeking (-ss after -i is slower but frame-exact,
    which matters for short sentence clips)."""
    _require_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name
    try:
        cmd = [FFMPEG, "-y", "-v", "error", "-i", video_path]
        if start is not None:
            cmd += ["-ss", f"{start:.3f}"]
        if end is not None:
            dur = max(0.05, (end - (start or 0.0)))
            cmd += ["-t", f"{dur:.3f}"]
        cmd += [
            "-vn",                     # drop video
            "-ac", "1",                # mono
            "-ar", str(target_sr),     # sample rate
            "-f", "wav",
            out_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise FFmpegError(f"ffmpeg audio extraction failed: {res.stderr}")
        return load_audio(out_path, target_sr=target_sr)
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
