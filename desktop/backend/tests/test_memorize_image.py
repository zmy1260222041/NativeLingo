"""Tests for the production photo-to-model pixel contract."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from backend.core import memorize_image


def _portrait_exif_source() -> bytes:
    image = Image.new("RGB", (2400, 1800), (30, 90, 160))
    exif = Image.Exif()
    exif[274] = 6  # stored landscape, displayed 90° clockwise as portrait
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95, exif=exif)
    return output.getvalue()


def test_canonicalize_upload_applies_exif_resize_and_fixed_jpeg_contract():
    raw = _portrait_exif_source()

    model_image, canonical_bytes = memorize_image.canonicalize_upload(raw)
    repeated_image, repeated_bytes = memorize_image.canonicalize_upload(raw)

    assert model_image.size == (1440, 1920)
    assert repeated_image.size == model_image.size
    assert repeated_bytes == canonical_bytes
    with Image.open(io.BytesIO(canonical_bytes)) as stored:
        assert stored.format == "JPEG"
        assert stored.size == model_image.size
        assert stored.getexif().get(274) is None
        assert stored.convert("RGB").tobytes() == model_image.tobytes()


@pytest.mark.parametrize("raw", [b"", b"not an image"])
def test_canonicalize_upload_rejects_unusable_bytes(raw):
    with pytest.raises(memorize_image.ImageUploadError):
        memorize_image.canonicalize_upload(raw)
