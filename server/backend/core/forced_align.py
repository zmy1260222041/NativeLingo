"""Character-level forced alignment via the MMS CTC ONNX export.

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

**Server variant (ORT):** the desktop uses torchaudio's MMS_FA bundle (~1.18 GB
fp32). This deployment runs the HF-rehosted int8 ONNX export
(scripts/onnx_export_mms.py; R-6) — the same 338 MB model the Android app
ships. Its graph omits three torchaudio ops, re-implemented here exactly as
the Android port (core-align/MmsEmitter.kt) does:
  * normalizeWaveform — whole-clip layer_norm (eps 1e-5; MMS's convention).
  * log_softmax — kept IN the graph.
  * the "star" column — MMS_FA appends an all-zero 29th column (log p = 0, a
    wildcard that can absorb any frame); we never put star in a target
    sequence, but the emission width must match.

The character Viterbi is the same blank-extended DP as torchaudio's
`functional.forced_align` (and the desktop phoneme.py `_viterbi_align`),
ported from :core-scoring's CtcViterbi.kt which was verified frame-for-frame
against torchaudio (Gate B / R-6).

Degrades gracefully: if the model is unavailable, or alignment fails,
:func:`align_words` returns ``None`` and callers fall back to whatever
timestamps they already had (e.g. faster-whisper).
"""
from __future__ import annotations

import re

import numpy as np

from .onnx_runtime import model_path, normalize_mms, session

_SR = 16000
# chars the MMS dict knows about; everything else is stripped per word
_CHAR_RE = re.compile(r"[^a-z']")

# `MMS_FA.get_dict()` — blank, 26 letters, apostrophe, and the star wildcard.
# The ONNX export's 28 outputs are [a-z'] + blank (order per the re-hosted
# Wav2Vec2ForCTC vocab); the star column is appended by the wrapper below.
_MMS_TOKENS: dict[str, int] = {
    "a": 1, "i": 2, "e": 3, "n": 4, "o": 5, "u": 6, "t": 7, "s": 8, "r": 9,
    "m": 10, "k": 11, "l": 12, "d": 13, "g": 14, "h": 15, "y": 16, "b": 17,
    "p": 18, "w": 19, "c": 20, "v": 21, "j": 22, "z": 23, "f": 24, "'": 25,
    "q": 26, "x": 27,
}
_BLANK = 0

_state = None  # (session, input_name, output_name)


def is_available() -> bool:
    """True when the ONNX export can be loaded (model staged on the server)."""
    try:
        _get_state()
        return True
    except Exception:  # noqa: BLE001
        return False


def _get_state():
    """Lazily build and cache the ORT session singleton."""
    global _state
    if _state is not None:
        return _state
    s = session(model_path("mms_fa_int8_transformer.onnx"))
    _state = (s, s.get_inputs()[0].name, s.get_outputs()[0].name)
    return _state


def _clean(word: str) -> str:
    return _CHAR_RE.sub("", word.lower())


def _ctc_align(emission: np.ndarray, seq_ids: list[int], blank: int = 0):
    """Blank-extended CTC forced alignment (CtcViterbi.kt port).

    Returns (mean_logprob, [(ext_pos, first_frame, last_frame)]). Odd ext
    positions are the real tokens: ext position ``2k+1`` ↔ ``seq_ids[k]``.
    """
    t = emission.shape[0]
    if t == 0 or not seq_ids:
        return 0.0, []
    ext = [blank]
    for s in seq_ids:
        ext += [s, blank]
    s = len(ext)
    neg = -1e30
    dp = np.full((t, s), neg, dtype="float64")
    bp = np.full((t, s), -1, dtype="int16")
    dp[0, 0] = emission[0, blank]
    if s > 1:
        dp[0, 1] = emission[0, ext[1]]
        bp[0, 1] = 0
    for ti in range(1, t):
        row = emission[ti]
        prev, cur, bpt = dp[ti - 1], dp[ti], bp[ti]
        for si in range(s):
            best_val, best_src = prev[si], si
            if si - 1 >= 0 and prev[si - 1] > best_val:
                best_val, best_src = prev[si - 1], si - 1
            # skip-over-blank — only for real tokens that differ from the token
            # two positions back (CTC forbids skipping repeats)
            if (
                si - 2 >= 0
                and ext[si] != blank
                and ext[si] != ext[si - 2]
                and prev[si - 2] > best_val
            ):
                best_val, best_src = prev[si - 2], si - 2
            if best_val <= neg:
                continue
            cur[si] = row[ext[si]] + best_val
            bpt[si] = best_src
    # terminal cell: trailing blank (s-1) or the last real token (s-2)
    last = s - 1 if dp[t - 1, s - 1] >= (dp[t - 1, s - 2] if s > 1 else neg) else s - 2
    final = dp[t - 1, last]
    # backtrack — frame range per ext position
    ranges: dict[int, list[int]] = {}
    ti, si = t - 1, last
    while ti >= 0 and si >= 0:
        ranges.setdefault(si, []).append(ti)
        si = bp[ti, si]
        ti -= 1
    spans = [(s_, min(ts), max(ts)) for s_, ts in sorted(ranges.items())]
    return float(final / max(t, 1)), spans


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
    try:
        s, in_name, out_name = _get_state()
    except Exception:  # noqa: BLE001
        return None
    if wav is None:
        return None
    wav = np.asarray(wav, dtype="float32")
    if wav.ndim != 1 or wav.size == 0 or not words:
        return None

    cleaned = [_clean(w) for w in words]
    keep_idx = [i for i, c in enumerate(cleaned) if c]
    if not keep_idx:
        return None

    try:
        normalized = normalize_mms(wav)
        emission = s.run([out_name], {in_name: normalized[None, :]})[0][0]
        # append the star column (V 28 → 29), matching the golden emission width
        emission = np.concatenate([emission, np.zeros((emission.shape[0], 1), np.float32)], axis=1)
        nframes = emission.shape[0]
        if nframes <= 0:
            return None
        # seconds per output frame (~0.02 for wav2vec2 CTC); derive from the
        # actual emission length so it stays correct for any model stride
        spf = (wav.size / _SR) / nframes

        # one flat character sequence across all kept words, then unflatten by
        # word length — torchaudio's aligner does exactly this, and it matters:
        # aligning words independently would let their frame ranges overlap.
        char_ids: list[int] = []
        for i in keep_idx:
            for c in cleaned[i]:
                tid = _MMS_TOKENS.get(c)
                if tid is None:
                    return None
                char_ids.append(tid)

        log_probs = emission.astype("float64")
        _, spans = _ctc_align(log_probs, char_ids, _BLANK)
        # ext position 2k+1 holds the k-th character; a character with no span
        # in the backtrack was never visited and the word is left unaligned.
        by_char: dict[int, list[int]] = {}
        for ext_pos, f0, f1 in spans:
            if ext_pos % 2 == 1:
                by_char[(ext_pos - 1) // 2] = [f0, f1]
    except Exception:  # noqa: BLE001 - never break analysis over alignment
        return None

    out: list[tuple[float, float] | None] = [None] * len(words)
    ci = 0
    for gi in keep_idx:
        n = len(cleaned[gi])
        first = by_char.get(ci)
        last = by_char.get(ci + n - 1)
        ci += n
        if first is None or last is None:
            continue
        # torchaudio's TokenSpan.end is exclusive (= lastFrame + 1), and macOS
        # then adds one more frame of tail: end = (f1 + 1) * spf. Reproduced
        # verbatim — the golden word spans encode this, and FR-8 replay seeks
        # to them, so "more correct" here would just desync from macOS.
        f0 = first[0]
        f1 = last[1] + 1
        out[gi] = (round(f0 * spf, 3), round((f1 + 1) * spf, 3))
    return out
