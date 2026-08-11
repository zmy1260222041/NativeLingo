"""Extract and normalize reference/render silhouettes for reference-to-3d QA."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return mask
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == index, 255, 0).astype(np.uint8)


def reference_mask(image: np.ndarray) -> np.ndarray:
    border = np.concatenate((image[:12].reshape(-1, 3), image[-12:].reshape(-1, 3), image[:, :8].reshape(-1, 3), image[:, -8:].reshape(-1, 3)))
    background = np.median(border.astype(np.float32), axis=0)
    distance = np.linalg.norm(image.astype(np.float32) - background, axis=2)
    mask = np.where(distance > 28.0, 255, 0).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return largest_component(mask)


def render_mask(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    border = np.concatenate((gray[:4].ravel(), gray[-4:].ravel(), gray[:, :4].ravel(), gray[:, -4:].ravel()))
    background = float(np.median(border))
    mask = np.where(gray < background - 10.0, 255, 0).astype(np.uint8)
    return largest_component(mask)


def normalize(mask: np.ndarray, size: int = 1024, height: int = 900) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.zeros((size, size), dtype=np.uint8)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = mask[y0 : y1 + 1, x0 : x1 + 1]
    scale = height / crop.shape[0]
    width = max(1, int(round(crop.shape[1] * scale)))
    resized = cv2.resize(crop, (width, height), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((size, size), dtype=np.uint8)
    left = max(0, (size - width) // 2)
    bottom = 974
    top = bottom - height
    clipped_width = min(width, size - left)
    canvas[top:bottom, left : left + clipped_width] = resized[:, :clipped_width]
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--kind", required=True, choices=("reference", "render"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(args.image)
    raw = reference_mask(image) if args.kind == "reference" else render_mask(image)
    alpha = normalize(raw)
    output = np.zeros((alpha.shape[0], alpha.shape[1], 4), dtype=np.uint8)
    output[:, :, 3] = alpha
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, output)


if __name__ == "__main__":
    main()
