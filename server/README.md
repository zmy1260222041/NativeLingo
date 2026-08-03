# NativeLingo Cloud Server (`server/`)

The cloud Speaking backend that the Android app (v0.7+) talks to — a
Duolingo-style architecture: transcription, forced alignment, SSL scoring and
FR-11 phoneme diagnosis run server-side; the app uploads the learner take and
parses the result.

Deployed at `124.220.234.178:8756` (systemd unit `nativelingo.service`).

## Why this variant exists

The desktop backend (`backend/`, the torch implementation) needs ~4 GB of fp32
models and peaks at ~5.5 GB RAM. The deploy box has 3.7 GB RAM and 40 GB disk —
the torch stack does not fit. This variant runs the **same ONNX exports the
Android app ships** (R-5/R-6/R-7, validated on device) through onnxruntime:

| module           | desktop (torch)              | server (ORT)                  |
|------------------|------------------------------|-------------------------------|
| ssl_encoder      | wav2vec2-base-960h fp32 360MB| `w2v2_base_69_fp16.onnx` 146MB|
| forced_align     | torchaudio MMS_FA 1.2GB      | `mms_fa_int8_transformer.onnx` 355MB |
| phoneme (FR-11)  | espeak-cv-ft fp32 2.4GB      | `espeak_cv_ft_int8.onnx` 317MB |
| transcribe       | faster-whisper base.en 141MB | same                          |

Model footprint 0.8 GB, resident RAM ~1.5 GB. Parity was A/B-verified against
the torch staging backend on the same inputs: embeddings cosine = 1.000000
(max |Δ| 0.0037), 8/10 alignment spans byte-identical (the rest within ±2
frames — int8 jitter), and `/analyze_video` returned identical overall/accuracy/
fluency (60.6/33.3/88.0) with FR-11 tips firing on the same words.

## Layout

* `backend/core/onnx_runtime.py` — shared ORT plumbing: cached CPU sessions,
  the wav2vec2 (eps 1e-7) and MMS (eps 1e-5) normalizations that the exports
  leave out, log-softmax. The eps distinction is load-bearing (see
  `core-align/MmsEmitter.kt` for the Android twin).
* `backend/core/ssl_encoder.py` / `forced_align.py` / `phoneme.py` — ORT ports
  of the desktop modules, same public interfaces (`SSLEncoder.encode`,
  `align_words`, `decode_phonemes`/`diagnose_word_span`), so the rest of the
  pipeline (DTW, calibration, feedback, word-diff, Viterbi) is untouched.
* `backend/main.py` — same API as the desktop backend incl. `POST /videos`
  (upload a video → server-side transcription in one call).
* `requirements-server.txt` — no torch / torchaudio / transformers.

## Deploy (as done on 124.220.234.178)

```bash
rsync -az --exclude='__pycache__' server/ root@HOST:/opt/nativelingo/
# stage the ONNX exports + vocab.json into /opt/nativelingo/models/:
#   w2v2_base_69_fp16.onnx  mms_fa_int8_transformer.onnx
#   espeak_cv_ft_int8.onnx  vocab.json (from facebook/wav2vec2-lv-60-espeak-cv-ft)
python3 -m venv /opt/nativelingo/.venv
/opt/nativelingo/.venv/bin/pip install -r /opt/nativelingo/requirements-server.txt
# pre-warm the HF cache with the faster-whisper base.en model (the box cannot
# reach huggingface.co; rsync ~/.cache/huggingface/hub/models--Systran--faster-whisper-base.en)
```

`nativelingo.service` (systemd):

```
[Service]
WorkingDirectory=/opt/nativelingo
EnvironmentFile=/opt/nativelingo/nativelingo.env   # NATIVELINGO_TOKEN + dirs
ExecStart=/opt/nativelingo/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8756
Restart=always
```

Security: static bearer token (`NATIVELINGO_TOKEN`) on every endpoint except
`/health`; plain HTTP for now (TLS via Caddy/nginx is a documented follow-up —
the Tencent Cloud security group must open TCP 8756).

## Keeping in sync

`server/` is a deployment fork of `backend/` — when the desktop backend's
scoring logic changes, port the diff into the three ORT modules (the numpy
pipeline files are shared verbatim; only the model calls differ).
