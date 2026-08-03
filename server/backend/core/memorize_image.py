"""Canonical photo preprocessing for Memorizing recognition.

This module is the single source of truth for pixels presented to YOLOE.
Production uploads, automated tests and offline recognition benchmarks must
all call :func:`canonicalize_upload`; reimplementing the resize/encode path in
Canvas, Pillow or OpenCV makes threshold-sensitive results incomparable.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 50_000_000
MAX_SOURCE_PIXELS = 80_000_000
MAX_DIMENSION = 1920
JPEG_QUALITY = 90
JPEG_SUBSAMPLING = 2
CONTRACT_VERSION = "memorize-image-v1"


class ImageUploadError(ValueError):
    """The uploaded bytes cannot be converted into a safe model image."""


def canonicalize_upload(raw: bytes) -> tuple[Image.Image, bytes]:
    """Return the exact RGB model image and its canonical JPEG bytes.

    The intentionally explicit encode settings lock the production contract:
    EXIF orientation is applied, the long edge is capped at 1920 with LANCZOS,
    and the resized image is encoded as quality-90 4:2:0 JPEG.  The model image
    is decoded back from those bytes, so stored/click-crop pixels and detection
    pixels are identical.
    """
    if not raw:
        raise ImageUploadError("empty image upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageUploadError("image too large (>50MB)")

    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise ImageUploadError("image dimensions are too large")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except ImageUploadError:
        raise
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ImageUploadError(f"could not decode image: {exc}") from exc

    scale = min(1.0, MAX_DIMENSION / max(image.size))
    if scale < 1.0:
        size = (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        )
        image = image.resize(size, Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=JPEG_QUALITY,
        subsampling=JPEG_SUBSAMPLING,
        optimize=False,
        progressive=False,
    )
    canonical_bytes = output.getvalue()
    with Image.open(io.BytesIO(canonical_bytes)) as canonical:
        model_image = canonical.convert("RGB")
    return model_image, canonical_bytes
