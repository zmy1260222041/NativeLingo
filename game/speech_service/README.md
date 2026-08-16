# Stranger local speech service

This optional service listens only on `127.0.0.1:17831`, transcribes short
English WAV recordings with the bundled `base.en` faster-whisper model, and
returns a graded expression verdict (FR-28). It does not own or mutate game
state.

Each verdict has two 0–100 dimensions:

- **delivery** — deterministic word-boundary slot matching: did the request
  meaning get across? Grammar is never checked.
- **pronunciation** — SSL+DTW accuracy against a synthesised reference
  sentence when the desktop scoring stack is importable in this interpreter
  (`pronunciation_source: reference_dtw`); otherwise a Whisper
  acoustic-confidence proxy (`whisper_confidence`). The source is always
  reported and the proxy is never labelled as reference scoring.

`score = 0.5 × pronunciation + 0.5 × delivery`; reward bands are monotonic:
`>= 70 generous`, `40–69 sparse`, `< 40 none` (retry is free). The first
utterance can take a while because the service pre-warms Whisper and the
optional SSL encoder in a background thread.

From the repository root:

```sh
.venv/bin/python game/speech_service/server.py
```

Health check:

```sh
curl http://127.0.0.1:17831/health
```

The Godot game remains fully playable when this process is absent: the
`gesture_fallback` channel grants the minimum survival portions so the
three-day path can still be completed. Hold `V` near a resident, speak, then
release; use `G` for the always-available gesture confirmation.

Reference audio for the five intents lives in `reference_audio/` and is the
same set deployed to the cloud `/game/evaluate` endpoint (FR-29), so dev and
production score against identical audio.
