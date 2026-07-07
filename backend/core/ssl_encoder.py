"""Self-supervised speech encoder (Track B foundation).

This is the technical anchor of the "reverse evaluation" idea: modern voice
cloning / expressive TTS works because SSL models learn a disentangled latent
space over speech. We reuse that *same* representation in reverse — encode both
the reference and the learner audio into frame-level embeddings, then measure
their divergence (after removing the speaker factor) to score pronunciation
accuracy and fluency.

We use wav2vec2 (CTC-pretrained) by default: its hidden states carry strong
phonetic/content information, which is exactly what we want for accuracy.
"""
from __future__ import annotations

import functools

import numpy as np
import torch
from transformers import Wav2Vec2Model, Wav2Vec2FeatureExtractor

from .audio_io import TARGET_SR

# Base model: light enough to run on CPU, strong phonetic content in hidden
# states. Frame stride is 20 ms (50 frames/sec).
DEFAULT_MODEL = "facebook/wav2vec2-base-960h"
FRAME_RATE_HZ = 50.0  # wav2vec2 produces one frame per 20 ms


def _select_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@functools.lru_cache(maxsize=2)
def _load_model(model_name: str, device: str):
    """Load and cache the model + feature extractor. Cached so repeated
    requests in the long-running backend don't reload weights."""
    extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
    model = Wav2Vec2Model.from_pretrained(model_name)
    model.eval()
    model.to(device)
    return extractor, model


class SSLEncoder:
    """Encodes a waveform into a (T, D) frame-level embedding sequence."""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        self.model_name = model_name
        self.device = device or _select_device()
        self.extractor, self.model = _load_model(model_name, self.device)

    @torch.no_grad()
    def encode(self, wav: np.ndarray) -> np.ndarray:
        """Return frame-level embeddings of shape (num_frames, hidden_dim).

        ``wav`` must be 16 kHz mono float32.
        """
        if wav.size == 0:
            hidden = self.model.config.hidden_size
            return np.zeros((0, hidden), dtype="float32")
        inputs = self.extractor(
            wav, sampling_rate=TARGET_SR, return_tensors="pt"
        )
        input_values = inputs.input_values.to(self.device)
        out = self.model(input_values)
        # (1, T, D) -> (T, D)
        emb = out.last_hidden_state.squeeze(0).cpu().numpy().astype("float32")
        return emb

    @staticmethod
    def frames_to_seconds(frame_index: float) -> float:
        return frame_index / FRAME_RATE_HZ
