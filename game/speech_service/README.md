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

## NPC voice (FR-32, optional)

`POST /game/tts` (also `/tts`) synthesises server-known NPC lines with Qwen
`qwen-audio-3.0-tts-plus`. The game sends only `npc_id + line_id + voice +
format`; the text comes from the server-side catalog and is never accepted
from the client. Configure the provider key in the environment (never in git):

```sh
export QWEN_TTS_API_KEY=...   # or DASHSCOPE_API_KEY
export QWEN_TTS_VOICE=Cherry  # optional
.venv/bin/python game/speech_service/server.py
```

Without a key the endpoint returns 503 and the game silently falls back to
subtitles. The cloud deployment uses the same endpoint contract and its own
catalog/cache (`server/backend/core/{npc_lines,qwen_tts}.py`).

## Word practice (FR-36, optional)

`POST /score_word` (also `/game/score_word`) scores one short WAV against a
server-catalog practice word. The client sends the lexical ID in
`X-Stranger-Lexical`; text is never accepted from the client. Reference audio is
synthesised with the bundled Piper voice (the cloud endpoint uses the same
voice), and the Whisper-confidence proxy is always labelled when the SSL stack
is unavailable.

Unit tests:

```sh
.venv/bin/python -m unittest game.speech_service.test_tts -v
```
