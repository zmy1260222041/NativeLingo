"""Empirically verify the CtcViterbi backpointer tie-break matches Python's
phoneme._viterbi_align, on tie-PRONE synthetic emissions (constant-ish logprobs
that force equal-score predecessor cells).

The audit flagged a possible tie-break divergence; this checks 2000 random
tie-prone cases. If 0 mismatches, the Kotlin port (strict `>`, candidates in
descending src order si, si-1, si-2) is equivalent to Python's tuple max().
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.core import phoneme as ph  # noqa: E402


def kotlin_align(em, seq_ids, blank=0):
    """The Kotlin CtcViterbi tie-break, re-implemented in Python (strict >)."""
    T = len(em)
    ext = [blank]
    for s in seq_ids:
        ext += [s, blank]
    S = len(ext)
    NEG = -1e30
    dp = np.full((T, S), NEG, np.float64)
    bp = np.full((T, S), -1, np.int16)
    dp[0, 0] = em[0, blank]
    if S > 1:
        dp[0, 1] = em[0, ext[1]]
        bp[0, 1] = 0
    for t in range(1, T):
        for s in range(S):
            best_val = dp[t - 1, s]
            best_src = s
            if s - 1 >= 0 and dp[t - 1, s - 1] > best_val:
                best_val = dp[t - 1, s - 1]
                best_src = s - 1
            if (s - 2 >= 0 and ext[s] != blank and ext[s] != ext[s - 2]
                    and dp[t - 1, s - 2] > best_val):
                best_val = dp[t - 1, s - 2]
                best_src = s - 2
            if best_val <= NEG:
                continue
            dp[t, s] = em[t, ext[s]] + best_val
            bp[t, s] = best_src
    last = S - 1 if dp[T - 1, S - 1] >= (dp[T - 1, S - 2] if S > 1 else NEG) else S - 2
    ranges = {}
    t, s = T - 1, last
    while t >= 0 and s >= 0:
        ranges.setdefault(s, []).append(t)
        s = bp[t, s]
        t -= 1
    return [(s, min(ts), max(ts)) for s, ts in sorted(ranges.items())]


def main():
    rng = np.random.default_rng(0)
    logpool = np.log(np.array([0.2, 0.2, 0.2, 0.3, 0.1]))  # repeats → ties
    mismatches = 0
    for trial in range(2000):
        T = int(rng.integers(8, 40))
        V = 6
        em = rng.choice(logpool, size=(T, V)).astype(np.float64)
        seq = list(map(int, rng.integers(1, V, size=int(rng.integers(2, 5)))))
        a = ph._viterbi_align(em, seq, 0)[1]
        b = kotlin_align(em, seq, 0)
        if a != b:
            mismatches += 1
            if mismatches <= 2:
                print(f"MISMATCH trial {trial} seq {seq}")
                print(f"  py: {a[:6]}")
                print(f"  kt: {b[:6]}")
    verdict = "BUG CONFIRMED" if mismatches else "tie-breaks equivalent (no divergence)"
    print(f"2000 tie-prone trials: {mismatches} mismatches -> {verdict}")


if __name__ == "__main__":
    main()
