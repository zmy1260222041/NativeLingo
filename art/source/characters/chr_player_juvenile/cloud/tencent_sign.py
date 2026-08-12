"""TC3-HMAC-SHA256 signer for the Tencent Cloud ``ai3d`` service.

Implements the signature v3 algorithm
(https://cloud.tencent.com/document/api/213/30654) without depending on the
external blender-copilot addon's ``_get_tencent_cloud_sign_headers``. The
runbook ``HUNYUAN_FROM_CONCEPT_RUNBOOK.md`` proved these parameters work for
``SubmitHunyuanTo3DProJob``; the same credential scope serves every other ai3d
action (``SubmitReduceFaceJob``, ``SubmitAutoRiggingJob``, ...).

Common params (Action / Version / Region) travel as ``X-TC-*`` headers, so the
canonical query string is empty. Three headers are signed: ``content-type``,
``host`` and ``x-tc-action``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

SERVICE = "ai3d"
HOST = "ai3d.tencentcloudapi.com"
VERSION = "2025-05-13"
REGION = "ap-guangzhou"
CONTENT_TYPE = "application/json; charset=utf-8"


class SignError(RuntimeError):
    """Raised on signing failures."""


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_signed_headers(
    secret_id: str,
    secret_key: str,
    action: str,
    payload: dict,
    *,
    region: str = REGION,
    version: str = VERSION,
    service: str = SERVICE,
    host: str = HOST,
) -> tuple[dict, str]:
    """Return ``(headers, payload_str)`` for a POST to the ai3d endpoint.

    ``payload_str`` is returned so the caller can send the exact bytes that were
    signed (the JSON must not be re-serialised, or the body hash would diverge).
    """
    if not secret_id or not secret_key:
        raise SignError("secret_id/secret_key are empty")

    payload_str = json.dumps(payload, ensure_ascii=False)
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")

    canonical_headers = (
        f"content-type:{CONTENT_TYPE}\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = (
        f"POST\n/\n\n"  # method, uri, empty query string
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{_sha256_hex(payload_str)}"
    )

    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = (
        f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{_sha256_hex(canonical_request)}"
    )

    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    headers = {
        "Authorization": authorization,
        "Content-Type": CONTENT_TYPE,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": region,
    }
    return headers, payload_str
