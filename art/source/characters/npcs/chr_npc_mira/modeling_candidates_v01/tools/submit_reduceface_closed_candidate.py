#!/usr/bin/env python3
"""Submit the verified closed Mira candidate to Tencent ReduceFace (non-destructive)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[7]
PLAYER_ROOT = PROJECT / "art/source/characters/chr_player_juvenile"
BUCKET = "nativelingo-ai3d-1418160727"
REGION = "ap-guangzhou"
COS_PREFIX = "chr_npc_mira/modeling_locked_a_pose_v01/reduceface"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    if candidate.suffix.lower() != ".glb" or not candidate.is_file():
        raise RuntimeError(f"Expected existing GLB candidate, got {candidate}")
    sys.path.insert(0, str(PLAYER_ROOT))
    from cloud import ai3d_client, cos_upload, secret  # noqa: PLC0415
    secret_id, secret_key = secret.load_secret()
    client = cos_upload.make_client(secret_id, secret_key, REGION)
    key = f"{COS_PREFIX}/inputs/{candidate.name}"
    cos_upload.upload_file(client, BUCKET, key, candidate)
    url = cos_upload.presign_get(client, BUCKET, key, 3600)
    payload = {"File3D": {"Type": "GLB", "Url": url}, "FaceLevel": "high", "PolygonType": "triangle"}
    job_id, request_id = ai3d_client.submit_job("SubmitReduceFaceJob", payload, secret_id, secret_key)
    record = {
        "schema": "mira_reduceface_submission.v1",
        "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
        "action": "SubmitReduceFaceJob", "job_id": job_id, "request_id": request_id,
        "input": {"file": str(candidate), "bytes": candidate.stat().st_size, "sha256": sha256(candidate), "topology_gate": "closed candidate audited before submission"},
        "parameters": {"File3D.Type": "GLB", "FaceLevel": "high", "PolygonType": "triangle"},
        "input_url": url.split("?", 1)[0] + "?<presigned>",
        "credentials": "read externally at runtime; not stored in this record"
    }
    path = output / "submit.json"; path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": job_id, "request_id": request_id, "audit": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
