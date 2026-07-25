"""Self-supervised speech encoder (Track B foundation).

This is the technical anchor of the "reverse evaluation" idea: modern voice
cloning / expressive TTS works because SSL models learn a disentangled latent
space over speech. We reuse that *same* representation in reverse — encode both
the reference and the learner audio into frame-level embeddings, then measure
their divergence (after removing the speaker factor) to score pronunciation
accuracy and fluency.

We use wav2vec2 (CTC-pretrained) by default: its hidden states carry strong
phonetic/content information, which is exactly what we want for accuracy.

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

import functools

import numpy as np
import torch
from transformers import Wav2Vec2Model, Wav2Vec2FeatureExtractor

from .audio_io import TARGET_SR

# Base model: light enough to run on CPU, strong phonetic content in hidden
# states. Frame stride is 20 ms (50 frames/sec).
DEFAULT_MODEL = "facebook/wav2vec2-base-960h"
FRAME_RATE_HZ = 50.0  # wav2vec2 produces one frame per 20 ms

# Transformer layers averaged into the embedding (1-based indices into the
# model's hidden_states; index 0 is the CNN feature output, so transformer
# layer L == hidden_states[L]). Layers 6–9: chosen empirically (see module
# docstring) — best speaker invariance + wrong-text separability; consistent
# with the literature's "middle layers carry phonetics" finding. A single int
# also works; None restores the final layer (v0.0/v0.1 behaviour).
DEFAULT_LAYERS: tuple[int, ...] = (6, 7, 8, 9)


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

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        layers: tuple[int, ...] | int | None = DEFAULT_LAYERS,
    ):
        self.model_name = model_name
        self.device = device or _select_device()
        if layers is None:  # explicit opt-out: final layer (v0.0/v0.1 behaviour)
            self.layers: tuple[int, ...] | None = None
        elif isinstance(layers, int):
            self.layers = (layers,)
        else:
            self.layers = tuple(layers)
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
        if self.layers is None:
            out = self.model(input_values)
            emb = out.last_hidden_state.squeeze(0)
        else:
            out = self.model(input_values, output_hidden_states=True)
            hs = out.hidden_states  # tuple of (1, T, D); [0]=CNN out, [L]=layer L
            n = len(hs) - 1
            sel = [hs[min(max(l, 0), n)] for l in self.layers]
            emb = torch.stack(sel, dim=0).mean(dim=0).squeeze(0)
        return emb.cpu().numpy().astype("float32")

    @staticmethod
    def frames_to_seconds(frame_index: float) -> float:
        return frame_index / FRAME_RATE_HZ
