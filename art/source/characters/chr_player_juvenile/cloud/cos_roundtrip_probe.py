"""Round-trip COS probe — upload a tiny file, presign it, fetch it back.

Confirms the credential can PutObject + presign GET on the project bucket
before we commit a 28 MB GLB upload. Run:

    python3 -m art.source.characters.chr_player_juvenile.cloud.cos_roundtrip_probe --bucket <name> [--region ap-guangzhou]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import requests

from .secret import load_secret
from . import cos_upload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True, help="COS bucket name (name-appid)")
    parser.add_argument("--region", default=cos_upload.DEFAULT_REGION)
    args = parser.parse_args()

    secret_id, secret_key = load_secret()
    client = cos_upload.make_client(secret_id, secret_key, args.region)

    print(f"[cos-rt] head_bucket {args.bucket} @ {args.region}")
    if not cos_upload.head_bucket(client, args.bucket):
        print(f"[cos-rt] FAIL — cannot head bucket {args.bucket} (wrong region? missing CAM PutObject/HeadBucket?)")
        return 2
    print("[cos-rt] OK — bucket reachable")

    key = "probe/roundtrip-probe.txt"
    payload = b"nativelingo ai3d cos roundtrip probe " + str(Path(__file__).stat().st_mtime).encode()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    try:
        print(f"[cos-rt] upload {tmp_path.name} → {args.bucket}/{key}")
        cos_upload.upload_file(client, args.bucket, key, tmp_path)

        url = cos_upload.presign_get(client, args.bucket, key, expires=600)
        print(f"[cos-rt] presigned GET ({len(url)} chars), fetching back…")
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200 or resp.content != payload:
            print(f"[cos-rt] FAIL — presigned GET returned HTTP {resp.status_code}, body mismatch={resp.content != payload}")
            return 3
        print("[cos-rt] OK — uploaded, presigned, fetched, content matches.")
        print("[cos-rt] COS round-trip works. Safe to upload the 28 MB GLB and run ai3d jobs.")
        return 0
    finally:
        tmp_path.unlink(missing_ok=True)
        try:
            client.delete_object(Bucket=args.bucket, Key=key)
            print(f"[cos-rt] cleaned up {args.bucket}/{key}")
        except Exception as exc:  # noqa: BLE001
            print(f"[cos-rt] cleanup skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
