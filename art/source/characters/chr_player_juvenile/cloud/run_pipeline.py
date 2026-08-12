"""Orchestrates ai3d cloud jobs for the chr_player_juvenile Gate D pipeline.

One subcommand per stage; each does: upload input to COS → presign → submit →
poll → download to ``source_locked_v06/cloud_raw/`` → measure → append to
``source_locked_v06/cloud_jobs.json``. Run one stage at a time so results can
be measured and the next stage only fires when the previous looks right.

Examples
--------
    # LOD0 (must end up ≤32k tris)
    python3 -m art.source.characters.chr_player_juvenile.cloud.run_pipeline reduce-face --face-level high
    # LOD1 / LOD2
    python3 -m ...run_pipeline reduce-face --face-level medium
    python3 -m ...run_pipeline reduce-face --face-level low
    # rig + idle preset on the LOD0 output
    python3 -m ...run_pipeline auto-rig --input cloud_raw/reduceface_high_00.glb --motion 26
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .secret import load_secret
from . import cos_upload
from . import ai3d_client

# ---- config -----------------------------------------------------------------

PROJECT = Path(__file__).resolve().parents[5]
CHAR_ROOT = PROJECT / "art/source/characters/chr_player_juvenile"
V06_ROOT = CHAR_ROOT / "source_locked_v06"
CLOUD_RAW = V06_ROOT / "cloud_raw"
JOB_LOG = V06_ROOT / "cloud_jobs.json"

V05_INPUT_GLB = CHAR_ROOT / "source_locked_v05/hunyuan_processed/hunyuan_multiview_v3_1_normalized.glb"

BUCKET = "nativelingo-ai3d-1418160727"
REGION = "ap-guangzhou"
COS_PREFIX = "chr_player_juvenile/v06"
PRESIGN_EXPIRES = 3600  # ai3d must fetch within 1h


# ---- job log ----------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_job_log(entry: dict) -> None:
    JOB_LOG.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []
    if JOB_LOG.exists():
        try:
            history = json.loads(JOB_LOG.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []
    entry.setdefault("logged_at", _now_iso())
    history.append(entry)
    JOB_LOG.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- glb measurement --------------------------------------------------------


def measure_glb(path: Path) -> dict:
    """Return {triangles, vertices, meshes, materials, skins, animations, morphs, nodes, size_kb}."""
    out: dict[str, Any] = {"path": str(path.relative_to(PROJECT)), "size_kb": round(path.stat().st_size / 1024, 1)}
    try:
        with path.open("rb") as f:
            data = f.read()
        if data[:4] != b"glTF":
            out["error"] = "not GLB"
            return out
        length = struct.unpack("<I", data[8:12])[0]
        offset = 12
        gltf = None
        while offset < length:
            chunk_len = struct.unpack("<I", data[offset:offset + 4])[0]
            chunk_type = data[offset + 4:offset + 8]
            chunk_data = data[offset + 8:offset + 8 + chunk_len]
            if chunk_type == b"JSON":
                gltf = json.loads(chunk_data.decode("utf-8").rstrip("\x00").rstrip())
            offset += 8 + chunk_len
        if gltf is None:
            out["error"] = "no JSON chunk"
            return out
        accessors = gltf.get("accessors", [])
        tris = verts = 0
        for mesh in gltf.get("meshes", []):
            for prim in mesh.get("primitives", []):
                idx = prim.get("indices")
                if idx is not None and idx < len(accessors):
                    tris += accessors[idx].get("count", 0) // 3
                pos = prim.get("attributes", {}).get("POSITION")
                if pos is not None and pos < len(accessors):
                    verts += accessors[pos].get("count", 0)
        morphs = 0
        for mesh in gltf.get("meshes", []):
            for prim in mesh.get("primitives", []):
                if "targets" in prim:
                    morphs += len(prim["targets"])
        out.update(
            triangles=tris,
            vertices=verts,
            meshes=len(gltf.get("meshes", [])),
            materials=len(gltf.get("materials", [])),
            skins=len(gltf.get("skins", [])),
            animations=len(gltf.get("animations", [])),
            morph_target_blocks=morphs,
            nodes=len(gltf.get("nodes", [])),
            generator=(gltf.get("asset", {}).get("generator") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = repr(exc)
    return out


# ---- COS staging ------------------------------------------------------------


def stage_input(local_path: Path, secret_id: str, secret_key: str) -> str:
    """Upload ``local_path`` to COS and return a presigned GET URL."""
    key = f"{COS_PREFIX}/inputs/{local_path.name}"
    client = cos_upload.make_client(secret_id, secret_key, REGION)
    print(f"[cos] upload {local_path.name} → {BUCKET}/{key} ({local_path.stat().st_size/1024:.0f} KB)")
    cos_upload.upload_file(client, BUCKET, key, local_path)
    url = cos_upload.presign_get(client, BUCKET, key, PRESIGN_EXPIRES)
    print(f"[cos] presigned GET ready ({PRESIGN_EXPIRES}s)")
    return url


# ---- generic job runner -----------------------------------------------------


@dataclass
class JobResult:
    stage: str
    action: str
    job_id: str = ""
    status: str = ""
    request_ids: list[str] = field(default_factory=list)
    credits_consumed: int | None = None
    input_url: str = ""
    output_files: list[dict] = field(default_factory=list)
    measures: list[dict] = field(default_factory=list)
    error: str = ""

    def to_log(self) -> dict:
        d = asdict(self)
        d["finished_at"] = _now_iso()
        return d


def run_job(
    stage: str,
    submit_action: str,
    describe_action: str,
    payload: dict,
    input_url: str,
    secret_id: str,
    secret_key: str,
    *,
    output_prefix: str,
    existing_job_id: str | None = None,
) -> JobResult:
    result = JobResult(stage=stage, action=submit_action, input_url=input_url)
    try:
        if existing_job_id:
            job_id = existing_job_id
            print(f"[{stage}] resuming poll on existing job_id={job_id} (no submit, no credit re-spend)")
        else:
            job_id, req_id = ai3d_client.submit_job(submit_action, payload, secret_id, secret_key)
            result.request_ids.append(req_id)
            print(f"[{stage}] submitted {submit_action} job_id={job_id}")
        result.job_id = job_id

        def _tick(jid: str, status: str, env: dict) -> None:
            credits = env.get("ResultCreditConsumed")
            if credits is not None and result.credits_consumed is None:
                result.credits_consumed = int(credits)
            print(f"[{stage}] poll {jid} status={status} credits={credits}")

        final = ai3d_client.poll_job(describe_action, job_id, secret_id, secret_key, on_tick=_tick)
        result.status = str(final.get("Status", "")).upper()
        result.request_ids.append(final.get("RequestId", ""))
        if final.get("ResultCreditConsumed") is not None:
            result.credits_consumed = int(final["ResultCreditConsumed"])
        print(f"[{stage}] final status={result.status} credits={result.credits_consumed}")

        if result.status != "DONE":
            result.error = f"terminal status {result.status}: {json.dumps(final, ensure_ascii=False)[:400]}"
            return result

        downloads = ai3d_client.download_result_files(final, CLOUD_RAW, name_prefix=output_prefix)
        for label, path in downloads:
            m = measure_glb(path)
            m["label"] = label
            result.output_files.append({"label": label, "path": str(path.relative_to(PROJECT)), "size_kb": m.get("size_kb")})
            result.measures.append(m)
            print(f"[{stage}] downloaded {label} → {path.name} | tris={m.get('triangles')} verts={m.get('vertices')} anims={m.get('animations')} skins={m.get('skins')}")
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    return result


# ---- subcommands ------------------------------------------------------------


def cmd_reduce_face(args: argparse.Namespace) -> int:
    secret_id, secret_key = load_secret()
    existing = getattr(args, "job_id", None)
    if existing:
        url = "(resume)"
        payload: dict[str, Any] = {}
    else:
        input_path = Path(args.input) if args.input else V05_INPUT_GLB
        if not input_path.exists():
            print(f"input not found: {input_path}", file=sys.stderr)
            return 2
        url = stage_input(input_path, secret_id, secret_key)
        payload = {
            "File3D": {"Type": "GLB", "Url": url},
            "FaceLevel": args.face_level,
            "PolygonType": args.polygon_type,
        }
    result = run_job(
        f"reduce-face-{args.face_level}",
        "SubmitReduceFaceJob",
        "DescribeReduceFaceJob",
        payload,
        url,
        secret_id,
        secret_key,
        output_prefix=f"reduceface_{args.face_level}_",
        existing_job_id=existing,
    )
    append_job_log(result.to_log())
    _report_budget(result, {"high": 32000, "medium": 16000, "low": 6000}.get(args.face_level))
    return 0 if not result.error else 1


def cmd_auto_rig(args: argparse.Namespace) -> int:
    secret_id, secret_key = load_secret()
    existing = getattr(args, "job_id", None)
    if existing:
        url = "(resume)"
        payload: dict[str, Any] = {}
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"input not found: {input_path}", file=sys.stderr)
            return 2
        url = stage_input(input_path, secret_id, secret_key)
        payload = {"File3D": {"Type": "GLB", "Url": url}}
        if args.motion is not None:
            payload["MotionType"] = int(args.motion)
    result = run_job(
        f"auto-rig-motion{args.motion}",
        "SubmitAutoRiggingJob",
        "DescribeAutoRiggingJob",
        payload,
        url,
        secret_id,
        secret_key,
        output_prefix=f"autorig_m{args.motion}_",
        existing_job_id=existing,
    )
    append_job_log(result.to_log())
    _report_budget(result, budget_bones=72)
    return 0 if not result.error else 1


def cmd_motion(args: argparse.Namespace) -> int:
    secret_id, secret_key = load_secret()
    payload: dict[str, Any] = {
        "Prompt": args.prompt,
        "EnableMesh": args.enable_mesh,
        "EnableRewrite": args.enable_rewrite,
        "EnableDurationEst": True,
    }
    result = run_job(
        f"motion-{args.tag}",
        "SubmitHunyuanTo3DMotionJob",
        "DescribeHunyuanTo3DMotionJob",
        payload,
        input_url="(text-only, no COS)",
        secret_id=secret_id,
        secret_key=secret_key,
        output_prefix=f"motion_{args.tag}_",
        existing_job_id=getattr(args, "job_id", None),
    )
    append_job_log(result.to_log())
    return 0 if not result.error else 1


def _report_budget(result: JobResult, tri_budget: int | None = None, budget_bones: int | None = None) -> None:
    if result.error:
        print(f"\n!! {result.stage} FAILED: {result.error}")
        return
    for m in result.measures:
        if tri_budget is not None and "triangles" in m:
            flag = "OK" if m["triangles"] <= tri_budget else f"OVER by {m['triangles']-tri_budget}"
            print(f"   budget: triangles {m['triangles']} vs ≤{tri_budget} → {flag}")
        if budget_bones is not None and "nodes" in m:
            print(f"   (note: GLB node count {m['nodes']} — bone count verified later in Blender)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    rf = sub.add_parser("reduce-face", help="SubmitReduceFaceJob (smart topology / retopo)")
    rf.add_argument("--face-level", required=True, choices=["high", "medium", "low"])
    rf.add_argument("--polygon-type", default="triangle", choices=["triangle", "quadrilateral"])
    rf.add_argument("--input", help="override input GLB (default: v05 normalized)")
    rf.add_argument("--job-id", help="resume polling an already-submitted job instead of submitting again")
    rf.set_defaults(func=cmd_reduce_face)

    ar = sub.add_parser("auto-rig", help="SubmitAutoRiggingJob (rig + skin + optional preset motion)")
    ar.add_argument("--input", required=True, help="input GLB (e.g. cloud_raw/reduceface_high_00.glb)")
    ar.add_argument("--motion", help="preset MotionType (23/24/25 walk, 26/27 idle, ...)")
    ar.add_argument("--job-id", help="resume polling an already-submitted job instead of submitting again")
    ar.set_defaults(func=cmd_auto_rig)

    mo = sub.add_parser("motion", help="SubmitHunyuanTo3DMotionJob (text→motion FBX, no upload)")
    mo.add_argument("--tag", required=True, help="short tag used in output filenames, e.g. greet")
    mo.add_argument("--prompt", required=True, help="motion description (≤128 chars)")
    mo.add_argument("--enable-mesh", action=argparse.BooleanOptionalAction, default=True,
                    help="include a skinned reference mesh in the FBX (default true)")
    mo.add_argument("--enable-rewrite", action=argparse.BooleanOptionalAction, default=False,
                    help="let the model expand the prompt (default false)")
    mo.add_argument("--job-id", help="resume polling an already-submitted job instead of submitting again")
    mo.set_defaults(func=cmd_motion)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
