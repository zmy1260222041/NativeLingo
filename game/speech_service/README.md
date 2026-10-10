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

## Current 2D speech backend (FR-46, R-35)

The default is **xAI TTS, US-East (`us-east-1`)**, using the existing server-only `XAI_API_KEY` or `XAI.csv`. All authored lines, word models and dynamic replies use `https://api.x.ai/v1/tts`; 24 kHz mono 16-bit PCM is streamed, then wrapped as valid WAV for playback/cache. The game never receives this credential. Gemini remains the text-only dialogue provider, and local Whisper/SSL-DTW remain the player recognition/scoring path. No player audio is sent to xAI TTS.

`STRANGER_TTS_PROVIDER=qwen` explicitly selects the historical backend described below; there is no automatic Beijing fallback on US TTS errors. The 2D voice cache uses a new namespace so earlier Qwen files cannot mask the change. Voices: Mira/Eve, Tavi/Ara, Ori/Eve, Rowan/Rex, Vesh/Leo (Mira and Ori share Eve). Each town profile carries pronouns that match its voice (Mira, Tavi, Ori: she/her; Rowan, Vesh: he/him), and every town dialogue payload includes `resident_pronouns` so one resident refers to another consistently.

`GET /health` reports `tts_provider`, `tts_region`, `tts_configured`, and a separate `dialogue_ready`; `GET /health?refresh=1` checks real Gemini generation. A configured key is not treated as successful dialogue. 2D requests include `require_live_dialogue=true`; model failure produces a retriable error, never a scored stub transaction.

`/health` judges each capability separately (FR-46 "失败如实提示"); `ok: true` only means the listener answered:

| Field | Meaning |
|---|---|
| `asr_ready` / `asr_reason` | Whisper actually loaded. `asr_reason` is `""` when ready, otherwise `not_checked` (no load attempted yet), `loading`, `asr_not_installed` (no `faster_whisper`), `model_missing` (no `models/whisper-base.en` and the `base.en` download failed) or `load_failed` (local model present but unusable). Each recording retries the load. The 2D client treats `not_checked`/`loading` as "starting" (no gesture minimum, quiet re-poll of `/health`), and only the last three as down. |
| `reference_scorer_ready` | The desktop SSL+DTW stack imported; when false, word practice uses the labelled transcript check described below. |
| `dialogue_ready` / `dialogue_reason` | Gemini generation verified. Without a Gemini key the reason is `not_configured`; an xAI-only setup reports `dialogue_provider: grok`, `dialogue_configured: true`, `dialogue_ready: false`, `dialogue_reason: provider_unverified` — Grok has no readiness probe and is not a supported 2D live path. |
| `tts_region` | `us-east-1` for xAI, `global` for Google Cloud TTS on its default endpoint (otherwise the endpoint host), `legacy-configured` for Qwen. |

`protocol` stays `2`; older fields are unchanged.

When `tts_configured` is false but dialogue works, the 2D town shows each validated reply as text and settles it after a short reading pause instead of its audio, so exchanges, Mira's greeting and orders still count (the campus already asks for text-only turns). Campus dialogue whose every repair attempt fails the content gates answers `422 campus_rejected` (or an SSE `error` with that reason), a free retry; `503 campus_unavailable` stays for provider or transport failures.

Dialogue failures keep the reasons Godot already localizes and add a machine-readable `detail`: `503 VOICE_REASON_SERVICE_UNAVAILABLE` with `detail: not_configured` (strict turn, no model key at all — checked before the relevance gate) or `provider_failed` (provider error/timeout); `422 VOICE_REASON_DIALOGUE_REJECTED` with `detail: reply_rejected` (the model answered but every candidate failed the content gates; the violations are logged as `stage=dialogue_rejected`) or `transcript_rejected` (offline relevance gate). When the work plane returns no usable `player_turn` (missing or truncated JSON), the score event carries `player_turn.idiomaticity: null` and `player_turn.idiomaticity_source: "unavailable"` (otherwise `gemini`, `grok` or `stub`) and `session.running_score: null`; no stub constant or parser default is ever reported as a model score.

Only local callers are served: a `Host` other than `127.0.0.1`/`localhost` (DNS rebinding) or an `Origin` other than absent/`null`/a localhost page gets `403`; JSON endpoints (`/game/dialogue`, `/game/campus/dialogue`, `/game/tts`, `/game/prewarm`) require `Content-Type: application/json` and audio endpoints (`/transcribe`, `/score_word`) require `audio/*`, otherwise `415`. This keeps CORS "simple" cross-site POSTs away from paid model and TTS calls; the Godot client sends exactly these headers. A malformed `Content-Length` or JSON body answers `400` instead of dropping the connection.

`game/run_novel.command` starts this service automatically for local desktop play. `probe_novel_live.py` is an opt-in paid API test: it plays synthetic WAVs through Godot's real recording effect and finish-recording upload path, and checks word acquisition, two-turn dialogue, audible playback completion and usable item rewards. It does not record the user's physical microphone.

Official API contract: [xAI TTS guide](https://docs.x.ai/developers/model-capabilities/audio/text-to-speech), [US-East region](https://docs.x.ai/developers/models/text-to-speech). Read on 2026-09-11; Context7 was unavailable in this session, so official documentation was used directly.

## Legacy Qwen NPC voice (FR-32, optional)

`POST /game/tts` (also `/tts`) synthesises server-known NPC lines with Qwen
`qwen-audio-3.0-tts-plus` over the dedicated WebSocket inference route
(`/api-ws/v1/inference`). The game sends only `npc_id + line_id + voice +
format`; the text comes from the server-side catalog and is never accepted
from the client. Install the SDK once into the project venv:

```sh
.venv/bin/pip install dashscope
```

Credentials are read from `TTS.csv` beside this service (git-ignored; move
operator-provided files there) or the repo root, or from the environment:

```sh
export QWEN_TTS_API_KEY=...   # or DASHSCOPE_API_KEY
export QWEN_TTS_WS_URL=wss://<host>/api-ws/v1/inference  # optional override
.venv/bin/python game/speech_service/server.py
```

The CSV only needs `apiKey` and `apiHost`. Each NPC has a default voice from
the model's two system voices — `longanlingxin` (female: Mira, Tavi, Ori) and
`longanlufeng` (male: Rowan, Vesh); `QWEN_TTS_VOICE` overrides all of them.
Qwen3-TTS voice names such as `Cherry` are rejected by this model family.

Without a key the endpoint returns 503 and the game falls back to the no-voice
text path. The cloud deployment uses the same endpoint contract and its own
catalog/cache (`server/backend/core/{npc_lines,qwen_tts}.py`).

## Google Cloud TTS (`STRANGER_TTS_PROVIDER=cloud`)

The only backend with a numeric speaking rate, and therefore the only one that
can implement the graded speech-rate design. **It cannot use an API key** — the
REST endpoint answers `401 UNAUTHENTICATED: API keys are not supported by this
API` — so it authenticates with a service account JSON, whose RS256 assertion
this service signs in process:

```sh
export STRANGER_TTS_PROVIDER=cloud
export GOOGLE_TTS_CREDENTIALS=/path/to/service-account.json  # or CloudTTS.json beside this file
export GOOGLE_TTS_SPEAKING_RATE=0.9   # optional; clamped to 0.25–2.0
.venv/bin/python game/speech_service/server.py
```

Full project setup, including the recorded IAM findings and the acceptance
check that measures whether slowing down preserves pitch, is in
`docs/cloud-tts-setup.md`; run
`.venv/bin/python game/speech_service/verify_cloud_tts.py` before trusting a
new voice. Signing needs `cryptography`, which the venv currently receives only
as a transitive dependency of `dashscope` — install it directly if the qwen
backend is ever removed.

Outbound traffic in this mode: NPC line text to `texttospeech.googleapis.com`
and the signed service-account assertion to `oauth2.googleapis.com`; no player
audio or transcript. Prewarm (at startup and on `POST /game/prewarm`) follows
the active provider: in cloud mode it only mints/caches the OAuth token and
never opens the DashScope/Qwen (Beijing) websocket pool, which is touched only
when `STRANGER_TTS_PROVIDER=qwen`.

## Service-point dialogue (FR-41)

`POST /game/dialogue` takes a transcript, role card id, and short history.
With `Accept: text/event-stream` it emits `speaking` (first sentence +
`reply_id`) then `score` (`player_turn`) then `done`. Without that header it
still returns one JSON object for tests and older clients. Godot then asks
`/game/tts` for that `reply_id`; free text from the client is rejected.
Both paths run social and town-orientation turns through the same social-depth
and town-attitude checks with up to three repair rounds. Campus lines
(`/game/campus/dialogue`) pass the same AI/prompt-injection/link/profanity gate
plus a narrow never-grade-aloud check (`your grammar`, `repeat after`,
`pronunciation score`, ...) inside their repair loop; malformed model fields
are retried before a line is published, never reported after it was spoken.

Set `GEMINI_API_KEY` (or a gitignored `GEMINI.csv` beside this service) to
send text-only scene cards to Gemini `gemini-3.1-flash-lite` with
`thinking_level=MINIMAL` over `streamGenerateContent`. Optional
`GEMINI_DIALOGUE_MODEL` overrides the model id. Gemini never receives audio.
`GEMINI_PROXY` routes Google traffic: `auto` (default) probes a token-free
direct GET first and only falls back to the `HTTPS_PROXY` env proxy when the
machine cannot reach Google natively (several proxy exit regions are rejected
by Gemini with "User location is not supported"); the winning route is cached
and re-discovered on the next prewarm once it starts failing. `off` never
proxies; `on` always honors the env proxy.
`POST /game/prewarm` runs a token-free GET for the shared Google HTTPS connection,
a tiny throttled streamed generation for the model data plane, and the TTS
websocket concurrently. The configured/prewarmed
live plane races two identical short-window requests (and starts a third only
after a tail-latency delay); only a safe, request-relevant Gemini utterance can
win. On a completion turn, a generic first sentence is not committed by itself:
the service waits within the same short window for at most a second sentence that
names the concrete inventory item and states the handoff. The online acceptance gate
requires `speaking.source=gemini`; the deterministic
stub remains only an outage/offline recovery path. Late Gemini JSON may improve
idiomaticity, but cannot reverse the already-spoken real-time transaction
commitment. `transaction_complete=true` additionally requires a completion speech
act, a non-question handoff phrase, and `requested_item == confirmed_item` (allowing
declared inventory aliases). Generic category terms are never settlement evidence.
Inventory matching accepts simple number inflection on both the transcript and
the committed NPC line (`two tacos` ↔ `taco`, `sandwiches` ↔ `sandwich`,
`a battery` ↔ `batteries`), and a quantity word never blocks an order.
Without a Gemini key, `XAI_API_KEY` / `XAI.csv` may still
call grok-4.3. With neither key, the stub completes in-inventory orders and
refuses off-inventory requests so local tests stay offline.

### Authorized caption corpus

`corpus_pipeline.py` prepares evidence-backed candidates from locally acquired
captions. Search specifications and the real-life source policy are in
`corpus_queries.json`. Before a subtitle is ingested, an operator must inspect
the title, description, channel, and visible video context. A real vlog or news
video is still insufficient when it contains only narration: the manifest must
identify an adjacent request and response spoken by two people in the recorded
event.

### Automatic native-speaker discovery

`native_speaker_screener.py` ranks videos as `reject`, `pending`, or
`candidate` from public metadata and caption-language keys. It never sets
`native_speaker_verified`. A `candidate` hit means the host looks like American English: a US news org,
an American self-identification, or a US on-location vlog. British and
other non-US sources stay pending. The person who answers in the clip is
still `not_evidenced`.

```sh
# Score already-downloaded yt-dlp info.json files. No network.
python3 game/speech_service/youtube_discover.py screen \
  --input game/speech_service/raw_captions \
  --output game/speech_service/corpus_work/native_speaker_screen.json

# Optional live search. Requires yt-dlp.
.venv/bin/pip install yt-dlp
python3 game/speech_service/youtube_discover.py search \
  --limit 6 \
  --output game/speech_service/corpus_work/native_speaker_search.json
```

Search is not “bakery” or “safe water” as a topic. Each scenario has query
families that ask for American counter talk (`can I get`, `for here or to go`,
`extra blanket`, `you can wait inside`) and then `scenario_search.py` checks
captions for an adjacent request and response. Reviews, UK clips, ESL lessons,
and whole-menu vlogs are excluded before ranking. Filmot searches put teaching
words in the title filter (`title=-learn+-dialogue+-ESL`) instead of the
transcript query, then drop remaining lesson cards locally.

### Source-first scene discovery

The five converted pilot IDs stay stable for save compatibility. When a phrase
produces few credible real-life exchanges, do not keep expanding that phrase
indefinitely. Run the source-first pass instead: collect real adjacent
request-response exchanges first, group repeated interactions into a scene
family, and only then decide whether that family should replace a pilot
scenario. A mapped scenario keeps its project-authored response patterns and
records the research family in `provenance`; it is still provisional until the
response speaker and rights are reviewed.

The saved-report pass is offline and consumes Filmot/YouTube reports. It does
not mark a native speaker or grant rights. The optional live YouTube pass below
downloads metadata and captions into ignored `corpus_work/`; it also does not
edit `game/data/dialogue` automatically:

```sh
python3 game/speech_service/native_scene_discovery.py extract \
  game/speech_service/corpus_work/filmot_chrome_search_round2.json \
  game/speech_service/corpus_work/us_dialogue_search.json \
  game/speech_service/corpus_work/native_speaker_search_round2.json \
  --metadata game/speech_service/corpus_work/native_speaker_screen.json \
  --metadata game/speech_service/corpus_work/native_speaker_search_round2.json \
  --output game/speech_service/corpus_work/native_scene_candidates.json
```

Each result is `research_candidate` evidence with a video URL, timestamp,
caption excerpt, scene family, and `native_speaker_verified=false`. The optional
metadata report fills in title/channel and host-screening evidence, but it does
not verify the person who answers in the clip. Create the human review sheet
from the candidate report:

```sh
python3 game/speech_service/native_scene_discovery.py review-template \
  game/speech_service/corpus_work/native_scene_candidates.json \
  --output game/speech_service/corpus_work/native_scene_review.json
```

The reviewer must confirm the real event, adjacent request-response, two
distinct speakers, American-English evidence for the response speaker, and
usable rights. The review sheet also requires at least two independent videos
for a repeated scene family and an explicit replacement target. The extractor
never applies that sheet or edits Godot assets; the runtime pattern JSON remains
project-authored until the ordinary corpus promotion gate passes.

For a new source-first YouTube pass, use the same filters and caption-window
scoring directly against YouTube search results:

```sh
.venv/bin/python game/speech_service/native_scene_discovery.py search \
  --limit 3 --families 6 \
  --output game/speech_service/corpus_work/native_scene_youtube_search.json
```

```sh
python3 game/speech_service/youtube_discover.py search --limit 6
```

The screen report is a research shortlist. `*_research_stubs.json` can seed a
manifest, but ingest still requires the ordinary human flags, and `promote`
still refuses anything that is not independently verified.

```json
{
  "sources": [{
    "source_id": "owned-bakery-001",
    "source_url": "https://www.youtube.com/watch?v=...",
    "transcript_path": "raw_captions/owned-bakery-001.vtt",
    "rights": "owned",
    "source_title": "Morning at the Neighborhood Bakery",
    "source_description": "Continuous footage of customers ordering at the counter.",
    "channel": "Neighborhood Bakery",
    "source_kind": "on_location_service_interaction",
    "metadata_review": {
      "title_checked": true,
      "description_checked": true,
      "channel_checked": true,
      "video_context_checked": true
    },
    "real_life_verified": true,
    "real_life_evidence": "The customer and employee are visible at the real counter.",
    "unscripted_verified": true,
    "unscripted_evidence": "Continuous service footage, not a lesson or demonstration.",
    "direct_dialogue_verified": true,
    "native_speaker_verified": true,
    "native_speaker_evidence": "signed production release",
    "verified_interaction_ranges": [{
      "scenario_id": "food_ask_bread",
      "request_start_seconds": 12.1,
      "request_end_seconds": 14.0,
      "response_start_seconds": 14.1,
      "response_end_seconds": 16.4,
      "request_speaker_role": "customer",
      "response_speaker_role": "bakery_staff",
      "distinct_speakers_verified": true,
      "evidence": "The staff response immediately follows the customer's request."
    }],
    "scenario_ids": ["food_ask_bread"]
  }]
}
```

Language courses, conversation practice, roleplay, film/TV clips, AI stories,
travel advice, reviews, and narrated explainers are rejected as dialogue
evidence. Verified response windows are used instead of keyword hits from the
whole subtitle, so a narrator mentioning "blanket" elsewhere in a hotel vlog
cannot become an NPC response.

Allowed rights values are `owned`, `licensed`, `cc0`, `cc_by`, and
`written_permission`. Raw captions and candidates stay under ignored
`raw_captions/` and `corpus_work/` directories and are excluded from Godot by
`.gdignore`. The workflow is:

For an exploratory research pass, a source may set `research_only: true` and use
`rights: research_pending`. This keeps the URL, timestamps, and evidence IDs in
the candidate report without treating the source as release-eligible. Research
candidates are never promoted by `promote` until their rights and native-speaker
review fields satisfy the normal allowed-rights checks.

```sh
python3 game/speech_service/corpus_pipeline.py queries
python3 game/speech_service/corpus_pipeline.py ingest \
  game/speech_service/corpus_work/manifest.json \
  game/speech_service/corpus_work/candidates.json

# A native editor reviews each item and sets approved=true before promotion.
python3 game/speech_service/corpus_pipeline.py promote \
  game/speech_service/corpus_work/candidates-reviewed.json \
  game/data/dialogue/response_patterns/authorized_corpus.json
```

Promotion preserves source ID, URL, timestamps, rights, and evidence ID. An
unknown-rights source, unverified speaker, missing file, non-observational
source, unverified interaction, or unapproved candidate cannot enter the
release pattern JSON.

### Grounding observed lines into Godot patterns

`promote` stays closed until rights clearance exists, so observed research can
still enrich the game through `ground_patterns.py`. The versioned, curated
`grounding_evidence.json` lists adjacent request-response exchanges that were
actually observed in sources which cleared an American-variety screening tier
(`screened_candidate_us_news`, or `us_onlocation_vlog_oembed` where the Filmot
card and YouTube oEmbed agree on a non-teaching US on-location channel). The
generator validates every entry against the scenario's allowed speech acts,
normalizes the derived line, deduplicates it against the existing pattern set,
and writes `corpus_grounded_patterns.json` plus refreshed
`response_pattern_ids` and provenance blocks in each scenario JSON. Grounded
lines are short normalized functional phrases with `project_owned` rights; the
clips themselves remain `research_pending` and nothing longer or verbatim is
shipped. Teaching channels found by phrase matching (the `-more-*` caption
batch) and non-American sources are listed in the file's `exclusions` and can
never ground a line.

```sh
python3 game/speech_service/ground_patterns.py run
```

The audit lands in the ignored `corpus_work/grounding_audit.json`. Water,
blanket, and shelter currently ground zero lines because no screened candidate
contains a natural service exchange for them yet.

## Word practice (FR-36, optional)

`POST /score_word` (also `/game/score_word`) scores one short WAV against a
server-catalog practice word. The client sends the lexical ID in
`X-Stranger-Lexical`; for NPC spoken-choice turns it sends a comma-separated
list (`food,water,parts`) and the server matches the transcript before scoring.
Text is never accepted from the client. Reference audio is synthesised with the
bundled Piper voice (the cloud endpoint uses the same voice), and the
Whisper-confidence proxy is always labelled when the SSL stack is unavailable.

Without the SSL stack the proxy (`pronunciation_source: whisper_confidence`) is
a binary recognition check, not a confidence: 80 when the transcript contains
the practice word as a whole word (case and punctuation are ignored, so
Whisper's `Morning.` or `Good morning.` count), otherwise 20. Spoken-choice
matching uses the same word-boundary rule (`I want water.` selects `water`).
An empty transcript returns `VOICE_REASON_CLARIFY`; if transcription itself
fails and there is no reference scorer, the endpoint returns
`503 VOICE_REASON_SERVICE_UNAVAILABLE` — a service fault is never reported as
a low score.

Unit tests (from the repository root; the modules import each other by
directory, so use discovery rather than dotted module names):

```sh
.venv/bin/python -m unittest discover -s game/speech_service -p 'test_*.py'
```

No unit test loads Whisper or calls a paid API. The Cloud TTS pitch-detector
tests skip unless `praat-parselmouth` (declared in `desktop/requirements.txt`)
is installed.
