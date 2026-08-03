"""Offline English word pronunciation via Piper neural TTS (FR-17).

Piper (GPL-3.0) runs a small VITS voice model exported to ONNX. NativeLingo
bundles the ``en_US-libritts_r-medium`` voice (CC-BY 4.0, redistributable;
chosen by listening — it keeps both the /s/ fricative and the /t/ burst in
word-initial /st-/ clusters, which lessac and amy each blur). It powers the
Memorizing module's "dictionary pronunciation" playback and the reference
side of the optional shadow-scoring endpoint.

Everything here returns 16 kHz mono float32 waveforms (matching
``audio_io.TARGET_SR``) so the synthesized reference can be fed straight into
the existing Track B scoring pipeline without a separate resample step.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from .audio_io import TARGET_SR

_voice = None  # PiperVoice instance (lazy, guarded by callers' lifecycle lock)
_voice_sr = 0  # Piper's native sample rate (Hz); usually 22050
_SYSTEM_SAY_VOICE = object()

# Deterministic synthesis: zero noise keeps the reference identical across the
# playback (/memorize/tts) and scoring (/memorize/pronounce) calls so the user
# is always scored against exactly the audio they heard.
_SYNTH_CONFIG = None  # piper.SynthesisConfig(noise_scale=0, noise_w_scale=0)


def uses_system_voice() -> bool:
    """Use macOS's offline voice in a frozen app.

    Piper's macOS espeakbridge wheel embeds its CI build directory and can
    terminate a large PyInstaller process before Python can handle the error.
    ``say`` is part of macOS, runs out-of-process, and therefore keeps the app
    backend alive even if synthesis itself fails.
    """
    return sys.platform == "darwin" and bool(getattr(sys, "_MEIPASS", ""))


def _espeak_data_dir() -> str:
    """Resolve espeak-ng-data/ at runtime, working under both dev and PyInstaller.

    Do not import ``piper`` while resolving this path.  Its native
    ``espeakbridge`` can cache the wheel's build-machine default as soon as the
    package is imported, which makes a later explicit path ineffective in a
    frozen process.  Resolve the package location without importing it, set
    ``ESPEAK_DATA_PATH``, and only then import Piper in :func:`load`.
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        frozen_candidate = Path(meipass) / "piper" / "espeak-ng-data"
        candidates.append(frozen_candidate)
        if (frozen_candidate / "phontab").is_file():
            return str(frozen_candidate)

    spec = importlib.util.find_spec("piper")
    if spec is not None and spec.origin:
        candidates.append(Path(spec.origin).resolve().parent / "espeak-ng-data")

    for candidate in candidates:
        if (candidate / "phontab").is_file():
            return str(candidate)

    checked = ", ".join(str(path) for path in candidates) or "no candidate paths"
    raise RuntimeError(f"Piper espeak-ng-data is missing (checked: {checked})")


def load(model_path: str) -> None:
    """Load a Piper voice model. Idempotent; re-load only after :func:`unload`.

    ``model_path`` must point at ``en_US-libritts_r-medium.onnx``; Piper
    locates the adjacent ``.onnx.json`` config automatically.

    ``ESPEAK_DATA_PATH`` is set before importing piper because espeakbridge.so
    initialises at import time and needs valid espeak-ng-data phontab/ etc.
    files — otherwise it falls back to a baked build-host path that does not
    exist in the frozen app.
    """
    global _voice, _voice_sr, _SYNTH_CONFIG
    if _voice is not None:
        return
    if uses_system_voice():
        _voice = _SYSTEM_SAY_VOICE
        _voice_sr = TARGET_SR
        _SYNTH_CONFIG = None
        return
    espeak_dir = _espeak_data_dir()
    # Must be set before the first Piper import.  Override any inherited stale
    # wheel/build path instead of using setdefault.
    os.environ["ESPEAK_DATA_PATH"] = espeak_dir
    from piper import PiperVoice, SynthesisConfig  # noqa: PLC0415

    _voice = PiperVoice.load(model_path, espeak_data_dir=espeak_dir)
    _voice_sr = int(getattr(_voice.config, "sample_rate", 22050))
    _SYNTH_CONFIG = SynthesisConfig(noise_scale=0.0, noise_w_scale=0.0)


def unload() -> None:
    """Drop the voice model (frees the ONNX session / memory)."""
    global _voice, _voice_sr, _SYNTH_CONFIG
    _voice = None
    _voice_sr = 0
    _SYNTH_CONFIG = None


def is_loaded() -> bool:
    return _voice is not None


def _synth_macos_say(text: str) -> np.ndarray:
    """Synthesize a 16 kHz mono waveform with macOS's offline ``say`` tool."""
    descriptor, wav_path = tempfile.mkstemp(prefix="nativelingo-tts-", suffix=".wav")
    os.close(descriptor)
    commands = (
        [
            "/usr/bin/say",
            "-v",
            "Samantha",
            "--file-format=WAVE",
            "--data-format=LEI16@16000",
            "-o",
            wav_path,
            text,
        ],
        [
            "/usr/bin/say",
            "--file-format=WAVE",
            "--data-format=LEI16@16000",
            "-o",
            wav_path,
            text,
        ],
    )
    errors: list[str] = []
    try:
        for command in commands:
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                break
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(str(exc))
        else:
            raise RuntimeError("macOS speech synthesis failed: " + "; ".join(errors))

        with wave.open(wav_path, "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
        if channels != 1 or sample_width != 2:
            raise RuntimeError(
                f"unexpected macOS speech format: channels={channels}, width={sample_width}"
            )
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        if sample_rate != TARGET_SR:
            import librosa

            samples = librosa.resample(
                samples, orig_sr=sample_rate, target_sr=TARGET_SR
            ).astype(np.float32)
        return samples
    finally:
        try:
            os.unlink(wav_path)
        except FileNotFoundError:
            pass


def synth_wav(text: str) -> np.ndarray:
    """Synthesize ``text`` and return a 16 kHz mono float32 waveform.

    Raises ``RuntimeError`` if the model is not loaded, or ``ValueError`` if
    synthesis yields no audio (e.g. an empty/unspeakable input).
    """
    if _voice is None:
        raise RuntimeError("piper model not loaded")
    if _voice is _SYSTEM_SAY_VOICE:
        return _synth_macos_say(text)
    chunks = list(_voice.synthesize(text, syn_config=_SYNTH_CONFIG))
    parts = [chunk.audio_float_array for chunk in chunks]
    parts = [p for p in parts if p is not None and len(p) > 0]
    if not parts:
        raise ValueError(f"piper produced no audio for {text!r}")
    samples = np.concatenate(parts).astype(np.float32)
    if _voice_sr and _voice_sr != TARGET_SR:
        import librosa

        samples = librosa.resample(samples, orig_sr=_voice_sr, target_sr=TARGET_SR)
    return samples
