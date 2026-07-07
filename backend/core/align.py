"""Dynamic Time Warping alignment of two embedding sequences (Track B).

DTW finds the lowest-cost monotonic alignment between the reference and learner
frame sequences. It gives us two things at once:

* **Accuracy** — the per-frame cosine distance along the aligned path tells us
  *how different* the learner's pronunciation is from the reference, content-wise.
* **Fluency** — the *shape* of the warping path tells us about timing: a path
  that hugs the diagonal means similar rhythm; large horizontal/vertical runs
  mean the learner stretched, compressed, or paused relative to the reference.

Pure-numpy implementation with a Sakoe-Chiba band to keep it O(N * band) and to
forbid pathological alignments.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EPS = 1e-8


def cosine_distance_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance (1 - cosine similarity) between rows of a (N,D)
    and b (M,D). Cosine is used so loudness/voice magnitude differences don't
    dominate — only the *direction* (content) of each embedding matters."""
    a_n = a / (np.linalg.norm(a, axis=1, keepdims=True) + EPS)
    b_n = b / (np.linalg.norm(b, axis=1, keepdims=True) + EPS)
    sim = a_n @ b_n.T
    return (1.0 - sim).astype("float32")


@dataclass
class DTWResult:
    path: np.ndarray            # (K, 2) aligned (ref_idx, learner_idx) pairs
    path_costs: np.ndarray      # (K,) cosine distance at each aligned pair
    normalized_cost: float      # mean cost along the path -> accuracy basis
    cost_matrix: np.ndarray     # local cost matrix (N, M)


def dtw_align(
    ref: np.ndarray, learner: np.ndarray, band_frac: float = 0.2
) -> DTWResult:
    """Align ``learner`` to ``ref`` via banded DTW.

    ``band_frac`` is the Sakoe-Chiba radius as a fraction of the longer
    sequence; 0.2 lets the learner be up to ~20% faster/slower locally while
    blocking nonsensical warps.
    """
    n, m = ref.shape[0], learner.shape[0]
    if n == 0 or m == 0:
        return DTWResult(
            path=np.zeros((0, 2), dtype=int),
            path_costs=np.zeros((0,), dtype="float32"),
            normalized_cost=1.0,
            cost_matrix=np.zeros((n, m), dtype="float32"),
        )

    cost = cosine_distance_matrix(ref, learner)
    band = max(int(band_frac * max(n, m)), abs(n - m) + 1)

    INF = np.float32(1e9)
    acc = np.full((n + 1, m + 1), INF, dtype="float32")
    acc[0, 0] = 0.0

    for i in range(1, n + 1):
        # constrain j to the band around the diagonal
        j_center = int(round(i * m / n))
        j_lo = max(1, j_center - band)
        j_hi = min(m, j_center + band)
        for j in range(j_lo, j_hi + 1):
            d = cost[i - 1, j - 1]
            acc[i, j] = d + min(acc[i - 1, j], acc[i, j - 1], acc[i - 1, j - 1])

    # backtrack
    path = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        candidates = (acc[i - 1, j - 1], acc[i - 1, j], acc[i, j - 1])
        step = int(np.argmin(candidates))
        if step == 0:
            i, j = i - 1, j - 1
        elif step == 1:
            i -= 1
        else:
            j -= 1
    path.reverse()
    path_arr = np.array(path, dtype=int)
    path_costs = np.array(
        [cost[r, l] for r, l in path_arr], dtype="float32"
    )
    normalized_cost = float(path_costs.mean()) if path_costs.size else 1.0
    return DTWResult(
        path=path_arr,
        path_costs=path_costs,
        normalized_cost=normalized_cost,
        cost_matrix=cost,
    )
