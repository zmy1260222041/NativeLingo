"""Verify immutable Stranger character sources against the lock manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = Path(__file__).with_name("ASSET_LOCK_MANIFEST.json")
FORBIDDEN_NAME_PARTS = (
    "subscription_key",
    "api_key",
    "signed_url",
    "rodin_submission_preflight",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    checked = 0

    for asset in manifest["assets"]:
        for item in asset["files"]:
            path = PROJECT_ROOT / item["path"]
            checked += 1
            if not path.is_file():
                failures.append(f"MISSING {item['path']}")
                continue
            actual_size = path.stat().st_size
            if actual_size != item["bytes"]:
                failures.append(
                    f"SIZE {item['path']}: expected {item['bytes']}, got {actual_size}"
                )
            actual_hash = sha256(path)
            if actual_hash != item["sha256"]:
                failures.append(
                    f"SHA256 {item['path']}: expected {item['sha256']}, got {actual_hash}"
                )

    character_root = Path(__file__).resolve().parent
    for path in character_root.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(part in lowered for part in FORBIDDEN_NAME_PARTS):
            failures.append(f"FORBIDDEN_ARTIFACT {path.relative_to(PROJECT_ROOT)}")

    if failures:
        print(f"Asset lock verification FAILED ({checked} protected files checked)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"Asset lock verification PASSED ({checked} protected files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
