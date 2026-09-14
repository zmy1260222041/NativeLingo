"""Extract the authored magenta matte; retain source PNGs unchanged.

Run only after explicit approval for local image processing. Requires Pillow,
NumPy and SciPy (available in the repository .venv). Output is straight-alpha
RGBA with foreground colors reconstructed at antialiased boundaries.
"""
from pathlib import Path
import json

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
DEST = ROOT / "game/assets/novel/campus"
REPORT = ROOT / "docs/reviews/campus_art_2026-09-12/alpha-audit.json"


def extract(source: Path, destination: Path) -> dict:
    rgb = np.asarray(Image.open(source).convert("RGB"), dtype=np.float32) / 255.0
    # None of the authored costumes contains magenta. Fine ink lines remain
    # foreground; this also finds enclosed gaps around hands and loose curls.
    chroma = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
    opaque = chroma < 0.055
    _, nearest = distance_transform_edt(~opaque, return_indices=True)
    foreground = rgb[nearest[0], nearest[1]]
    key = np.array([1.0, 0.0, 1.0], dtype=np.float32)
    direction = foreground - key
    denominator = np.maximum(np.sum(direction * direction, axis=2), 1e-6)
    alpha = np.clip(np.sum((rgb - key) * direction, axis=2) / denominator, 0, 1)
    alpha[opaque] = 1
    # Generated mattes contain slight compression/paint variation (corners are
    # around 240,13,238 rather than exact 255,0,255).
    alpha[chroma > 0.85] = 0
    alpha[alpha < 0.02] = 0
    safe_alpha = np.maximum(alpha, 0.02)[..., None]
    unmixed = np.clip((rgb - (1 - alpha[..., None]) * key) / safe_alpha, 0, 1)
    spill = (np.minimum(unmixed[..., 0], unmixed[..., 2]) - unmixed[..., 1] > 0.055) & ~opaque
    unmixed[spill] = foreground[spill]
    unmixed[alpha == 0] = 0
    rgba = np.dstack((unmixed, alpha))
    result = Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.save(destination)
    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((result.width // 2, result.height // 2))[3] > 230
    return {
        "source": str(source.relative_to(ROOT)),
        "output": str(destination.relative_to(ROOT)),
        "size": list(result.size),
        "mode": result.mode,
        "transparent_pixels": int(np.sum(alpha == 0)),
        "opaque_pixels": int(np.sum(alpha == 1)),
        "edge_pixels": int(np.sum((alpha > 0) & (alpha < 1))),
        "visible_magenta_pixels": int(np.sum((alpha > 0.5) & (np.minimum(unmixed[..., 0], unmixed[..., 2]) - unmixed[..., 1] > 0.12))),
    }


if __name__ == "__main__":
    records = [extract(path, DEST / (path.stem.removesuffix("-matte") + ".png")) for path in sorted(SOURCE.glob("*-matte.png"))]
    assert len(records) == 8, "All eight original character mattes must be present"
    REPORT.write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))
