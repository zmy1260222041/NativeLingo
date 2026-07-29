"""Character-level forced alignment via torchaudio's MMS_FA bundle.

faster-whisper's `word_timestamps` come from decoder cross-attention and are
only approximate: they clip word tails and collapse short words (e.g. a
correctly-spoken "long" can get a 20 ms span). Forced alignment instead takes
the *known* transcript and Viterbi-decodes the monotonic alignment of its
characters to the audio frames at ~20 ms resolution, so word boundaries land
on real acoustic edges.

Flow::

    waveform -(MMS CTC model)-> per-frame emission
            -(forced_align / aligner)-> TokenSpan per char
            -> group chars by word -> per-word [start, end] in seconds

Model: ``torchaudio.pipelines.MMS_FA`` (``ctc_alignment_mling_uroman``,
~1.18 GB, downloaded once to ``~/.cache/torch/hub``). The dict is Latin
letters + a couple of symbols, so for English (already Latin) the tokenizer
maps characters directly — no uromanisation step is needed. The model is
lazily constructed and cached as a process singleton (like ``ssl_encoder``).

Degrades gracefully: if torchaudio or the model is unavailable, or alignment
fails, :func:`align_words` returns ``None`` and callers fall back to whatever
timestamps they already had (e.g. faster-whisper).
"""
from __future__ import annotations

import re

import numpy as np

try:
    import torch  # noqa: F401
    import torchaudio
    _BUNDLE = torchaudio.pipelines.MMS_FA
    _HAS_TA = True
except Exception:  # noqa: BLE001 - alignment is optional, never hard-fail
    _BUNDLE = None
    _HAS_TA = False

_SR = 16000
# chars the MMS dict knows about; everything else is stripped per word
_CHAR_RE = re.compile(r"[^a-z']")

_state = None  # (model, tokenizer, aligner)


def is_available() -> bool:
    """True if torchaudio + the MMS_FA bundle can be imported."""
    return _HAS_TA


def _get_state():
    """Lazily build and cache the (model, tokenizer, aligner) singleton."""
    global _state
    if _state is not None:
        return _state
    # CPU is reliable for the short clips we align; MPS can be flaky with
    # torchaudio CTC models, and one forward pass is well under a second.
    model = _BUNDLE.get_model().eval()
    tokenizer = _BUNDLE.get_tokenizer()
    aligner = _BUNDLE.get_aligner()
    _state = (model, tokenizer, aligner)
    return _state


def _clean(word: str) -> str:
    return _CHAR_RE.sub("", word.lower())


def align_words(words: list[str], wav: np.ndarray) -> list[tuple[float, float] | None] | None:
    """Align an ordered word sequence to a 16 kHz mono waveform.

    ``words``: transcript words in order. Non-letter chars are stripped per
    word; words that become empty (e.g. a bare number) are skipped and get no
    span — callers can fall back for those.
    ``wav``: 1-D float32 numpy array at 16 kHz.

    Returns a list parallel to ``words``: each entry is ``(start_s, end_s)``
    for that word, or ``None`` if it could not be aligned. Returns ``None``
    entirely if alignment is unavailable / failed, so callers can fall back to
    their previous timestamps.

    Because the transcript (not an ASR decode) is what gets aligned, a
    mispronounced word still maps to the word it *should* be: the aligner finds
    the best monotonic fit of the intended text to the audio regardless of how
    clearly the learner said it.
    """
    if not _HAS_TA or wav is None:
        return None
    wav = np.asarray(wav, dtype="float32")
    if wav.ndim != 1 or wav.size == 0 or not words:
        return None

    cleaned = [_clean(w) for w in words]
    keep_idx = [i for i, c in enumerate(cleaned) if c]
    if not keep_idx:
        return None

    try:
        import torch

        model, tokenizer, aligner = _get_state()
        t = torch.from_numpy(wav).unsqueeze(0)
        with torch.inference_mode():
            emission, _ = model(t)
        nframes = int(emission.shape[1])
        if nframes <= 0:
            return None
        # seconds per output frame (~0.02 for wav2vec2 CTC); derive from the
        # actual emission length so it stays correct for any model stride
        spf = (wav.size / _SR) / nframes
        spans = aligner(emission[0], tokenizer([cleaned[i] for i in keep_idx]))
    except Exception:  # noqa: BLE001 - never break analysis over alignment
        return None

    out: list[tuple[float, float] | None] = [None] * len(words)
    for k, gi in enumerate(keep_idx):
        # spans[k] is a list of TokenSpan, one per char of this word;
        # the word occupies frames [first.start, last.end]
        char_spans = spans[k] if k < len(spans) else None
        if not char_spans:
            continue
        f0 = int(char_spans[0].start)
        f1 = int(char_spans[-1].end)
        out[gi] = (round(f0 * spf, 3), round((f1 + 1) * spf, 3))
    return out
