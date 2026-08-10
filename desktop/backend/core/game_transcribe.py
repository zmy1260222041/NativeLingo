"""Survival module transcription entry point (FR-22 input, R-14 G2 target).

WHY THIS IS NOT transcribe.transcribe_waveform  (红线 1)
  transcribe_waveform is tuned for the Speaking module's input: long, fluent,
  studio-recorded news sentences (`beam_size=1`, `vad_filter=True`). R-14 G6
  requires Speaking's accuracy/fluency to stay bit-identical, so that function
  is off limits -- retuning it for this module would violate the gate directly.
  This module's input is the opposite distribution: 2-6 words, L2 accent,
  grammatically incomplete, laptop/phone microphone. It gets its own decoder
  settings and shares only the loaded model instance (no second 141MB load).

THE THREE DEVIATIONS, EACH WITH ITS REASON
  beam_size=5            +5.6pp keyword recall on the speechocean762 proxy.
                         Affordable here because clips are seconds long, not
                         the minutes-long videos the Speaking path decodes.
  hotwords=<accept>      The game knows the scenario BEFORE the learner speaks,
                         so the scenario's `accept` terms are a zero-cost
                         decoding prior. This is not "giving away the answer":
                         it biases towards which words could occur in this
                         situation -- dozens of equivalent phrasings across all
                         slots -- not towards one reference sentence.
  vad_filter=False       VAD on a 1-6s utterance can swallow the whole clip,
                         and a hesitant learner's leading pause is signal, not
                         silence to trim.
  condition_on_previous_text=False
                         Anti-hallucination. Measured on the proxy corpus:
                         "WHAT WOULD IT BE LIKE THEN" -> "I will see you in the
                         next video". A dropped word only withholds supplies; a
                         hallucinated one makes slot matching hit a word never
                         said, which injects false positives into G1 -- and G1
                         is precision-first. Short clips have no useful prior
                         context anyway.

  faster-whisper 1.2.1 supports all of the above (verified against the
  installed version, not assumed).
"""
from __future__ import annotations

from .transcribe import _get_model
from .game_scenario import hotword_terms, normalise

# A learner utterance whose average log-probability falls below this is treated
# as "nothing intelligible was said" rather than transcribed into slot matching.
# Deliberately permissive: a low-confidence real attempt should still reach the
# matcher and be judged (A)-type (learner did not say the word), because that
# is the case the NPC's `miss` reply and the correction entry exist to handle.
_LOG_PROB_FLOOR = -1.4
_NO_SPEECH_CEIL = 0.8


def transcribe_utterance(wav, scenario: dict | None = None) -> dict:
    """Transcribe one short learner utterance.

    Returns ``{"text", "words", "avg_logprob", "no_speech_prob", "low_confidence"}``.
    `words` carries per-word timing/probability so the correction entry (FR-27)
    can show the learner *which* word the instrument thought it heard -- that is
    the (A)/(B) triage the whole corpus effort rests on.
    """
    model = _get_model()
    hotwords = " ".join(hotword_terms(scenario)) if scenario else None
    segments, info = model.transcribe(
        wav,
        language="en",
        beam_size=5,
        vad_filter=False,
        condition_on_previous_text=False,
        word_timestamps=True,
        hotwords=hotwords or None,
    )

    parts: list[str] = []
    words: list[dict] = []
    logprobs: list[float] = []
    no_speech: list[float] = []
    for seg in segments:
        text = str(getattr(seg, "text", "") or "").strip()
        if text:
            parts.append(text)
        lp = getattr(seg, "avg_logprob", None)
        if lp is not None:
            logprobs.append(float(lp))
        ns = getattr(seg, "no_speech_prob", None)
        if ns is not None:
            no_speech.append(float(ns))
        for w in (getattr(seg, "words", None) or []):
            tok = str(getattr(w, "word", "") or "").strip()
            if not tok:
                continue
            words.append(
                {
                    "word": tok,
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "probability": round(float(getattr(w, "probability", 0.0) or 0.0), 4),
                }
            )

    avg_logprob = sum(logprobs) / len(logprobs) if logprobs else None
    no_speech_prob = max(no_speech) if no_speech else None
    text = normalise(" ".join(parts))
    low = (
        not text
        or (avg_logprob is not None and avg_logprob < _LOG_PROB_FLOOR)
        or (no_speech_prob is not None and no_speech_prob > _NO_SPEECH_CEIL)
    )
    return {
        "text": text,
        "words": words,
        "avg_logprob": round(avg_logprob, 4) if avg_logprob is not None else None,
        "no_speech_prob": round(no_speech_prob, 4) if no_speech_prob is not None else None,
        "low_confidence": bool(low),
        "decode": {
            "model": getattr(model, "model_size_or_path", None) or "base.en",
            "beam_size": 5,
            "vad_filter": False,
            "condition_on_previous_text": False,
            "hotwords": hotwords,
            "language": getattr(info, "language", "en") if info is not None else "en",
        },
    }
