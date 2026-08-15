#!/usr/bin/env python3
"""Local capture server for the R-14 G1/G2 corpus collection page.

Review tool, not product code. R-14's P0 gates (G1/G2/G3) are unmet, so no
product implementation may start; this server exists only to collect the real
L2 recordings G1 and G2 need. It is deliberately isolated from
``desktop/src/`` -- nothing here is imported by the app.

Two jobs, and the first one is the reason this is a server at all rather than a
``file://`` page:

1. **Strip the scenarios before they reach the browser.** The page must never
   show ``slots.accept`` or ``reference_answer``: a speaker who has seen the
   accept set produces text that trivially matches it, and G1's precision then
   measures the prompt instead of the matcher (see
   ``scripts/fixtures/game_delivery/README.md``). The strip is a **whitelist**,
   not a blacklist -- ``_strip`` copies the five fields the page is allowed to
   render and drops everything else, so a future scenario field cannot leak by
   default. Dropped for cause, beyond those two:

   - ``npc.responses`` -- ``hit`` lines name the target ("Bread? Here you are.")
   - ``new_words`` -- that is the target vocabulary, verbatim
   - ``situation.en`` -- English phrasing to copy; the ASR corpus spec asks for
     a Chinese situation plus intent, with no English example
   - ``slots`` entirely, ``zh_hint`` included

2. **Write clips and skeletons to disk.** 120+ clips through browser downloads
   is worse than a loopback POST.

Binds 127.0.0.1 only. Nothing is served outside this directory, and uploads are
restricted to an audio-extension allowlist with sanitised names.

Usage::

    python3 scripts/collect/serve.py            # then open the printed URL
    python3 scripts/collect/serve.py --port 8080 --out /tmp/g2-capture

Outputs, under ``--out`` (default ``scripts/fixtures/game_asr/``):

    clips/<tier>-<scenario>-<speaker>-<seq>.<ext>
    manifest.json            G2 skeleton, exactly the schema in that README
    responses.skeleton.csv   G1 skeleton, exactly game_delivery/README.md's columns
    capture_log.jsonl        anonymised capture metadata (speaker code, L1, mime)

``manifest.json`` is kept to the documented schema with no extra keys, so the
capture metadata that backs the ">=8 speakers / >=3 L1" claim lives in
``capture_log.jsonl`` instead of being smuggled into the manifest.

**expected_keywords ships empty on purpose.** It is filled by a human listening
to the recording, per that README -- filling it from the intended prompt would
make G2 grade itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCENARIO_DIR = REPO / "desktop" / "backend" / "core" / "game_scenarios"
DEFAULT_OUT = REPO / "scripts" / "fixtures" / "game_asr"

# Whatever MediaRecorder hands us in WKWebView/Safari/Chrome. The ASR spec
# prefers .wav but reads .m4a/.webm/.flac via soundfile+librosa, and re-encoding
# here would defeat the point of capturing through the production path.
ALLOWED_EXT = {".m4a", ".mp4", ".webm", ".ogg", ".wav", ".flac"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
MAX_CLIP_BYTES = 32 * 1024 * 1024

CSV_COLUMNS = (
    "response_id",
    "scenario_id",
    "tier",
    "response_text",
    "delivered",
    "origin",
    "notes",
)


def _strip(raw: dict) -> dict | None:
    """Whitelist the fields the capture page is allowed to see.

    Returns ``None`` for a scenario missing the two fields the page needs, so a
    malformed file is skipped loudly rather than rendered blank.
    """
    situation = raw.get("situation") or {}
    greeting = (raw.get("npc") or {}).get("greeting")
    if not situation.get("zh") or not greeting:
        return None
    return {
        "id": raw.get("id"),
        "tier": raw.get("tier"),
        "need": raw.get("need"),
        "maslow_level": raw.get("maslow_level"),
        "situation_zh": situation["zh"],
        "greeting": greeting,
    }


def load_scenarios(scenario_dir: Path) -> list[dict]:
    scenarios: list[dict] = []
    for path in sorted(scenario_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  skip {path.name}: {exc}", file=sys.stderr)
            continue
        stripped = _strip(raw)
        if stripped is None:
            print(f"  skip {path.name}: no situation.zh / npc.greeting", file=sys.stderr)
            continue
        scenarios.append(stripped)
    return scenarios


def _load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"  warn: {path} unreadable, starting a fresh one", file=sys.stderr)
        return fallback


def _csv_cell(value: str) -> str:
    text = "" if value is None else str(value)
    if any(ch in text for ch in ',"\n\r'):
        return '"' + text.replace('"', '""') + '"'
    return text


class Handler(BaseHTTPRequestHandler):
    server_version = "SurvivalCapture/1.0"
    scenarios: list[dict] = []
    out_dir: Path = DEFAULT_OUT

    # -- helpers ---------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _read_body(self, limit: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "bad Content-Length"})
            return None
        if length <= 0:
            self._json(400, {"error": "empty body"})
            return None
        if length > limit:
            self._json(413, {"error": f"body over {limit} bytes"})
            return None
        return self.rfile.read(length)

    def log_message(self, fmt: str, *args) -> None:  # quieter default log
        if self.command != "GET":
            super().log_message(fmt, *args)

    # -- GET -------------------------------------------------------------

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/collect.js":
            return self._static("collect.js", "text/javascript; charset=utf-8")
        if path == "/scenarios.json":
            return self._json(200, self.scenarios)
        self._json(404, {"error": "not found"})

    def _static(self, name: str, ctype: str) -> None:
        target = HERE / name
        try:
            body = target.read_bytes()
        except OSError:
            return self._json(404, {"error": f"{name} missing"})
        self._send(200, body, ctype)

    # -- POST ------------------------------------------------------------

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/clip/"):
            return self._save_clip(path[len("/clip/") :])
        if path == "/finish":
            return self._finish()
        self._json(404, {"error": "not found"})

    def _save_clip(self, name: str) -> None:
        if not SAFE_NAME.match(name):
            return self._json(400, {"error": f"unsafe clip name: {name!r}"})
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_EXT:
            return self._json(400, {"error": f"extension not allowed: {suffix!r}"})
        body = self._read_body(MAX_CLIP_BYTES)
        if body is None:
            return

        clips = self.out_dir / "clips"
        clips.mkdir(parents=True, exist_ok=True)
        target = clips / name
        if target.exists():
            # Never overwrite a recording: a repeated speaker code would
            # silently destroy an earlier session's clips.
            stem, ext = target.stem, target.suffix
            n = 2
            while (clips / f"{stem}-r{n}{ext}").exists():
                n += 1
            target = clips / f"{stem}-r{n}{ext}"
        target.write_bytes(body)
        self._json(200, {"clip": target.name, "bytes": len(body)})

    def _finish(self) -> None:
        body = self._read_body(4 * 1024 * 1024)
        if body is None:
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            rows = payload["rows"]
            assert isinstance(rows, list)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, AssertionError):
            return self._json(400, {"error": "expected {\"rows\": [...]}"})

        self.out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.out_dir / "manifest.json"
        csv_path = self.out_dir / "responses.skeleton.csv"
        log_path = self.out_dir / "capture_log.jsonl"

        manifest = _load_json(manifest_path, [])
        if not isinstance(manifest, list):
            manifest = []
        seen = {row.get("clip") for row in manifest if isinstance(row, dict)}

        added = 0
        csv_lines: list[str] = []
        log_lines: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            clip = row.get("clip")
            scenario = row.get("scenario")
            tier = row.get("tier")
            if not clip or not scenario or clip in seen:
                continue
            seen.add(clip)
            added += 1
            # Exactly game_asr/README.md §4's schema, no extra keys.
            # expected_keywords stays empty: a human fills it by listening.
            manifest.append(
                {
                    "clip": clip,
                    "scenario": scenario,
                    "tier": tier,
                    "expected_keywords": [],
                    "intended": "",
                }
            )
            stem = Path(clip).stem
            csv_lines.append(
                ",".join(
                    _csv_cell(v)
                    for v in (stem, scenario, tier, "", "", "real", "")
                )
            )
            log_lines.append(
                json.dumps(
                    {
                        "clip": clip,
                        "scenario": scenario,
                        "tier": tier,
                        "speaker": row.get("speaker"),
                        "l1": row.get("l1"),
                        "mime": row.get("mime"),
                        "duration_s": row.get("duration_s"),
                        "recorded_at": row.get("recorded_at"),
                        "capture_page": row.get("capture_page"),
                    },
                    ensure_ascii=False,
                )
            )

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if not csv_path.exists():
            csv_path.write_text(",".join(CSV_COLUMNS) + "\n", encoding="utf-8")
        if csv_lines:
            with csv_path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(csv_lines) + "\n")
        if log_lines:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(log_lines) + "\n")

        self._json(
            200,
            {
                "added": added,
                "manifest_rows": len(manifest),
                "manifest": str(manifest_path),
                "csv": str(csv_path),
                "log": str(log_path),
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8756)
    parser.add_argument("--scenarios", type=Path, default=SCENARIO_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.scenarios.is_dir():
        print(f"scenario dir not found: {args.scenarios}", file=sys.stderr)
        return 2

    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        print(f"no usable scenarios in {args.scenarios}", file=sys.stderr)
        return 2

    tiers: dict[str, int] = {}
    for item in scenarios:
        tiers[item["tier"]] = tiers.get(item["tier"], 0) + 1

    Handler.scenarios = scenarios
    Handler.out_dir = args.out.resolve()

    print(f"scenarios : {len(scenarios)}  {tiers}")
    print("fields    : id / tier / need / maslow_level / situation_zh / greeting")
    print("            (accept, reference_answer, npc.responses, new_words,")
    print("             situation.en, slots all dropped before serving)")
    print(f"output    : {Handler.out_dir}")
    print(f"open      : http://127.0.0.1:{args.port}/")
    print("            probe round default: infant 10 + toddler 10 per speaker")
    print("            override: /?tiers=youth:6,professional:6")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
