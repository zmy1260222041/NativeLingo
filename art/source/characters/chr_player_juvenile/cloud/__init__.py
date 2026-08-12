"""Tencent ai3d cloud pipeline for the chr_player_juvenile player asset.

Self-contained, no dependency on the external blender-copilot addon. Signs requests
with TC3-HMAC-SHA256 against the mainland ``ai3d`` service
(``ai3d.tencentcloudapi.com``, version ``2025-05-13``).

Credentials are read from outside the repo (see :mod:`secret`) and are never
written into the tree, blend files, reports or logs.
"""

__all__ = ["secret", "tencent_sign", "ai3d_client"]
