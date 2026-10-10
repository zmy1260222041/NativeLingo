#!/usr/bin/env python3
"""Poll and download one safe ReduceFace job without modifying the input candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[7]
PLAYER_ROOT = PROJECT / "art/source/characters/chr_player_juvenile"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def without_signed_query(value):
    """Drop presigned URL queries (COS q-ak SecretId and signature) before a reply is stored."""
    if isinstance(value, dict):
        return {key: without_signed_query(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_signed_query(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value.split("?", 1)[0]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(PLAYER_ROOT))
    from cloud import ai3d_client, secret  # noqa: PLC0415
    secret_id, secret_key = secret.load_secret()
    response = ai3d_client.call("DescribeReduceFaceJob", {"JobId": args.job_id}, secret_id, secret_key)
    record = {"schema": "mira_reduceface_poll.v1", "polled_at_utc": datetime.now(timezone.utc).isoformat(), "job_id": args.job_id, "status": response.get("Status"), "request_id": response.get("RequestId"), "api_response": without_signed_query(response), "url_queries_removed": True}
    if str(response.get("Status", "")).upper() == "DONE":
        downloads = ai3d_client.download_result_files(response, output, name_prefix="reduceface_high_")
        record["downloads"] = [{"label": label, "file": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha256(path)} for label, path in downloads]
    path = output / "latest_poll.json"; path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_id": args.job_id, "status": record["status"], "downloads": record.get("downloads", [])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
