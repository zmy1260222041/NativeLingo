"""Thin client over the Tencent ai3d async job API.

Most ai3d actions are async: a ``Submit*`` call returns a ``JobId`` (valid 24h),
a ``Describe*``/``Query*`` call polls ``Status`` (``RUN`` → ``DONE``), and a
``DONE`` response carries presigned COS URLs (24h) for the result files. This
module wraps that loop and downloads the COS links to disk.

It does NOT upload inputs — every 3D-model-input job (``SubmitReduceFaceJob``,
``SubmitAutoRiggingJob``, ``SubmitHunyuanTo3DUVJob``, ``SubmitHunyuan3DPartJob``)
takes a ``File3D.Url`` that must already be a readable COS URL. Producing that
URL (upload to a bucket the caller owns) is a separate concern handled by the
caller; see ``run_pipeline.py``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterator

import requests

from . import tencent_sign

ENDPOINT = f"https://{tencent_sign.HOST}"
DEFAULT_TIMEOUT = 30  # seconds for each HTTP call
DEFAULT_POLL_INTERVAL = 8.0  # seconds between Describe polls
DEFAULT_POLL_MAX = 60 * 25  # ~25 min ceiling per job

# Statuses that mean "still working, keep polling". Anything else (DONE/FAIL/...)
# is treated as terminal. WAIT = queued for a worker slot (ReduceFace/AutoRigging
# default to 1 concurrent slot, so jobs often sit in WAIT before RUN).
IN_PROGRESS_STATUSES = {"RUN", "WAIT", "PENDING", "QUEUED", "PROCESSING", "SUBMITTED", ""}


class Ai3dError(RuntimeError):
    """Raised when the service returns ``Response.Error`` or transport fails."""

    def __init__(self, code: str, message: str, request_id: str = "", raw: Any = None):
        super().__init__(f"[{code}] {message} (RequestId={request_id})")
        self.code = code
        self.message = message
        self.request_id = request_id
        self.raw = raw


def call(
    action: str,
    payload: dict,
    secret_id: str,
    secret_key: str,
    *,
    region: str = tencent_sign.REGION,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Sign and POST one ai3d request; return the parsed ``Response`` dict.

    Raises :class:`Ai3dError` when the body carries ``Response.Error`` and on
    transport failures. A successful return still needs the caller to inspect
    job-specific fields (``JobId``, ``Status``, result URLs).
    """
    headers, payload_str = tencent_sign.build_signed_headers(
        secret_id, secret_key, action, payload, region=region
    )
    resp = requests.post(ENDPOINT, headers=headers, data=payload_str.encode("utf-8"), timeout=timeout)
    try:
        body = resp.json()
    except ValueError as exc:
        raise Ai3dError("TransportError", f"non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}", raw=resp.text) from exc

    envelope = body.get("Response", {}) if isinstance(body, dict) else {}
    if "Error" in envelope:
        err = envelope["Error"]
        raise Ai3dError(
            err.get("Code", "UnknownError"),
            err.get("Message", ""),
            envelope.get("RequestId", ""),
            raw=envelope,
        )
    return envelope


def submit_job(
    submit_action: str,
    payload: dict,
    secret_id: str,
    secret_key: str,
    *,
    region: str = tencent_sign.REGION,
) -> tuple[str, str]:
    """Submit an async job; return ``(job_id, request_id)``."""
    envelope = call(submit_action, payload, secret_id, secret_key, region=region)
    job_id = envelope.get("JobId")
    if not job_id:
        raise Ai3dError("MissingJobId", f"submit returned no JobId: {envelope}", envelope.get("RequestId", ""), raw=envelope)
    return job_id, envelope.get("RequestId", "")


def poll_job(
    describe_action: str,
    job_id: str,
    secret_id: str,
    secret_key: str,
    *,
    region: str = tencent_sign.REGION,
    interval: float = DEFAULT_POLL_INTERVAL,
    max_seconds: float = DEFAULT_POLL_MAX,
    on_tick=None,
) -> dict:
    """Poll until ``Status`` leaves ``RUN``; return the final ``Response``.

    A non-RUN terminal status that is not ``DONE`` (e.g. ``FAIL``) is returned
    to the caller for inspection rather than raised — the result body often
    carries a failure reason worth surfacing.
    """
    deadline = time.monotonic() + max_seconds
    last: dict = {}
    while True:
        last = call(describe_action, {"JobId": job_id}, secret_id, secret_key, region=region)
        status = str(last.get("Status", "")).upper()
        if on_tick:
            on_tick(job_id, status, last)
        if status not in IN_PROGRESS_STATUSES:
            return last
        if time.monotonic() >= deadline:
            raise Ai3dError(
                "PollTimeout",
                f"{describe_action} {job_id} still {status or 'RUN'} after {max_seconds:.0f}s",
                last.get("RequestId", ""),
                raw=last,
            )
        time.sleep(interval)


def iter_result_urls(response: dict) -> Iterator[tuple[str, str]]:
    """Yield ``(label, url)`` pairs from a completed job response.

    Handles the common shapes: ``ResultFile3Ds[].{Url, Type}``,
    ``ResultFile3DList``, ``ResultFiles``, and a bare ``ResultUrl``. ``label``
    is the file ``Type`` (e.g. ``GLB``/``FBX``) or ``result``; dedupe is the
    caller's job.
    """
    seen: set[str] = set()

    def _emit(label: str, url: str):
        if url and url not in seen:
            seen.add(url)
            yield (label, url)

    lists = response.get("ResultFile3Ds") or response.get("ResultFile3DList") or response.get("ResultFiles") or []
    if isinstance(lists, list):
        for item in lists:
            if isinstance(item, dict):
                url = item.get("Url") or item.get("DownloadUrl") or ""
                if url:
                    yield from _emit(item.get("Type") or item.get("Format") or "result", url)
    single = response.get("ResultUrl") or response.get("ResultFileUrl")
    if single:
        yield from _emit(response.get("ResultType") or "result", single)


def download_result_files(
    response: dict,
    dest_dir: Path,
    *,
    name_prefix: str = "",
    timeout: float = 120,
) -> list[tuple[str, Path]]:
    """Download every result URL in ``response`` into ``dest_dir``.

    Returns ``[(label, path), ...]``. Filenames are ``{prefix}{index}.{ext}``
    where ``ext`` is derived from the ``Type`` label (``GLB``→``.glb``).
    Presigned COS URLs are public for their validity window, so no auth header
    is attached.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str, Path]] = []
    for index, (label, url) in enumerate(iter_result_urls(response)):
        ext = _ext_for_label(label)
        path = dest_dir / f"{name_prefix}{index:02d}{ext}"
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with path.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        handle.write(chunk)
        out.append((label, path))
    return out


def _ext_for_label(label: str) -> str:
    label = (label or "").lower()
    table = {"glb": ".glb", "gltf": ".gltf", "fbx": ".fbx", "obj": ".obj", "usdz": ".usdz"}
    for key, ext in table.items():
        if key in label:
            return ext
    return ".bin"
