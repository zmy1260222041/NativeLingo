"""Shared onnxruntime plumbing for the server variant.

The cloud server runs the SAME int8/fp16 ONNX exports the Android app was
gated on (scripts/onnx_export_spike.py + onnx_export_mms.py; R-5/R-6/R-7),
instead of the torch fp32 models the desktop uses. That shrinks the model
footprint from ~4 GB to ~0.8 GB and the resident RAM from ~5 GB to ~1.5 GB —
the deciding factor for the 3.7 GB deploy box (124.220.234.178).

Each export keeps its normalization OUTSIDE the graph (the exporter rejected
the dynamic-shape ops), so the wrappers re-implement it here, byte-for-byte as
the Android ports do:
  * wav2vec2 (SSL encoder, espeak CTC): Wav2Vec2FeatureExtractor do_normalize
    — zero-mean, unit-variance (population), eps 1e-7.
  * MMS (forced alignment): torchaudio's whole-clip layer_norm, eps 1e-5.
The eps values are load-bearing: 1e-5 vs 1e-7 is the difference between the
MMS and wav2vec2 conventions and they are NOT interchangeable.
"""
from __future__ import annotations

import functools
import os

import numpy as np
import onnxruntime as ort

# Where the ONNX weights live. The desktop backend downloads torch weights to
# the HF cache; the server keeps the exports in one flat directory, overridable
# so tests can point at a staging tree.
MODELS_DIR = os.environ.get("NATIVELINGO_MODELS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "models"))


def model_path(name: str) -> str:
    """Absolute path of an ONNX export inside [MODELS_DIR]."""
    return os.path.join(MODELS_DIR, name)


@functools.lru_cache(maxsize=8)
def session(path: str) -> ort.InferenceSession:
    """A cached CPU ORT session per model path (one per resident model)."""
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
    return ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])


def normalize_wav2vec2(wav: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    """Wav2Vec2FeatureExtractor do_normalize — zero-mean, unit-variance (population)."""
    if wav.size == 0:
        return wav
    mean = float(wav.mean())
    denom = float(np.sqrt(wav.var() + eps))
    return (wav - mean) / denom


def normalize_mms(wav: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    """torchaudio whole-clip layer_norm (no affine) — the MMS convention."""
    if wav.size == 0:
        return wav
    mean = float(wav.mean())
    denom = float(np.sqrt(wav.var() + eps))
    return (wav - mean) / denom


def log_softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable log-softmax (the torch op the exports omit)."""
    m = x.max(axis=axis, keepdims=True)
    e = np.exp(x - m)
    return (x - m) - np.log(e.sum(axis=axis, keepdims=True))
