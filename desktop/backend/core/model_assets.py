"""Pinned Hugging Face artifacts used by the Memorizing module.

The model repositories are pinned to immutable commit revisions.  We also
verify the large weight file's exact byte size and SHA-256 once per process so
an interrupted/manual cache copy cannot be mistaken for a usable model.
"""
from __future__ import annotations

import functools
import hashlib
import os

QWEN_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
QWEN_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
QWEN_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
QWEN_SIZE = 491_400_032
QWEN_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"

YOLO_REPO = "ultralytics/assets"
YOLO_REVISION = "v8.4.0"
YOLO_SOURCE_FILENAME = "yoloe-26s-seg-pf.pt"
YOLO_SOURCE_SIZE = 32_696_887
YOLO_SOURCE_SHA256 = "9f0cefea64c48103a917dbc8ea4baf581aaf6ffa286675861dafd6fd04826f50"
YOLO_FILENAME = "yoloe-26s-pf.onnx"
YOLO_SIZE = 45_190_231
YOLO_SHA256 = "b54b75dfdc803038c5dbbd510898c99fad0cc17e2a7577f33406af135c73028d"

# Native Transformers conversion of Microsoft's Florence-2-base-ft weights.
# This avoids executing the original repository's legacy remote Python code,
# which is incompatible with Transformers 5.x and awkward to freeze safely.
FLORENCE_REPO = "florence-community/Florence-2-base-ft"
FLORENCE_ORIGIN = "microsoft/Florence-2-base-ft"
FLORENCE_REVISION = "0b03b6f15a4a211370fb204aee4e7dd48887ea37"
FLORENCE_FILENAME = "model.safetensors"
FLORENCE_SIZE = 463_178_864
FLORENCE_SHA256 = "ab06dea66b16d5e54513256d64854be2194443452fd0d84353b40a278bf87d42"


class ModelIntegrityError(RuntimeError):
    """A cached model artifact does not match the pinned manifest."""


@functools.lru_cache(maxsize=4)
def verify_file(path: str, expected_size: int, expected_sha256: str) -> str:
    actual_size = os.path.getsize(path)
    if actual_size != expected_size:
        raise ModelIntegrityError(
            f"{os.path.basename(path)} has {actual_size} bytes; expected {expected_size}"
        )
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise ModelIntegrityError(
            f"{os.path.basename(path)} SHA-256 mismatch "
            f"({actual_sha256[:12]}…, expected {expected_sha256[:12]}…)"
        )
    return path


def download_verified(
    repo_id: str,
    filename: str,
    revision: str,
    expected_size: int,
    expected_sha256: str,
) -> str:
    """Resolve a pinned HF artifact and verify its local cache contents."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)
    return verify_file(path, expected_size, expected_sha256)
