"""Run ai3d ``SubmitReduceFaceJob`` (智能拓扑 / Polygen 1.5) on Mira's Hunyuan high-poly.

Reuses the player's proven cloud/ primitives (tencent_sign + ai3d_client + cos_upload +
secret) without touching player paths. Matches the player's LOD0 config that produced the
"OK" runtime model: FaceLevel=high, PolygonType=triangle. Input is the normalized textured
high-poly GLB; ReduceFace bakes it into the output IMAGE.

~50 credits (ai3d post-pay, same account as Hunyuan generation). Failed jobs do not deduct.
Outputs land under source_locked_v06/cloud_raw/; job log at cloud_jobs.json.

Run:
  python3 art/source/characters/npcs/chr_npc_mira/source_locked_v06/reduceface_run.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _proj_root() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here, *here.parents):
        if (cand / "CLAUDE.md").exists() and (cand / "art").is_dir():
            return cand
    raise RuntimeError("could not locate NativeLingo repo root")


PROJ = _proj_root()
V06 = Path(__file__).resolve().parent
# Reuse the player cloud package (importable as `cloud`).
sys.path.insert(0, str(PROJ / "art/source/characters/chr_player_juvenile"))
from cloud import ai3d_client, cos_upload, secret  # noqa: E402
from cloud.run_pipeline import measure_glb  # noqa: E402

INPUT_GLB = V06 / "hunyuan_processed/chr_npc_mira_hunyuan_v06_normalized.glb"
CLOUD_RAW = V06 / "cloud_raw"
JOB_LOG = V06 / "cloud_jobs.json"
BUCKET = "nativelingo-ai3d-1418160727"
REGION = "ap-guangzhou"
COS_PREFIX = "chr_npc_mira/v06"
FACE_LEVEL = "high"
POLY = "triangle"
STAGE = f"reduce-face-{FACE_LEVEL}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mask_url(url: str) -> str:
    return url.split("?", 1)[0] + "?<presigned>" if "?" in url else url


def _log(entry: dict) -> None:
    hist: list = []
    if JOB_LOG.exists():
        try:
            hist = json.loads(JOB_LOG.read_text(encoding="utf-8"))
            if not isinstance(hist, list):
                hist = []
        except json.JSONDecodeError:
            hist = []
    entry["logged_at"] = _now_iso()
    hist.append(entry)
    JOB_LOG.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if not INPUT_GLB.exists():
        print(f"input not found: {INPUT_GLB}", file=sys.stderr)
        return 2
    sid, skey = secret.load_secret()
    CLOUD_RAW.mkdir(parents=True, exist_ok=True)

    # 1. stage input on COS + presign GET (ai3d reads File3D.Url, must be a readable COS URL)
    key = f"{COS_PREFIX}/inputs/{INPUT_GLB.name}"
    client = cos_upload.make_client(sid, skey, REGION)
    print(f"[cos] upload {INPUT_GLB.name} -> {BUCKET}/{key} ({INPUT_GLB.stat().st_size/1024:.0f} KB)", flush=True)
    cos_upload.upload_file(client, BUCKET, key, INPUT_GLB)
    url = cos_upload.presign_get(client, BUCKET, key, 3600)
    print("[cos] presigned GET ready (1h)", flush=True)

    # 2. submit ReduceFace
    payload = {"File3D": {"Type": "GLB", "Url": url}, "FaceLevel": FACE_LEVEL, "PolygonType": POLY}
    job_id, req_id = ai3d_client.submit_job("SubmitReduceFaceJob", payload, sid, skey)
    print(f"[{STAGE}] submitted job_id={job_id} (req={req_id})", flush=True)

    # 3. poll (capture ResultCreditConsumed)
    cred = {"v": None}

    def _tick(jid: str, status: str, env: dict) -> None:
        c = env.get("ResultCreditConsumed")
        if c is not None and cred["v"] is None:
            cred["v"] = int(c)
        print(f"[{STAGE}] poll {jid} status={status} credits={c}", flush=True)

    final = ai3d_client.poll_job("DescribeReduceFaceJob", job_id, sid, skey, on_tick=_tick)
    status = str(final.get("Status", "")).upper()
    if final.get("ResultCreditConsumed") is not None:
        cred["v"] = int(final["ResultCreditConsumed"])
    print(f"[{STAGE}] final status={status} credits={cred['v']}", flush=True)

    entry = {
        "stage": STAGE, "action": "SubmitReduceFaceJob", "job_id": job_id,
        "status": status, "credits_consumed": cred["v"],
        "input_url": _mask_url(url), "request_ids": [req_id, final.get("RequestId", "")],
        "finished_at": _now_iso(),
    }
    if status != "DONE":
        entry["error"] = json.dumps(final, ensure_ascii=False)[:500]
        _log(entry)
        print(f"FAILED: {entry['error']}", flush=True)
        return 1

    # 4. download + measure
    downloads = ai3d_client.download_result_files(final, CLOUD_RAW, name_prefix=f"reduceface_{FACE_LEVEL}_")
    outs, meas = [], []
    for label, path in downloads:
        m = measure_glb(path)
        m["label"] = label
        outs.append({"label": label, "path": str(path.relative_to(PROJ)), "size_kb": m.get("size_kb")})
        meas.append(m)
        print(f"[{STAGE}] {label} -> {path.name} | tris={m.get('triangles')} verts={m.get('vertices')} "
              f"mats={m.get('materials')} anims={m.get('animations')}", flush=True)
    entry["output_files"], entry["measures"] = outs, meas
    _log(entry)
    print("REDUCEFACE_DONE " + json.dumps({
        "stage": STAGE, "status": status, "credits": cred["v"],
        "outputs": [{"label": o["label"], "tris": (m.get("triangles") if m.get("triangles") is not None else None)}
                    for o, m in zip(outs, meas)],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
