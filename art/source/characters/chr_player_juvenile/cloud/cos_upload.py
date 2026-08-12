"""COS upload + presigned-URL helper for feeding ai3d jobs.

ai3d's 3D-model-input jobs read inputs from a COS URL. We upload the file into
the project bucket (private read/write), then mint a short-lived presigned GET
URL and hand THAT to ai3d. The object itself stays private; only the presigned
URL is temporarily readable, so the asset is never public.

Bucket/region come from the pipeline config (``run_pipeline.py``). Credentials
come from :mod:`secret`. Uses the official ``cos-python-sdk-v5`` so the COS v5
signing is handled correctly for both PUT and presign.
"""

from __future__ import annotations

from pathlib import Path

from qcloud_cos import CosConfig, CosS3Client, CosServiceError

from .secret import load_secret

DEFAULT_REGION = "ap-guangzhou"


def make_client(secret_id: str, secret_key: str, region: str = DEFAULT_REGION) -> CosS3Client:
    config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key, Scheme="https")
    return CosS3Client(config)


def upload_file(client: CosS3Client, bucket: str, key: str, local_path: Path) -> None:
    """Upload ``local_path`` to ``bucket/key`` (overwrites if present)."""
    client.upload_file(Bucket=bucket, Key=key, LocalFilePath=str(local_path), EnableMD5=False)


def presign_get(client: CosS3Client, bucket: str, key: str, expires: int = 3600) -> str:
    """Return a presigned HTTPS GET URL valid for ``expires`` seconds."""
    return client.get_presigned_url(
        Method="GET", Bucket=bucket, Key=key, Expired=expires
    )


def upload_and_presign(
    local_path: Path,
    key: str,
    bucket: str,
    *,
    secret_id: str | None = None,
    secret_key: str | None = None,
    region: str = DEFAULT_REGION,
    expires: int = 3600,
) -> str:
    """One-shot: upload a file and return a presigned GET URL for it."""
    if secret_id is None or secret_key is None:
        secret_id, secret_key = load_secret()
    client = make_client(secret_id, secret_key, region)
    upload_file(client, bucket, key, local_path)
    return presign_get(client, bucket, key, expires)


def head_bucket(client: CosS3Client, bucket: str) -> bool:
    """True if the bucket exists and the credential can reach it."""
    try:
        client.head_bucket(Bucket=bucket)
        return True
    except CosServiceError as exc:
        return False
