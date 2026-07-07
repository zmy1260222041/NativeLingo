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

from .video import resolve_video, videos_dir

# Small model keeps first-run transcription fast on CPU/Metal while giving good
# English timestamps. Upgrade to "small"/"medium" for accuracy if needed.
DEFAULT_MODEL_SIZE = "base.en"

_model = None

# terminal punctuation that ends a sentence
_SENTENCE_END = re.compile(r"[.!?]['\")\]]?$")


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        # int8 on CPU is fast and low-memory; works on Apple silicon too.
        _model = WhisperModel(DEFAULT_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


# bump when the cache schema changes so old caches are regenerated
CACHE_VERSION = 2


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
        word_timestamps=True,      # needed for per-word scoring
    )
    sentences = _merge_into_sentences(segments)
    result = {
        "version": CACHE_VERSION,
        "video": os.path.basename(video_path),
        "duration": round(float(info.duration), 3),
        "sentences": sentences,
    }
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
