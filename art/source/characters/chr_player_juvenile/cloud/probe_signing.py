"""Free signing probe — verifies TC3 auth against ai3d without spending credits.

Calls ``DescribeReduceFaceJob`` with a dummy JobId. Outcomes:
  * Error code starting ``AuthFailure`` → signing is broken (fix before any paid call).
  * Any other error code (``ResourceNotFound``/``InvalidParameter``/``FailedOperation``)
    → signing is correct; the service simply rejected the dummy id.
  * ``Response.JobId``/``Status`` echoed → signing correct AND the action accepts the param.

Run: ``python3 -m art.source.characters.chr_player_juvenile.cloud.probe_signing``
(or directly, adjusting sys.path).
"""

from __future__ import annotations

from .secret import load_secret
from . import ai3d_client
from .ai3d_client import Ai3dError


def main() -> int:
    secret_id, secret_key = load_secret()
    print(f"[probe] SecretId prefix: {secret_id[:6]}… ({len(secret_id)} chars)")
    print("[probe] POST DescribeReduceFaceJob {JobId: '0'} → expecting a business error, NOT AuthFailure")

    try:
        envelope = ai3d_client.call(
            "DescribeReduceFaceJob",
            {"JobId": "0"},
            secret_id,
            secret_key,
        )
    except Ai3dError as exc:
        if exc.code.startswith("AuthFailure"):
            print(f"[probe] FAIL — auth rejected: {exc.code}: {exc.message}")
            print("[probe] Signing chain is broken; do NOT proceed to paid jobs.")
            return 2
        print(f"[probe] OK — service reached and returned a business error: {exc.code}: {exc.message}")
        print("[probe] Signing chain works. Safe to proceed to paid jobs.")
        return 0

    # No error raised — action accepted the dummy id and returned something.
    print(f"[probe] OK — action accepted the call; envelope keys: {list(envelope.keys())}")
    print(f"[probe] envelope preview: {envelope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
