"""Device registration + per-device tokens.

Why this exists: the shared NATIVELINGO_TOKEN used to be baked into the APK
via BuildConfig — OWASP Mobile Top 10 (2024) M1: anything inside the APK is
extractable (apktool/jadx/strings), so the APK must contain NO credential.
The flow that replaces it:

  * the operator generates one-time registration codes on the server
    (`python -m backend.core.devices code`), valid 24 h, burned on use
  * the app POSTs /register {device_id, code} and receives a per-device token
  * device tokens are stored SHA-256-hashed, individually revocable
  * NATIVELINGO_TOKEN remains as the operator (admin) credential — it never
    leaves the server

State lives in ``<NATIVELINGO_DATA_DIR>/state/`` (devices.json + codes.json),
so it survives restarts and is excluded from the code tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time

_LOCK = threading.Lock()
_CODE_TTL_S = 24 * 3600          # registration codes expire after 24 h
_TOKEN_BYTES = 32                # 64 hex chars, ~256 bits of entropy
_CODE_BYTES = 4                  # 8 hex chars — short enough to type


def _state_dir() -> str:
    root = os.environ.get("NATIVELINGO_DATA_DIR") or "."
    d = os.path.join(root, "state")
    os.makedirs(d, exist_ok=True)
    return d


def _devices_path() -> str:
    return os.path.join(_state_dir(), "devices.json")


def _codes_path() -> str:
    return os.path.join(_state_dir(), "codes.json")


def _load(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── registration codes ──────────────────────────────────────────────────────

def issue_code() -> str:
    """Generate a one-time registration code (8 hex chars) valid 24 h."""
    code = secrets.token_hex(_CODE_BYTES)
    with _LOCK:
        data = _load(_codes_path())
        data[code] = {"expires": time.time() + _CODE_TTL_S}
        _save(_codes_path(), data)
    return code


def _consume_code(code: str) -> bool:
    """Validate + burn a registration code. Returns True once, then False."""
    code = code.strip().lower()
    with _LOCK:
        data = _load(_codes_path())
        entry = data.get(code)
        if entry is None:
            return False
        del data[code]
        _save(_codes_path(), data)
        return entry.get("expires", 0) > time.time()


# ── device tokens ───────────────────────────────────────────────────────────

def issue_token(device_id: str) -> str:
    """Create/rotate the token for a device (used by both the activation-code
    path and the account-login path). Re-registering the same id rotates the
    token — the old one stops working immediately."""
    token = secrets.token_hex(_TOKEN_BYTES)
    with _LOCK:
        data = _load(_devices_path())
        data[device_id] = {
            "token_hash": _sha256(token),
            "created_at": round(time.time(), 1),
            "last_seen": round(time.time(), 1),
        }
        _save(_devices_path(), data)
    return token


def register(device_id: str, code: str) -> str | None:
    """Bind a device id to a fresh token via a one-time activation code.
    Returns None on bad/expired code."""
    if not _consume_code(code):
        return None
    return issue_token(device_id)


def is_device_token(token: str) -> str | None:
    """Return the device_id whose token this is, or None."""
    digest = _sha256(token)
    with _LOCK:
        data = _load(_devices_path())
    for did, entry in data.items():
        if entry.get("token_hash") == digest:
            # last_seen is written on every authenticated request — cheap for
            # a personal server and gives the operator an audit trail.
            entry["last_seen"] = round(time.time(), 1)
            return did
    return None


def revoke(device_id: str) -> bool:
    """Revoke a device's token. Returns False if the id is unknown."""
    with _LOCK:
        data = _load(_devices_path())
        if device_id not in data:
            return False
        del data[device_id]
        _save(_devices_path(), data)
    return True


def list_devices() -> list[dict]:
    with _LOCK:
        data = _load(_devices_path())
    return [
        {"device_id": did, **entry}
        for did, entry in sorted(data.items(), key=lambda kv: kv[1].get("created_at", 0))
    ]


def admin_token() -> str | None:
    """The operator credential (never shipped in any APK)."""
    return os.environ.get("NATIVELINGO_TOKEN")


def is_admin_token(token: str) -> bool:
    admin = admin_token()
    return bool(admin) and secrets.compare_digest(token, admin)


# ── CLI: `python -m backend.core.devices code` ──────────────────────────────

def _main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="NativeLingo device registration management")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("code", help="issue a one-time registration code")
    sub.add_parser("devices", help="list registered devices")
    r = sub.add_parser("revoke", help="revoke a device's token")
    r.add_argument("device_id")
    args = p.parse_args()
    if args.cmd == "code":
        print(issue_code())
    elif args.cmd == "devices":
        for d in list_devices():
            print(f"{d['device_id']}  created={d['created_at']}  last_seen={d['last_seen']}")
    elif args.cmd == "revoke":
        print("revoked" if revoke(args.device_id) else "unknown device")


if __name__ == "__main__":
    _main()
