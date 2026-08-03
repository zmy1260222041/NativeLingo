"""Sentence segmentation via faster-whisper.

The reference videos have burned-in subtitles (no soft subtitle track), so we
can't parse a subtitle file. Instead we transcribe the audio to get sentence
text + precise timestamps. Those timestamps drive two things:

* clipping the reference audio for the sentence range the learner picks
* seeking the muted video playback to the right moment during shadowing

Whisper emits phrase-level segments; we merge them into *sentences* by terminal
punctuation so the user selects natural sentence boundaries. Results are cached
to videos/<name>.sentences.json so each video is only transcribed once.
"""
from __future__ import annotations

import json
import os
import re
import sys

from .video import resolve_video, videos_dir, extract_audio
from . import forced_align

# Small model keeps first-run transcription fast on CPU/Metal while giving good
# English timestamps. Upgrade to "small"/"medium" for accuracy if needed.
DEFAULT_MODEL_SIZE = "base.en"

# Prefer a pre-bundled model so the frozen app transcribes offline (no 141MB
# first-run download). Depth differs between the frozen onedir and dev:
#   frozen: <bundle>/backend/core/ -> ../../models = <bundle>/models  (freeze.spec stages it there)
#   dev:    desktop/backend/core/  -> ../../../models = <repo>/models  (staged at repo root)
_HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    _BUNDLED_MODEL = os.path.join(_HERE, "..", "..", "models", "whisper-base.en")
else:
    _BUNDLED_MODEL = os.path.join(_HERE, "..", "..", "..", "models", "whisper-base.en")
# In dev the dir may be absent; _model_path() then falls back to the
# model-size name (HuggingFace download, cached after first use).


def _model_path():
    return _BUNDLED_MODEL if os.path.isdir(_BUNDLED_MODEL) else DEFAULT_MODEL_SIZE


_model = None

# terminal punctuation that ends a sentence
_SENTENCE_END = re.compile(r"[.!?]['\")\]]?$")

# --- sub-sentence splitting (FR-M3) -------------------------------------------
# News sentences are long (43% of CBS material >6s or >18 words) — too long to
# shadow in one go. Long sentences get a conservative second-level split at
# natural boundaries (clause punctuation first, then conjunctions), aiming for
# chunks a learner can actually repeat.
_SPLIT_DUR_S = 8.0        # sentences longer than this get split
_SPLIT_WORDS = 20         # ... or with more words than this
_MIN_CHUNK_WORDS = 4      # never emit fragments shorter than this
_CLAUSE_END = re.compile(r"[,;:]['\")\]]?$")
_CONJ = {
    "and", "but", "so", "because", "which", "that", "when", "while", "if",
    "who", "whom", "whose", "where", "although", "though", "as", "since",
    "unless", "until", "after", "before",
}


def _needs_split(words: list[dict]) -> bool:
    dur = words[-1]["end"] - words[0]["start"]
    return dur > _SPLIT_DUR_S or len(words) > _SPLIT_WORDS


def _best_split_point(words: list[dict]) -> int | None:
    """Return the index to split ``words`` at (start of the right chunk).

    Prefer clause punctuation, then conjunctions; pick the candidate closest
    to the midpoint that leaves both chunks >= _MIN_CHUNK_WORDS.
    """
    n = len(words)
    if n < 2 * _MIN_CHUNK_WORDS:
        return None
    mid = n / 2.0

    def candidates():
        for i in range(_MIN_CHUNK_WORDS, n - _MIN_CHUNK_WORDS + 1):
            left_end = words[i - 1]["word"]
            right_start = re.sub(r"^[^a-zA-Z]+", "", words[i]["word"]).lower()
            if _CLAUSE_END.search(left_end):
                yield i, 0  # punctuation boundary is best
            elif right_start in _CONJ:
                yield i, 1

    best, best_key = None, None
    for i, rank in candidates():
        key = (rank, abs(i - mid))
        if best_key is None or key < best_key:
            best, best_key = i, key
    return best


def _split_long(words: list[dict]) -> list[list[dict]]:
    """Recursively split a long word list into shadowable chunks."""
    if not _needs_split(words):
        return [words]
    cut = _best_split_point(words)
    if cut is None:
        return [words]
    return _split_long(words[:cut]) + _split_long(words[cut:])


def _merge_words_into_sentences(words: list[dict]) -> list[dict]:
    """Merge a flat ordered word list into sentences by terminal punctuation.

    Each output sentence: ``{index, start, end, text, words}``. The word's
    original text (with trailing punctuation) drives sentence-end detection;
    the timestamps are whatever ``_aligned_words`` produced. Over-long
    sentences are sub-split at clause boundaries (FR-M3).
    """
    sentences: list[dict] = []
    cur: list[dict] = []

    def emit(chunk: list[dict]):
        text = re.sub(r"\s+", " ", " ".join(w["word"] for w in chunk)).strip()
        if text:
            sentences.append(
                {
                    "index": len(sentences),
                    "start": round(chunk[0]["start"], 3),
                    "end": round(chunk[-1]["end"], 3),
                    "text": text,
                    "words": [dict(w) for w in chunk],
                }
            )

    def flush():
        nonlocal cur
        if cur:
            for chunk in _split_long(cur):
                emit(chunk)
        cur = []

    for w in words:
        cur.append(w)
        if _SENTENCE_END.search(w["word"]):
            flush()
    flush()
    return sentences


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        # int8 on CPU is fast and low-memory; works on Apple silicon too.
        _model = WhisperModel(_model_path(), device="cpu", compute_type="int8")
    return _model


# bump when the cache schema changes so old caches are regenerated.
# v3: word timestamps now come from MMS forced alignment (not whisper attention).
# v4: over-long sentences sub-split at clause boundaries (FR-M3, news domain).
CACHE_VERSION = 4


def _cache_path(video_path: str) -> str:
    d = videos_dir()
    base = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(d, f"{base}.sentences.json")


def _merge_into_sentences(segments) -> list[dict]:
    """Merge whisper words into sentences by terminal punctuation.

    Each output sentence has: index, start, end, text, and words:
    [{word, start, end}] so downstream analysis can score each word.
    """
    sentences: list[dict] = []
    cur_words: list[dict] = []

    def flush():
        nonlocal cur_words
        if cur_words:
            text = re.sub(r"\s+", " ", " ".join(w["word"] for w in cur_words)).strip()
            if text:
                sentences.append(
                    {
                        "index": len(sentences),
                        "start": round(cur_words[0]["start"], 3),
                        "end": round(cur_words[-1]["end"], 3),
                        "text": text,
                        "words": cur_words,
                    }
                )
        cur_words = []

    for seg in segments:
        words = getattr(seg, "words", None)
        if not words:
            # no word timestamps for this segment; fall back to a whole-segment
            # pseudo-word so we don't lose the text
            piece = seg.text.strip()
            if piece:
                cur_words.append(
                    {"word": piece, "start": round(seg.start, 3), "end": round(seg.end, 3)}
                )
                if _SENTENCE_END.search(piece):
                    flush()
            continue
        for w in words:
            token = w.word.strip()
            if not token:
                continue
            cur_words.append(
                {"word": token, "start": round(w.start, 3), "end": round(w.end, 3)}
            )
            if _SENTENCE_END.search(token):
                flush()
    flush()
    return sentences


def _aligned_words(segments, video_path: str) -> list[dict]:
    """Flat ordered word list ``{word, start, end}`` across all segments.

    Word timestamps come from MMS forced alignment (whole-video, one call) when
    available; we fall back to faster-whisper's attention-based timestamps
    otherwise. We keep whisper for the *text* either way — only the timestamps
    are upgraded, because whisper's word boundaries clip tails and collapse
    short words.
    """
    base: list[dict] = []
    for seg in segments:
        for w in (getattr(seg, "words", None) or []):
            tok = w.word.strip()
            if not tok:
                continue
            base.append({"word": tok, "start": float(w.start), "end": float(w.end)})

    if base and forced_align.is_available():
        try:
            audio = extract_audio(video_path)  # full 16 kHz mono waveform
            spans = forced_align.align_words([b["word"] for b in base], audio)
        except Exception:  # noqa: BLE001 - fall back to whisper timestamps
            spans = None
        if spans is not None:
            for b, sp in zip(base, spans):
                if sp is not None:
                    b["start"], b["end"] = sp

    for b in base:
        b["start"] = round(b["start"], 3)
        b["end"] = round(b["end"], 3)
    return base


def transcribe_waveform(wav) -> list[dict]:
    """Transcribe an in-memory 16 kHz mono float32 waveform into sentences,
    same shape as ``transcribe_sentences``'s ``sentences`` (not cached).

    Used to segment the *learner's own* recording independently of the
    reference: the learner's speech rate differs, so their sentence boundaries
    should come from their own audio, not from warping the reference's grid.
    """
    model = _get_model()
    segments, _info = model.transcribe(
        wav,
        language="en",
        vad_filter=True,
        beam_size=1,
        word_timestamps=True,
    )
    return _merge_into_sentences(segments)


def transcribe_sentences(name: str, force: bool = False) -> dict:
    """Return {"video": name, "duration": .., "sentences": [...]}.

    Uses a cached JSON if present unless ``force`` is set.
    """
    video_path = resolve_video(name)
    cache = _cache_path(video_path)

    if not force and os.path.exists(cache):
        with open(cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # regenerate stale caches lacking word-level timestamps
        if cached.get("version") == CACHE_VERSION and cached.get("sentences") \
                and "words" in cached["sentences"][0]:
            return cached

    model = _get_model()
    segments, info = model.transcribe(
        video_path,
        language="en",
        vad_filter=True,           # skip long silences -> better boundaries
        beam_size=1,
        word_timestamps=True,      # fallback word timestamps; refined by forced alignment
    )
    segments = list(segments)
    flat_words = _aligned_words(segments, video_path)
    sentences = _merge_words_into_sentences(flat_words)
    result = {
        "version": CACHE_VERSION,
        "video": os.path.basename(video_path),
        "duration": round(float(info.duration), 3),
        "sentences": sentences,
    }
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
