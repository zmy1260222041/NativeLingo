"""Generate a Hunyuan3D Pro base mesh for Mira from her 4 registered reference views.

Mirrors the verified v05 runbook for the player character
(art/source/characters/chr_player_juvenile/source_locked_v05/HUNYUAN_FROM_CONCEPT_RUNBOOK.md):
直签 Tencent CAM ai3d service (NOT the outdated blender addon path). Credentials are
read at runtime from the external CSV (~/Developer/NativeLingo-survival/混元SecretKey.csv,
utf-8-sig) and NEVER written into this tree.

Views order (per source_locked_v06/reference/registration_report.json):
  front (main) / character_left / back / character_right.

Run:
  python3 art/source/characters/npcs/chr_npc_mira/source_locked_v06/hunyuan_generate.py
"""
import base64
import csv
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

CREDS_CSV = Path.home() / "Developer/NativeLingo-survival/混元SecretKey.csv"
MIRA_DIR = Path(__file__).resolve().parent
VIEWS = [
    ("front", "reference/figure_view_0.png"),   # main image
    ("left", "reference/figure_view_1.png"),
    ("back", "reference/figure_view_2.png"),
    ("right", "reference/figure_view_3.png"),
]
SERVICE = "ai3d"
VERSION = "2025-05-13"
REGION = "ap-guangzhou"
ENDPOINT = "https://ai3d.tencentcloudapi.com"
MODEL = "3.1"
OUT_DIR = MIRA_DIR / "hunyuan_raw"
OUT_DIR.mkdir(exist_ok=True)


def load_creds() -> tuple[str, str]:
    with open(CREDS_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            return row["SecretId"], row["SecretKey"]
    raise SystemExit("混元SecretKey.csv 无数据")


def tencent_sign(secret_id: str, secret_key: str, action: str, payload: dict) -> dict:
    """TC3-HMAC signature, verbatim port of the verified blender-copilot addon
    ``_get_tencent_cloud_sign_headers`` (service=ai3d). Two details are mandatory and
    were missing from the first inline version (both → ``AuthFailure.SignatureFailure``):

    1. The canonical headers MUST include ``x-tc-action:<action lowercased>`` and
       ``signed_headers`` must be ``content-type;host;x-tc-action`` — not just
       ``content-type;host``.
    2. The string-to-sign's 2nd line is the UNIX **timestamp** (e.g. ``1723490000``),
       not an ISO-8601 stamp.
    """
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    host = ENDPOINT.split("//")[1]
    action_lower = action.lower()
    ct = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action_lower}\n"
    signed_headers = "content-type;host;x-tc-action"
    payload_str = json.dumps(payload)
    hashed_request_payload = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    canonical_request = ("POST" + "\n" + "/" + "\n" + "" + "\n" +
                         canonical_headers + "\n" + signed_headers + "\n" + hashed_request_payload)
    credential_scope = f"{date}/{SERVICE}/tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = ("TC3-HMAC-SHA256" + "\n" + str(timestamp) + "\n" +
                      credential_scope + "\n" + hashed_canonical_request)

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _sign(secret_date, SERVICE)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = ("TC3-HMAC-SHA256 Credential=" + secret_id + "/" + credential_scope +
                     ", SignedHeaders=" + signed_headers + ", Signature=" + signature)
    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": VERSION,
        "X-TC-Region": REGION,
    }


def call(action: str, payload: dict, secret_id: str, secret_key: str) -> dict:
    headers = tencent_sign(secret_id, secret_key, action, payload)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit("Hunyuan %s HTTP %s: %s" % (action, e.code, e.read().decode()[:500]))
    response = data.get("Response", {})
    err = response.get("Error")
    if err:
        raise SystemExit("Hunyuan %s API %s: %s (RequestId=%s)"
                         % (action, err.get("Code"), err.get("Message"), response.get("RequestId")))
    return data


def submit_job(secret_id: str, secret_key: str) -> str:
    data = {"Model": MODEL}
    for name, rel in VIEWS:
        p = MIRA_DIR / rel
        b64 = base64.b64encode(p.read_bytes()).decode()
        if name == "front":
            data["ImageBase64"] = b64
        else:
            data.setdefault("MultiViewImages", []).append(
                {"ViewType": name, "ViewImageBase64": b64})
    resp = call("SubmitHunyuanTo3DProJob", data, secret_id, secret_key)
    job_id = resp.get("Response", {}).get("JobId")
    print("提交成功 JobId=%s" % job_id)
    return job_id


def poll_job(job_id: str, secret_id: str, secret_key: str, timeout_s: int = 900) -> str:
    start = time.time()
    while time.time() - start < timeout_s:
        resp = call("QueryHunyuanTo3DProJob", {"JobId": job_id}, secret_id, secret_key)
        response = resp.get("Response", {})
        status = response.get("Status")
        print("  ... status=%s" % status)
        if status == "DONE":
            for f in response.get("ResultFile3Ds", []):
                if "GLB" in f.get("Type", ""):
                    return f["Url"]
            raise SystemExit("DONE 但无 GLB 结果: %s" % json.dumps(response)[:400])
        if status in ("FAILED", "CANCELLED"):
            raise SystemExit("任务失败: %s" % json.dumps(response)[:400])
        time.sleep(10)
    raise SystemExit("JobId %s 超时" % job_id)


def main() -> None:
    secret_id, secret_key = load_creds()
    print("用 ai3d 直签提交 Mira Hunyuan3D Pro (Model=%s, 四视图)..." % MODEL)
    job_id = submit_job(secret_id, secret_key)
    print("轮询...")
    url = poll_job(job_id, secret_id, secret_key)
    out = OUT_DIR / "mira_hunyuan_mv_v01.glb"
    urllib.request.urlretrieve(url, out)
    print("HUNYUAN_DONE %s (%d KB)" % (out, out.stat().st_size // 1024))


if __name__ == "__main__":
    main()
