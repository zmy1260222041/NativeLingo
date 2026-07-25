#!/usr/bin/env python3
"""Phase 2 / Gate B — export torchaudio's MMS_FA forced-alignment model to a
quantizable ONNX graph by re-hosting its weights on HuggingFace `Wav2Vec2ForCTC`.

Why not export torchaudio's own graph (see R-6, docs/reviews/2026-07-25-android-gate-bc-onnx.md):

  1. `_Wav2Vec2Model.forward` builds `List[int]` from dynamic shapes in three
     places (length bookkeeping, waveform layer_norm, star-column cat) that the
     legacy exporter refuses.
  2. Worse, even when the inner submodules ARE exported cleanly, `quantize_dynamic`
     leaves the graph at 1204MB → 1204MB: torchaudio's linear ops don't match the
     quantizer's patterns. A 1.2GB first-launch download is not shippable.

HF's Wav2Vec2 is the *same architecture* and is known-quantizable (it is what
Gate A/C already shipped), so the fix is a state-dict re-host. The mapping is
mechanical — torchaudio and HF use nearly identical submodule names:

    encoder.transformer.layers.N.*  ->  wav2vec2.encoder.layers.N.*
    encoder.feature_projection.*    ->  wav2vec2.feature_projection.*
    feature_extractor.*             ->  wav2vec2.feature_extractor.*
    aux.*                           ->  lm_head.*

The one non-obvious part is `layer_norm_first`. The bundle declares
`encoder_layer_norm_first=True`, but `Transformer.layer_norm_first` reads False —
torchaudio passes the *negation* to the Transformer wrapper (the layers get True,
the wrapper gets `not True`). So the real topology is pre-norm layers with a
trailing encoder layer_norm, i.e. HF `do_stable_layer_norm=True`. Reading only
the wrapper flag would silently produce a post-norm model that loads without
error and emits garbage — hence `verify_parity` below runs before any export.

Three peripheral ops stay OUT of the graph and are re-implemented in Kotlin
(:core-align MmsForcedAligner) — they are dynamic-shape ops of no compute weight:
  (a) waveform layer_norm over the whole clip (eps 1e-5, no affine),
  (b) log_softmax over the vocab axis,   [kept in-graph, it exports fine]
  (c) the appended all-zero "star" column, V 28 -> 29.

Run: .venv/bin/python scripts/onnx_export_mms.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import torch
import onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.core import forced_align as fa  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(_REPO, "NativeLingoAndroid/core-scoring/src/test/resources/golden")

SENTENCE = "The quick brown fox jumps over the lazy dog."


# ---- 1. config -------------------------------------------------------------

def hf_config():
    """HF config mirroring torchaudio's MMS_FA `_params` (printed by the bundle).

    Dropouts/layerdrop are zeroed: we only ever run this in eval, and layerdrop
    in particular must not be traced into the exported graph.
    """
    from transformers import Wav2Vec2Config

    return Wav2Vec2Config(
        vocab_size=28,                    # aux_num_out (bundle already dropped axes 1,2,3)
        hidden_size=1024,
        num_hidden_layers=24,
        num_attention_heads=16,
        intermediate_size=4096,
        hidden_act="gelu",
        feat_extract_activation="gelu",
        conv_dim=(512,) * 7,
        conv_kernel=(10, 3, 3, 3, 3, 2, 2),
        conv_stride=(5, 2, 2, 2, 2, 2, 2),
        conv_bias=True,                   # extractor_conv_bias
        feat_extract_norm="layer",        # extractor_mode=layer_norm
        num_conv_pos_embeddings=128,
        num_conv_pos_embedding_groups=16,
        do_stable_layer_norm=True,        # see module docstring — NOT the wrapper flag
        layerdrop=0.0,
        hidden_dropout=0.0,
        activation_dropout=0.0,
        attention_dropout=0.0,
        feat_proj_dropout=0.0,
        final_dropout=0.0,
        apply_spec_augment=False,
        ctc_zero_infinity=True,
    )


# ---- 2. state-dict re-host -------------------------------------------------

def map_key(k: str) -> str:
    if k.startswith("aux."):
        return "lm_head." + k[len("aux."):]
    if k.startswith("encoder.feature_projection."):
        return "wav2vec2.feature_projection." + k[len("encoder.feature_projection."):]
    if k.startswith("encoder.transformer."):
        return "wav2vec2.encoder." + k[len("encoder.transformer."):]
    if k.startswith("feature_extractor."):
        return "wav2vec2." + k
    raise KeyError(f"unmapped torchaudio key: {k}")


def build_hf(ta_inner):
    from transformers import Wav2Vec2ForCTC

    hf = Wav2Vec2ForCTC(hf_config()).eval()
    src = ta_inner.state_dict()
    mapped = {map_key(k): v for k, v in src.items()}

    tgt = hf.state_dict()
    missing = [k for k in tgt if k not in mapped]
    unexpected = [k for k in mapped if k not in tgt]
    # masked_spec_embed is HF-only (SpecAugment, disabled) — the ONLY key allowed
    # to be missing. Anything else means the mapping is wrong, and a wrong
    # mapping still "works" (random weights) — so fail loudly here.
    allowed_missing = {"wav2vec2.masked_spec_embed"}
    if set(missing) - allowed_missing or unexpected:
        raise SystemExit(
            f"state-dict mapping mismatch\n  missing:    {sorted(set(missing) - allowed_missing)[:10]}"
            f"\n  unexpected: {unexpected[:10]}"
        )
    for k, v in mapped.items():
        if tgt[k].shape != v.shape:
            raise SystemExit(f"shape mismatch {k}: HF {tuple(tgt[k].shape)} vs MMS {tuple(v.shape)}")

    hf.load_state_dict(mapped, strict=False)
    print(f"  re-hosted {len(mapped)} tensors onto HF Wav2Vec2ForCTC "
          f"({sum(v.numel() for v in mapped.values())/1e6:.1f}M params)")
    return hf


# ---- 3. parity before export ----------------------------------------------

def normalize_waveform(wav: np.ndarray) -> np.ndarray:
    """torchaudio `F.layer_norm(waveforms, waveforms.shape)` — whole-clip
    zero-mean/unit-var, eps 1e-5, no affine. Mirrored in Kotlin."""
    x = wav.astype("float64")
    v = x.var()  # population
    return ((x - x.mean()) / np.sqrt(v + 1e-5)).astype("float32")


def verify_parity(hf, wav):
    """HF re-host vs torchaudio, on the real reference clip. This is the check
    that catches a wrong do_stable_layer_norm / a mis-mapped key.

    Criterion note: a raw max|Δ| bound on the emission is the WRONG test and was
    tried first — it reports ~1e-3 for a provably correct mapping, because the
    largest absolute deviations sit in the deep-negative tail (worst cell here is
    log p = -13.75, i.e. p ~ 1e-6) where fp32 accumulation across 24 layers and a
    different attention kernel (HF sdpa vs torchaudio's manual matmuls) differ
    harmlessly. What forced alignment actually consumes is the *shape* of the
    distribution, so gate on cosine + per-frame argmax, and report max|Δ| as a
    diagnostic only. A wrong mapping does not squeak past this: a wrong
    do_stable_layer_norm drives cosine well below 1 and argmax agreement to chance.
    """
    ta = fa._BUNDLE.get_model().eval()
    t = torch.from_numpy(wav.astype("float32")).unsqueeze(0)
    with torch.inference_mode():
        ta_out, _ = ta(t)                       # (1,T,29) log-softmax + star
        hf_logits = hf(torch.from_numpy(normalize_waveform(wav)).unsqueeze(0)).logits
        hf_out = torch.log_softmax(hf_logits, dim=-1)
    hf_out = append_star(hf_out.numpy())
    if hf_out.shape != tuple(ta_out.shape):
        raise SystemExit(f"shape mismatch: HF {hf_out.shape} vs torchaudio {tuple(ta_out.shape)}")
    ref = ta_out.numpy()
    d = float(np.abs(hf_out - ref).max())
    cos = _cos(hf_out[0], ref[0])
    argmax_agree = float((hf_out[0].argmax(-1) == ref[0].argmax(-1)).mean())
    ok = cos >= 0.9999 and argmax_agree == 1.0
    print(f"  parity vs torchaudio: cosine={cos:.6f}  argmax-agree={argmax_agree:.3f}  "
          f"(max|Δ|={d:.2e} in the log-prob tail)  {'OK' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit("re-hosted model does not reproduce torchaudio — mapping is wrong")
    return cos


def append_star(em: np.ndarray) -> np.ndarray:
    """torchaudio FA appends an all-zero 'star' column (V 28 -> 29)."""
    zeros = np.zeros(em.shape[:-1] + (1,), dtype=em.dtype)
    return np.concatenate([em, zeros], axis=-1)


# ---- 4. export + quantize --------------------------------------------------

def export(hf, out_dir):
    class LogSoftmaxCTC(torch.nn.Module):
        """Normalized waveform -> log-softmax emission (1,T,28). The star column
        is appended by the caller (dynamic-shape cat does not export)."""
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, wav):
            return torch.log_softmax(self.m(wav).logits, dim=-1)

    fp32 = os.path.join(out_dir, "mms_fa_fp32.onnx")
    dummy = torch.zeros(1, 16000, dtype=torch.float32)
    with torch.no_grad():
        torch.onnx.export(
            LogSoftmaxCTC(hf).eval(), dummy, fp32, opset_version=17, dynamo=False,
            input_names=["wav"], output_names=["emission"],
            dynamic_axes={"wav": {0: "batch", 1: "samples"},
                          "emission": {0: "batch", 1: "time"}},
        )
    # int8 transformer-only: the CNN feature extractor stays fp32 (Gate A's
    # finding — it is the drift-sensitive part, and full int8 also chokes on
    # the Conv bias initializer). The transformer is ~96% of the parameters
    # here, so this still gets nearly the full 4x.
    int8 = os.path.join(out_dir, "mms_fa_int8_transformer.onnx")
    quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8,
                     op_types_to_quantize=["MatMul", "Gemm"])
    return fp32, int8


# ---- 5. gate evaluation ----------------------------------------------------

def evaluate(paths, wav):
    golden_em = np.load(os.path.join(GOLDEN, "mms", "ref_samantha_emission.npy"))
    spans_json = json.load(open(os.path.join(GOLDEN, "mms", "ref_samantha_spans.json")))
    golden_char = spans_json["char_tokens"]

    names = SENTENCE.rstrip(".").split()
    cleaned = [fa._clean(w) for w in names]
    keep = [i for i, c in enumerate(cleaned) if c]
    _, tokenizer, aligner = fa._get_state()
    norm = normalize_waveform(wav)

    print("\n########## GATE B — MMS forced alignment (HF re-host) ##########")
    results = {}
    for label, path in paths:
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        em = append_star(sess.run(["emission"], {"wav": norm[None, :]})[0])[0]
        cos = _cos(em, golden_em)

        # the functional check: does forced alignment on THIS emission land the
        # same character frames as the macOS golden?
        spans = aligner(torch.from_numpy(em.astype("float32")),
                        tokenizer([cleaned[i] for i in keep]))
        max_err, gi = 0, 0
        for cs in spans:
            for ts in cs:
                if gi >= len(golden_char):
                    break
                g = golden_char[gi]
                max_err = max(max_err, abs(int(ts.start) - g["start_frame"]),
                              abs(int(ts.end) - g["end_frame"]))
                gi += 1
        ok = cos >= 0.995 and max_err <= 1
        mb = os.path.getsize(path) // 1024 // 1024
        print(f"  {label:24} cosine={cos:.5f}  char-frame-max-err={max_err}  "
              f"{'PASS ✅' if ok else 'FAIL ❌'}  ({mb}MB)")
        results[label] = (ok, cos, max_err, mb)
    return results


def verify_generalizes(path, clips):
    """The exported graph must be length-agnostic.

    The legacy exporter emits a TracerWarning for sdpa's
    `is_causal = query.shape[2] > 1 and attention_mask is None and is_causal`
    — a Python bool baked in from the 16000-sample dummy. It resolves to False
    for every input we ever feed (the wav2vec2 encoder is non-causal and we pass
    no mask), but "should be constant" is an argument, not evidence. So run the
    ONNX graph against eager torchaudio at several real clip lengths, none of
    them the dummy length.
    """
    ta = fa._BUNDLE.get_model().eval()
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    print("\n== exported-graph length generalization (vs eager torchaudio) ==")
    worst = 1.0
    for name, wav in clips:
        with torch.inference_mode():
            ref, _ = ta(torch.from_numpy(wav.astype("float32")).unsqueeze(0))
        em = append_star(sess.run(["emission"], {"wav": normalize_waveform(wav)[None, :]})[0])[0]
        ref = ref.numpy()[0]
        cos = _cos(em, ref)
        agree = float((em.argmax(-1) == ref.argmax(-1)).mean())
        worst = min(worst, cos)
        print(f"  {name:22} {len(wav):6d} samples -> {em.shape[0]:4d} frames  "
              f"cosine={cos:.6f}  argmax-agree={agree:.3f}")
        if cos < 0.9999 or agree < 1.0:
            raise SystemExit(f"{name}: exported graph does not generalize to this length")
    return worst


def _cos(a, b):
    if a.shape != b.shape:
        print(f"    shape {a.shape} vs golden {b.shape}")
        return -1.0
    a, b = a.reshape(-1), b.reshape(-1)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def dump_kotlin_fixture(wav, out_dir):
    """Extra fixtures for the :core-align JVM test: the normalized waveform (so
    the Kotlin layer_norm port is checkable standalone) and the tokenized
    character ids per word (so word grouping is checkable without a tokenizer)."""
    d = os.path.join(GOLDEN, "mms")
    np.save(os.path.join(d, "ref_samantha_wav_normalized.npy"), normalize_waveform(wav))
    names = SENTENCE.rstrip(".").split()
    cleaned = [fa._clean(w) for w in names]
    keep = [i for i, c in enumerate(cleaned) if c]
    _, tokenizer, _ = fa._get_state()
    toks = tokenizer([cleaned[i] for i in keep])
    payload = {
        "sentence": SENTENCE,
        "words": names,
        "cleaned": cleaned,
        "keep_idx": keep,
        "tokens": [list(map(int, t)) for t in toks],
    }
    with open(os.path.join(d, "ref_samantha_tokens.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  wrote golden/mms/ref_samantha_wav_normalized.npy + ref_samantha_tokens.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_REPO, "build", "onnx"))
    ap.add_argument("--skip-export", action="store_true",
                    help="evaluate already-exported files")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    wav = np.load(os.path.join(GOLDEN, "wav", "ref_samantha.npy"))
    fp32 = os.path.join(args.out, "mms_fa_fp32.onnx")
    int8 = os.path.join(args.out, "mms_fa_int8_transformer.onnx")

    if not args.skip_export:
        print("== re-host MMS weights onto HF Wav2Vec2ForCTC ==")
        ta_inner = fa._BUNDLE.get_model().eval().model
        hf = build_hf(ta_inner)
        verify_parity(hf, wav)
        print("== export + quantize ==")
        fp32, int8 = export(hf, args.out)
        print(f"  fp32 {os.path.getsize(fp32)//1024//1024}MB  ->  "
              f"int8-transformer {os.path.getsize(int8)//1024//1024}MB")

    evaluate([("fp32", fp32), ("int8 transformer-only", int8)], wav)

    clips = [(n, np.load(os.path.join(GOLDEN, "wav", f"{n}.npy")))
             for n in ("crossvoice_daniel", "slow_samantha", "wrongtext_samantha")]
    verify_generalizes(fp32, clips)

    dump_kotlin_fixture(wav, args.out)


if __name__ == "__main__":
    main()
