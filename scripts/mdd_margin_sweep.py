"""Margin sweep for the CTC-scoring MDD (scripts, not a unit test).

For minimal pairs (ref word vs substituted read) prints the winning
substitution hypothesis and its gain; for negative controls (same read twice)
prints the best gain — the margin must separate the two groups.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

from backend.core.audio_io import TARGET_SR, load_audio, trim_silence
from backend.core import phoneme
from backend.core.phoneme import _slice_with_context, _emissions, _viterbi_avg, \
    _load, _CANDIDATES, PhoneSub

SAY = shutil.which("say")
tmp = tempfile.mkdtemp(prefix="nl_mdd_")


def synth(t: str):
    """Untrimmed `say` audio + the word's span via energy trim. Mirrors
    production, where word spans sit inside continuous real audio — the CTC
    decoder needs that real-silence/neighbour context (pure-zero padding is
    out-of-distribution and wrecks the decode)."""
    import librosa

    p = os.path.join(tmp, f"{abs(hash(t))}.aiff")
    if not os.path.exists(p):
        subprocess.run([SAY, "-v", "Samantha", "-o", p, t],
                       check=True, capture_output=True)
    wav = load_audio(p)
    _, idx = librosa.effects.trim(wav, top_db=30)
    return wav, idx[0] / TARGET_SR, idx[1] / TARGET_SR


def best_sub(ref, lrn):
    rw, rs, re_ = ref
    lw, ls, le = lrn
    ref_span = _slice_with_context(rw, rs, re_)
    lrn_span = _slice_with_context(lw, ls, le)
    ref_phones = phoneme.decode_phonemes(ref_span)
    _, _, _, _, vocab, pad_id = _load()
    chars = [c for c in ref_phones.replace(" ", "") if c in vocab]
    ids = [vocab[c] for c in chars]
    em = _emissions(lrn_span)
    base = _viterbi_avg(em, ids, pad_id)
    best = (-9e9, None)
    for i, p in enumerate(chars):
        if p == "ː":
            continue
        for c in _CANDIDATES:
            if c == p or c not in vocab:
                continue
            g = _viterbi_avg(em, ids[:i] + [vocab[c]] + ids[i+1:], pad_id) - base
            if g > best[0]:
                best = (g, PhoneSub(p, c, "substitute"))
        g = _viterbi_avg(em, ids[:i] + ids[i+1:], pad_id) - base
        if g > best[0]:
            best = (g, PhoneSub(p, "", "delete"))
    return ref_phones, best[1], best[0]


PAIRS = [("think", "sink"), ("thin", "sin"), ("ship", "sheep"),
         ("bad", "bed"), ("light", "right"), ("fan", "van")]
NEG = ["think", "sheep", "bad", "very", "well"]

print("== minimal pairs (want: correct sub, high gain) ==")
for a, b in PAIRS:
    rp, sub, gain = best_sub(synth(a), synth(b))
    print(f"  {a:>6} (/{rp}/) -> {b:<6} best sub {sub}  gain {gain:+.3f}")

print("== negatives (same audio; want: gain ~0 / negative) ==")
for a in NEG:
    rp, sub, gain = best_sub(synth(a), synth(a))
    print(f"  {a:>6} (/{rp}/)          best sub {sub}  gain {gain:+.3f}")
