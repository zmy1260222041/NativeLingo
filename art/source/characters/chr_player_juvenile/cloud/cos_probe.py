"""Free COS probe — lists buckets owned by the credential, without uploading.

ai3d's 3D-model-input jobs (``SubmitReduceFaceJob`` etc.) take a ``File3D.Url``
that must be a readable COS URL. This probe answers the two prerequisite
questions at once, for free:

  1. Does the SecretId/SecretKey have COS permission? (AccessDenied if not.)
  2. Does the account already own a bucket in the ai3d region (ap-guangzhou)?

COS uses its own HMAC-SHA1 signature (``q-sign-algorithm=sha1``), NOT TC3.
Run: ``python3 -m art.source.characters.chr_player_juvenile.cloud.cos_probe``
"""

from __future__ import annotations

import hashlib
import hmac
import time
import xml.etree.ElementTree as ET

import requests

from .secret import load_secret

COS_SERVICE_HOST = "service.cos.myqcloud.com"
COS_SERVICE_URL = f"https://{COS_SERVICE_HOST}/"


def _cos_auth_get_service(secret_id: str, secret_key: str, host: str) -> str:
    """Build the COS v5 Authorization header for GET Service (list buckets)."""
    start = int(time.time())
    end = start + 60
    key_time = f"{start};{end}"

    # SignString = method + "\n" + path + "\n" + params + "\n" + headers + "\n"
    sign_string = f"get\n/\n\nhost={host}\n"
    format_string = f"sha1\n{key_time}\n{hashlib.sha1(sign_string.encode('utf-8')).hexdigest()}\n"
    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()
    signature = hmac.new(sign_key.encode("utf-8"), format_string.encode("utf-8"), hashlib.sha1).hexdigest()

    return (
        f"q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={key_time}"
        f"&q-key-time={key_time}&q-header-list=host&q-url-param-list=&q-signature={signature}"
    )


def main() -> int:
    secret_id, secret_key = load_secret()
    auth = _cos_auth_get_service(secret_id, secret_key, COS_SERVICE_HOST)
    headers = {"Authorization": auth, "Host": COS_SERVICE_HOST}

    print(f"[cos-probe] GET {COS_SERVICE_URL}")
    resp = requests.get(COS_SERVICE_URL, headers=headers, timeout=15)
    print(f"[cos-probe] HTTP {resp.status_code}")

    if resp.status_code == 403:
        # Inspect the XML error to distinguish auth vs permission
        print(f"[cos-probe] 403 body: {resp.text[:300]}")
        print("[cos-probe] FAIL — SecretId/SecretKey lacks COS permission (CAM needs QcloudCOSData* on the sub-account).")
        return 3
    if resp.status_code != 200:
        print(f"[cos-probe] unexpected status; body: {resp.text[:300]}")
        return 4

    root = ET.fromstring(resp.text)
    buckets = []
    for b in root.findall(".//Bucket"):
        name = (b.findtext("Name") or "").strip()
        region = (b.findtext("Location") or "").strip()
        create = (b.findtext("CreateDate") or "").strip()
        if name:
            buckets.append((name, region, create))

    if not buckets:
        print("[cos-probe] OK auth, but the account owns NO buckets. A bucket in ap-guangzhou must be created first.")
        return 0

    print(f"[cos-probe] OK — account owns {len(buckets)} bucket(s):")
    gz = []
    for name, region, create in buckets:
        region_norm = region.lstrip("-") if region else "?"
        flag = ""
        if region_norm in ("ap-guangzhou", "guangzhou"):
            flag = "  ← ap-guangzhou (usable by ai3d ap-guangzhou jobs)"
            gz.append(name)
        print(f"   - {name}  region={region_norm}  created={create}{flag}")

    if gz:
        print(f"[cos-probe] Reusable ap-guangzhou bucket(s): {gz}")
    else:
        print("[cos-probe] No ap-guangzhou bucket found; create one (or confirm ai3d accepts cross-region COS).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
