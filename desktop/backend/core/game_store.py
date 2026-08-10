"""On-device persistence for Survival attempts (R-14 G1/G2 corpus collection).

WHY NOT tempfile.mkdtemp  (红线 2)
  main.py's /recordings路径 uses `tempfile.mkdtemp(prefix="nativelingo_recordings_")`
  -- correct for its purpose (a scratch buffer for one shadowing session) and
  wrong for this one: it is gone on restart. The entire reason the beta build
  exists is to accumulate the >=200 labelled responses G1 needs and the >=8
  speakers G2 needs; collecting them into a temp dir would throw away the
  collection. So attempts land under NATIVELINGO_DATA_DIR, resolved exactly the
  way video.videos_dir does it (the Tauri shell sets that env var; the
  source-tree fallback is dev-only).

WHAT IS STORED AND WHY EACH FIELD IS THERE
  attempts/{aid}.wav    16 kHz mono PCM_16 -- the same shape audio_io.load_audio
                        hands the gates, so a collected clip needs no conversion
                        to be measured.
  attempts/{aid}.json   transcript + per-slot hit detail + delivery + decode
                        settings + tier/scenario. The decode block is recorded
                        per attempt because a clip transcribed under different
                        settings is a different measurement -- G2's numbers are
                        only meaningful against a known decoder.
  corrections/{aid}.json  FR-27. Kept in a SEPARATE file, never merged into the
                        attempt: the attempt records what the instrument heard,
                        the correction records what the human says was said.
                        Collapsing them would destroy the (A)/(B) distinction
                        the G2 criterion revision exists to preserve.

WHAT IS DELIBERATELY *NOT* STORED
  No `well_pronounced`. That annotation is a single-rater human judgement made
  afterwards while re-listening, and R-14 forbids the learner's own "I said it
  right" tap from standing in for it -- self-assessment is systematically
  optimistic, which is precisely the (A)/(B) conflation being separated. The
  export leaves the column empty for the annotator to fill.

NOTHING HERE LEAVES THE DEVICE. The beta build has no outbound surface at all
(no /game/review), so NFR-6's whitelist is empty for this round.
"""
from __future__ import annotations

import json
import os
import re
import uuid

# Bump when the on-disk attempt schema changes, same idiom as
# transcribe.CACHE_VERSION. Unlike a cache this is *collected data* -- old
# versions are kept and reported by the export, never silently regenerated.
STORE_VERSION = 1

_ID_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def game_dir(root: str | None = None) -> str:
    """Absolute path to the Survival data directory (created if missing)."""
    if root is None:
        root = os.environ.get("NATIVELINGO_DATA_DIR")
    if root is None:
        # desktop/backend/core/game_store.py -> repo root is three levels up.
        # (Bundled app sets NATIVELINGO_DATA_DIR and never reaches here.)
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    d = os.path.join(root, "game")
    os.makedirs(os.path.join(d, "attempts"), exist_ok=True)
    os.makedirs(os.path.join(d, "corrections"), exist_ok=True)
    return d


def new_attempt_id() -> str:
    return uuid.uuid4().hex[:16]


def _safe_id(aid: str) -> str:
    """Attempt ids reach here from a URL path, so validate rather than sanitise:
    a silently-rewritten id would read or overwrite someone else's attempt."""
    if not _ID_SAFE.match(str(aid or "")):
        raise ValueError(f"invalid attempt id: {aid!r}")
    return aid


def attempt_wav_path(aid: str, root: str | None = None) -> str:
    return os.path.join(game_dir(root), "attempts", f"{_safe_id(aid)}.wav")


def attempt_json_path(aid: str, root: str | None = None) -> str:
    return os.path.join(game_dir(root), "attempts", f"{_safe_id(aid)}.json")


def correction_path(aid: str, root: str | None = None) -> str:
    return os.path.join(game_dir(root), "corrections", f"{_safe_id(aid)}.json")


def _write_json(path: str, payload: dict) -> None:
    """Write via a temp file + rename so an interrupted write cannot leave a
    half-written attempt that later reads as corrupt corpus."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def save_attempt(aid: str, record: dict, root: str | None = None) -> str:
    """Persist one attempt's metadata. The wav is written separately by the
    caller (it owns the decoded waveform)."""
    path = attempt_json_path(aid, root)
    payload = dict(record)
    payload["attempt_id"] = aid
    payload["store_version"] = STORE_VERSION
    _write_json(path, payload)
    return path


def load_attempt(aid: str, root: str | None = None) -> dict:
    with open(attempt_json_path(aid, root), encoding="utf-8") as handle:
        return json.load(handle)


def save_correction(aid: str, record: dict, root: str | None = None) -> str:
    path = correction_path(aid, root)
    payload = dict(record)
    payload["attempt_id"] = aid
    payload["store_version"] = STORE_VERSION
    _write_json(path, payload)
    return path


def load_correction(aid: str, root: str | None = None) -> dict | None:
    path = correction_path(aid, root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def list_attempts(root: str | None = None) -> list[dict]:
    """Every stored attempt, oldest first, each with its correction attached
    under `correction` (None when the learner never corrected it).

    Unreadable files are skipped and counted by the caller rather than raising:
    one bad file must not make the whole collection unexportable."""
    d = os.path.join(game_dir(root), "attempts")
    out: list[dict] = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as handle:
                rec = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        aid = rec.get("attempt_id") or os.path.splitext(name)[0]
        rec["attempt_id"] = aid
        try:
            rec["correction"] = load_correction(aid, root)
        except ValueError:
            rec["correction"] = None
        out.append(rec)
    out.sort(key=lambda r: str(r.get("created_at") or ""))
    return out


def export_rows(root: str | None = None) -> dict:
    """Shape the collection into exactly what the two gate harnesses read.

    `delivery_rows` mirrors scripts/fixtures/game_delivery/responses.csv and
    `asr_manifest` mirrors scripts/fixtures/game_asr/manifest.json. Both leave
    the human-judgement columns EMPTY -- `delivered` and `origin` (G1),
    `expected_keywords` and `well_pronounced` (G2) are annotations made by
    listening to the audio, and prefilling them from the instrument's own output
    would make each gate grade its own homework.
    """
    attempts = list_attempts(root)
    delivery_rows = []
    asr_manifest = []
    for rec in attempts:
        aid = rec.get("attempt_id")
        correction = rec.get("correction") or {}
        corrected = str(correction.get("corrected_text") or "").strip()
        delivery_rows.append(
            {
                "response_id": aid,
                "scenario_id": rec.get("scenario_id") or "",
                "tier": rec.get("tier") or "",
                # what the production path produced; the corrected text rides in
                # its own column so G1 can be scored either way without losing
                # the distinction.
                "response_text": rec.get("transcript") or "",
                "corrected_text": corrected,
                "delivered": "",           # human ground truth, to be filled
                # Also a human column, and blank for the same reason as
                # `delivered`: the store cannot tell a person at the mic from a
                # speaker playing TTS back at it, so it must not self-certify
                # provenance. Blank reads as "unspecified" to G1, which withholds
                # its verdict until an annotator attests `real` while listening.
                # The collection route stays visible in `collection`, a column
                # the gate ignores.
                "origin": "",
                "collection": "beta-collect",
                "predicted_delivery": rec.get("delivery"),
                "predicted_delivered": rec.get("delivered"),
            }
        )
        asr_manifest.append(
            {
                "clip": f"{aid}.wav",
                "scenario": rec.get("scenario_id") or "",
                "tier": rec.get("tier") or "",
                "expected_keywords": [],   # from listening, not from the transcript
                "well_pronounced": [],     # single-rater, filled while re-listening
                "intended": corrected,     # the learner's own correction, if any
                "asr_text": rec.get("transcript") or "",
            }
        )
    return {
        "store_version": STORE_VERSION,
        "count": len(attempts),
        "corrected_count": sum(1 for r in attempts if r.get("correction")),
        "clips_dir": os.path.join(game_dir(root), "attempts"),
        "delivery_rows": delivery_rows,
        "asr_manifest": asr_manifest,
        "annotation_todo": [
            "delivery_rows[].delivered —— 听录音判「意思是否传达」(G1 ground truth)",
            "delivery_rows[].origin —— 听录音确认是真人应答后填 real;"
            "空着 G1 就不给裁决(仪器无法自证录到的是人还是外放的 TTS)",
            "asr_manifest[].expected_keywords —— 听录音填,不看 asr_text",
            "asr_manifest[].well_pronounced —— 不看上下文单听能否辨认;要么全标要么全不标",
        ],
    }
