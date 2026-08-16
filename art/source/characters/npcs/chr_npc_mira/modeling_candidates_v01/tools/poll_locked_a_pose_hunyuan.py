#!/usr/bin/env python3
"""Poll and download a Hunyuan3D Pro result for the Mira A-pose modeling lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


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
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    root = args.lock_root.resolve()
    client = load_hunyuan_client(args.client.resolve())
    secret_id, secret_key = client.load_creds()
    response = client.call("QueryHunyuanTo3DProJob", {"JobId": args.job_id}, secret_id, secret_key)
    reply = response.get("Response", {})
    record = {
        "schema": "mira_hunyuan_poll.v1",
        "job_id": args.job_id,
        "polled_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": reply.get("Status"),
        "request_id": reply.get("RequestId"),
        "api_response": reply,
    }
    if reply.get("Status") == "DONE":
        result = next((item for item in reply.get("ResultFile3Ds", []) if "GLB" in item.get("Type", "")), None)
        if result is None:
            raise RuntimeError("DONE without GLB result")
        output = root / "hunyuan_submission" / "mira_a_pose_hunyuan3d_pro.glb"
        urllib.request.urlretrieve(result["Url"], output)
        record["download"] = {"file": str(output.relative_to(root)), "bytes": output.stat().st_size, "sha256": sha256(output), "result_type": result.get("Type")}
    out = root / "hunyuan_submission" / "latest_poll.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": args.job_id, "status": record["status"], "poll": str(out), "download": record.get("download")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
