"""User accounts for the cloud Speaking track (v0.7.2).

Replaces the operator-issued activation-code flow as the *primary* path: a
user registers a username + password in the app and logs in on any of their
devices. The per-device token machinery (backend/core/devices.py) is reused
unchanged — login just issues a token for the requesting device instead of
exchanging a code, so each device is still individually revocable.

Password storage: scrypt (NIST-recommended memory-hard KDF, stdlib — no new
dependency) with a per-user random 16-byte salt, n=2**14. Plaintext never
touches disk or logs. Login is rate-limited per IP at the endpoint layer
(main.py) and scrypt itself is deliberately ~50 ms of work per attempt.

The activation-code path stays as an operator fallback (e.g. a guest device)
— `python -m backend.core.devices code` still works.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time

_LOCK = threading.Lock()

_SALT_BYTES = 16
_DKLEN = 32
_SCRYPT_N = 1 << 14   # ~50 ms per hash on the deploy box — cheap for login,
_SCRYPT_R = 8         # brutal for brute force
_SCRYPT_P = 1

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
_MIN_PASSWORD = 8
_MAX_PASSWORD = 128


def _state_dir() -> str:
    root = os.environ.get("NATIVELINGO_DATA_DIR") or "."
    d = os.path.join(root, "state")
    os.makedirs(d, exist_ok=True)
    return d


def _users_path() -> str:
    return os.path.join(_state_dir(), "users.json")


def _load() -> dict:
    try:
        with open(_users_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    tmp = _users_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _users_path())


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_DKLEN,
    )


def validate(username: str, password: str) -> str | None:
    """Return an error message, or None if the pair is acceptable."""
    if not _USERNAME_RE.match(username):
        return "用户名需为 3-32 位字母、数字、下划线或连字符"
    if len(password) < _MIN_PASSWORD:
        return f"密码至少 {_MIN_PASSWORD} 位"
    if len(password) > _MAX_PASSWORD:
        return f"密码最长 {_MAX_PASSWORD} 位"
    return None


def register(username: str, password: str) -> str | None:
    """Create an account. Returns an error message, or None on success."""
    err = validate(username, password)
    if err:
        return err
    salt = secrets.token_bytes(_SALT_BYTES)
    with _LOCK:
        data = _load()
        if username in data:
            return "用户名已存在"
        data[username] = {
            "salt": salt.hex(),
            "hash": _hash(password, salt).hex(),
            "created_at": round(time.time(), 1),
            "last_login": None,
        }
        _save(data)
    return None


def verify(username: str, password: str) -> bool:
    """Constant-time-ish password check (timing side channel on username
    existence is acceptable here — usernames are not secret)."""
    with _LOCK:
        entry = _load().get(username)
    if entry is None:
        # burn the same scrypt cost either way so the response time does not
        # reveal whether the username exists
        _hash(password, secrets.token_bytes(_SALT_BYTES))
        return False
    expected = bytes.fromhex(entry["hash"])
    actual = _hash(password, bytes.fromhex(entry["salt"]))
    ok = secrets.compare_digest(actual, expected)
    if ok:
        with _LOCK:
            data = _load()
            if username in data:
                data[username]["last_login"] = round(time.time(), 1)
                _save(data)
    return ok


def list_users() -> list[dict]:
    """Operator audit view — metadata only, never the password hash/salt."""
    with _LOCK:
        data = _load()
    return [
        {
            "username": u,
            "created_at": entry.get("created_at"),
            "last_login": entry.get("last_login"),
        }
        for u, entry in sorted(data.items(), key=lambda kv: kv[1].get("created_at", 0))
    ]


# ── CLI: `python -m backend.core.users users` ───────────────────────────────

def _main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="NativeLingo user management")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("users", help="list registered users")
    args = p.parse_args()
    for u in list_users():
        print(f"{u['username']}  created={u['created_at']}  last_login={u['last_login']}")


if __name__ == "__main__":
    _main()
