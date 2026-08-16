"""Generate a Tripo 3D model of Mira from her 4 registered reference views.

Uses the source_locked reference images (figure_view_{0..3}_rgba.png, order
front / left / back / right per registration_report.json) as multiview input to
Tripo's multiview_to_model task. Key read from ~/.config/tripo/config (never
committed). Uploads each PNG to get a file_token, submits the task, polls, and
downloads the GLB into a tripo_source/ directory for Gate A.

Run:
  python3 art/source/characters/npcs/chr_npc_mira/source_locked_v06/tripo_generate.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

CONFIG = Path.home() / ".config" / "tripo" / "config"
BASE = "https://api.tripo3d.ai/v2/openapi"
MIRA_DIR = Path(__file__).resolve().parent  # source_locked_v06/
VIEWS = [
    ("front", "reference/figure_view_0_rgba.png"),
    ("character_left", "reference/figure_view_1_rgba.png"),
    ("back", "reference/figure_view_2_rgba.png"),
    ("character_right", "reference/figure_view_3_rgba.png"),
]
MODEL_VERSION = "P1-20260311"
OUT_DIR = MIRA_DIR / "tripo_source"


def load_api_key() -> str:
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TRIPO_API_KEY=") and not line.endswith("PLACEHOLDER"):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TRIPO_API_KEY 未配置于 %s" % CONFIG)


def api(path: str, data: dict, token: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit("API %s HTTP %s: %s" % (path, e.code, e.read().decode()[:300]))
    if body.get("code", 0) != 0:
        raise SystemExit("API %s error: %s" % (path, body))
    return body["data"]


def upload_image(path: Path, token: str) -> str:
    """POST multipart file → image_token (via upload/sts)."""
    boundary = "----tripo-bd"
    with open(path, "rb") as f:
        file_bytes = f.read()
    parts = []
    parts.append(b"--" + boundary.encode())
    parts.append(b'Content-Disposition: form-data; name="file"; filename="%s"' % path.name.encode())
    parts.append(b"Content-Type: image/png")
    parts.append(b"")
    parts.append(file_bytes)
    parts.append(b"--" + boundary.encode() + b"--\r\n")
    body = b"\r\n".join(parts)
    req = urllib.request.Request(
        BASE + "/upload/sts",
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary,
                 "Authorization": "Bearer " + token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit("upload HTTP %s: %s" % (e.code, e.read().decode()[:300]))
    return result["data"]["image_token"]


def poll_task(task_id: str, token: str, timeout_s: int = 600) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        req = urllib.request.Request(BASE + "/task/" + task_id,
                                     headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode())
        status = body.get("data", {}).get("status")
        print("  ... task %s status=%s" % (task_id[:8], status))
        if status == "success":
            return body["data"]
        if status == "failed":
            raise SystemExit("task failed: %s" % body.get("data", {}).get("error", "unknown"))
        time.sleep(5)
    raise SystemExit("task %s timed out" % task_id)


def main() -> None:
    token = load_api_key()
    os.makedirs(OUT_DIR, exist_ok=True)
    print("上传 4 张参考图...")
    files = []
    for name, rel in VIEWS:
        p = MIRA_DIR / rel
        tok = upload_image(p, token)
        files.append({"type": "png", "file_token": tok})
        print("  %s → %s" % (name, tok[:12]))
    print("提交 multiview_to_model (%s)..." % MODEL_VERSION)
    data = api("/task", {
        "type": "multiview_to_model",
        "model_version": MODEL_VERSION,
        "files": files,
        "texture": True,
        "pbr": True,
        "texture_alignment": "original_image",
    }, token)
    task_id = data["task_id"]
    print("task_id=%s" % task_id)
    result = poll_task(task_id, token)
    print("下载模型...")
    model_url = result.get("output", {}).get("model")
    if not model_url:
        raise SystemExit("no model URL in output: %s" % json.dumps(result)[:300])
    out = OUT_DIR / "mira_tripo_v01.glb"
    urllib.request.urlretrieve(model_url, out)
    print("TRIpo_DONE %s (%d KB)" % (out, out.stat().st_size // 1024))


if __name__ == "__main__":
    main()
