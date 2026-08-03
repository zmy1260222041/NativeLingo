"""Self-supervised speech encoder (Track B foundation).

This is the technical anchor of the "reverse evaluation" idea: modern voice
cloning / expressive TTS works because SSL models learn a disentangled latent
space over speech. We reuse that *same* representation in reverse — encode both
the reference and the learner audio into frame-level embeddings, then measure
their divergence (after removing the speaker factor) to score pronunciation
accuracy and fluency.

We use wav2vec2 (CTC-pretrained) by default: its hidden states carry strong
phonetic/content information, which is exactly what we want for accuracy.

**Server variant (ORT):** the desktop loads torch fp32 weights via transformers;
this deployment runs the fp16 ONNX export of transformer layers 6-9 MEAN
(scripts/onnx_export_spike.py, R-5) — the same bytes the Android app gates were
measured on. The export bakes the layer selection in, and the fp16 embedding
space measured worst-case cosine ≥0.990 against the torch fp32 goldens on
device, so the calibrated score_b thresholds carry over unchanged.

Layer choice (v0.2): the default was the final transformer layer, but layer-wise
analyses of wav2vec2 (Pasad et al. 2021; ABX phonetic-discrimination probes on
wav2vec2-base-960h) show *middle* layers carry the most phonetically
discriminative content, while the last layers specialise toward the CTC/char
objective (and, for cross-speaker comparison, retain more speaker idiosyncrasy).
Our own controlled experiment (scripts/layer_comparison.py, synthetic multi-voice
reads) confirms it: averaging transformer layers 6–9 gives both the best speaker
invariance (cross-voice same-text cost 0.159 vs 0.182 for the last layer) and
the best wrong-text separability (0.653 vs 0.472 margin). Single layers (e.g. 5,
the ABX optimum) keep more speaker factor and lose on invariance — the multi-
layer average is the right trade-off for reference comparison.
"""
from __future__ import annotations

import os

import numpy as np

from .onnx_runtime import model_path, normalize_wav2vec2, session

# Frame stride is 20 ms (50 frames/sec).
FRAME_RATE_HZ = 50.0  # wav2vec2 produces one frame per 20 ms

# Transformer layers averaged into the embedding. The ONNX export bakes this in
# (DEFAULT_LAYERS is kept for interface parity with the desktop module — the
# actual selection is a property of the exported graph).
DEFAULT_LAYERS: tuple[int, ...] = (6, 7, 8, 9)


class SSLEncoder:
    """Encodes a waveform into a (T, D) frame-level embedding sequence."""

    def __init__(
        self,
        model_path_: str | None = None,
        device: str | None = None,
        layers: tuple[int, ...] | int | None = DEFAULT_LAYERS,
    ):
        path = model_path_ or model_path("w2v2_base_69_fp16.onnx")
        self._session = session(path)
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    def encode(self, wav: np.ndarray) -> np.ndarray:
        """Return frame-level embeddings of shape (num_frames, hidden_dim).

        ``wav`` must be 16 kHz mono float32.
        """
        if wav.size == 0:
            return np.zeros((0, 768), dtype="float32")
        normalized = normalize_wav2vec2(np.asarray(wav, dtype="float32"))
        out = self._session.run(
            [self._output_name],
            {self._input_name: normalized[None, :]},
        )[0]
        return np.asarray(out, dtype="float32")[0]

    @staticmethod
    def frames_to_seconds(frame_index: float) -> float:
        return frame_index / FRAME_RATE_HZ
