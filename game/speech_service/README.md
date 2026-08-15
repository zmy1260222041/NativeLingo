# Stranger local speech service

This optional service listens only on `127.0.0.1:17831`, transcribes short
English WAV recordings with the bundled `base.en` faster-whisper model, and
returns a narrow social-intent result. It does not own or mutate game state.

From the repository root:

```sh
.venv/bin/python game/speech_service/server.py
```

Health check:

```sh
curl http://127.0.0.1:17831/health
```

The Godot game remains fully playable when this process is absent. Hold `V`
near Mira or Rowan, speak, then release; use `G` for the always-available
gesture confirmation.
