"""Load Tencent Cloud SecretId/SecretKey from outside the repo.

The CSV is produced by the Tencent CAM console and carries a UTF-8 BOM, so it is
read with ``utf-8-sig``. The path lives outside the working tree by policy — see
``ASSET_LOCK_MANIFEST.json`` ``policy.credentials_must_not_be_stored`` — and the
values are never persisted anywhere inside the repo.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

DEFAULT_SECRET_PATH = Path(
    os.environ.get(
        "NATIVELINGO_HUNYUAN_SECRET",
        os.path.expanduser("~/Developer/NativeLingo-survival/混元SecretKey.csv"),
    )
)


class SecretError(RuntimeError):
    """Raised when the credential file is missing or malformed."""


def load_secret(pair: tuple[str, str] | None = None, path: Path | str | None = None) -> tuple[str, str]:
    """Return ``(secret_id, secret_key)`` read from the CAM CSV.

    The file must have a header row with ``SecretId`` and ``SecretKey`` columns.
    ``pair`` is ``(secret_id, secret_key)`` injected by tests / callers that
    already hold the values; when provided the file is not touched.
    """
    if pair is not None:
        secret_id, secret_key = pair
        if not secret_id or not secret_key:
            raise SecretError("injected secret pair has an empty value")
        return secret_id, secret_key

    secret_path = Path(path) if path else DEFAULT_SECRET_PATH
    if not secret_path.exists():
        raise SecretError(
            f"credential file not found at {secret_path}; set NATIVELINGO_HUNYUAN_SECRET "
            "or re-export from the Tencent CAM console"
        )

    with secret_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "SecretId" not in reader.fieldnames or "SecretKey" not in reader.fieldnames:
            raise SecretError(
                f"{secret_path} must have SecretId,SecretKey columns; got {reader.fieldnames!r}"
            )
        row = next(reader, None)
        if row is None:
            raise SecretError(f"{secret_path} has no data row")
        secret_id = (row.get("SecretId") or "").strip()
        secret_key = (row.get("SecretKey") or "").strip()
        if not secret_id or not secret_key:
            raise SecretError(f"{secret_path} has an empty SecretId/SecretKey value")
        return secret_id, secret_key
