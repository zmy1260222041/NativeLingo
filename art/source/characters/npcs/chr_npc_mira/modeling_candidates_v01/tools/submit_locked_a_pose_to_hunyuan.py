#!/usr/bin/env python3
"""Submit the Mira A-pose-only modeling lock to Tencent Hunyuan3D Pro.

Uses the repository's previously verified TC3 signer without modifying the original
source lock.  The local audit record intentionally stores only filenames/hashes and
the non-secret API response, never image payloads or credentials.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path


FILES = (
    ("front", "chr_npc_mira_a_pose_front.png"),
    ("left", "chr_npc_mira_a_pose_character_left.png"),
    ("back", "chr_npc_mira_a_pose_back.png"),
    ("right", "chr_npc_mira_a_pose_character_right.png"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_hunyuan_client(path: Path):
    spec = importlib.util.spec_from_file_location("mira_hunyuan_client", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock-root", required=True, type=Path)
    parser.add_argument("--client", required=True, type=Path)
    args = parser.parse_args()
    root = args.lock_root.resolve()
    input_dir = root / "hunyuan_input"
    client = load_hunyuan_client(args.client.resolve())
    secret_id, secret_key = client.load_creds()

    payload = {"Model": "3.1"}
    audit_views = []
    for view, filename in FILES:
        path = input_dir / filename
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        if view == "front":
            payload["ImageBase64"] = encoded
        else:
            payload.setdefault("MultiViewImages", []).append({"ViewType": view, "ViewImageBase64": encoded})
        audit_views.append({"view": view, "file": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256(path)})

    response = client.call("SubmitHunyuanTo3DProJob", payload, secret_id, secret_key)
    reply = response.get("Response", {})
    record = {
        "schema": "mira_hunyuan_submission.v1",
        "scope": "A_POSE_ONLY_MODELING_LOCK",
        "model": "3.1",
        "action": "SubmitHunyuanTo3DProJob",
        "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
        "views": audit_views,
        "job_id": reply.get("JobId"),
        "request_id": reply.get("RequestId"),
        "api_response": reply,
        "credential_storage": "external CSV read at runtime; no credential stored here"
    }
    out = root / "hunyuan_submission" / "submit.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": record["job_id"], "request_id": record["request_id"], "audit": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
