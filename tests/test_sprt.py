"""Tests for the pentanomial SPRT.

The LLR is verified against two oracles that share no code with `sprt.py`,
satisfying the repo's independent-verification rule:

1. The degenerate binomial case (only LL/WW), where the GSPRT collapses to the
   closed-form Wald LLR — hand-derivable and exact.
2. A brute-force numerical maximizer of the constrained multinomial likelihood
   for a worked five-category vector.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sprt  # noqa: E402

PAIR_SCORES = (0.0, 0.25, 0.5, 0.75, 1.0)


def _score(elo):
    """Logistic expected score, computed independently of sprt."""
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


# --- Oracle 1: binomial-degenerate closed-form Wald ---


def test_llr_matches_the_binomial_wald_oracle():
    elo0, elo1 = 0.0, 5.0
    s0, s1 = _score(elo0), _score(elo1)
    losses, wins = 20, 30  # counts only in LL and WW
    wald = wins * math.log(s1 / s0) + losses * math.log((1.0 - s1) / (1.0 - s0))
    llr = sprt.log_likelihood_ratio([losses, 0, 0, 0, wins], elo0, elo1)
    assert llr == pytest.approx(wald, abs=1e-9)


# --- Oracle 2: brute-force constrained likelihood maximizer ---


def _max_constrained_loglik(counts, mean, seed=0):
    """Maximize sum n_i log q_i over the simplex with mean fixed to `mean`, by
    random search with shrinking refinement — an independent method (no Lagrange
    root-find, no shared code with sprt)."""
    rng = np.random.default_rng(seed)
    n = np.array(counts, dtype=float)
    best_loglik = -np.inf
    best_q = None
    span = 1.0
    for _ in range(5):
        if best_q is None:
            free = rng.random((400_000, 3))
        else:
            free = best_q[1:4] + (rng.random((400_000, 3)) - 0.5) * span
        q1, q2, q3 = free[:, 0], free[:, 1], free[:, 2]
        q4 = mean - (0.25 * q1 + 0.5 * q2 + 0.75 * q3)
        q0 = 1.0 - (q1 + q2 + q3) - q4
        q = np.stack([q0, q1, q2, q3, q4], axis=1)
        feasible = (q > 1e-9).all(axis=1)
        loglik = np.where(
            feasible, (n * np.log(np.where(q > 0, q, 1.0))).sum(axis=1), -np.inf
        )
        best = int(np.argmax(loglik))
        if loglik[best] > best_loglik:
            best_loglik = float(loglik[best])
            best_q = q[best]
        span *= 0.2
    return best_loglik


def test_llr_matches_the_brute_force_maximizer():
    counts = [5, 10, 40, 12, 8]
    elo0, elo1 = 0.0, 5.0
    brute_force = _max_constrained_loglik(
        counts, _score(elo1)
    ) - _max_constrained_loglik(counts, _score(elo0))
    llr = sprt.log_likelihood_ratio(counts, elo0, elo1)
    assert llr == pytest.approx(brute_force, abs=0.02)


# --- Verdict bounds ---


def test_classify_crosses_the_wald_bounds():
    lower, upper = sprt.sprt_bounds(0.05, 0.05)
    assert sprt.classify(upper + 0.01, 0.05, 0.05) == sprt.ACCEPT_H1
    assert sprt.classify(lower - 0.01, 0.05, 0.05) == sprt.ACCEPT_H0
    assert sprt.classify(0.0, 0.05, 0.05) is None


# --- Streaming ---


def test_run_sprt_accepts_h1_on_a_strong_candidate():
    stream = [4, 3, 4, 3, 4, 2, 4, 3, 1, 4] * 20
    result = sprt.run_sprt(stream, elo0=0.0, elo1=5.0)
    assert result["verdict"] == sprt.ACCEPT_H1
    assert result["llr"] > 0


def test_run_sprt_accepts_h0_on_a_weak_candidate():
    stream = [0, 1, 0, 1, 0, 2, 0, 1, 3, 0] * 20
    result = sprt.run_sprt(stream, elo0=0.0, elo1=5.0)
    assert result["verdict"] == sprt.ACCEPT_H0
    assert result["llr"] < 0


def test_run_sprt_inconclusive_on_exhaustion_reports_census():
    stream = [2, 3, 1, 2, 2, 3, 1, 2] * 2  # balanced, too short to cross a bound
    result = sprt.run_sprt(stream, elo0=0.0, elo1=5.0, max_pairs=16, population=16)
    assert result["verdict"] == sprt.INCONCLUSIVE
    assert result["pairs"] == 16
    # full exhaustion: the finite-population correction collapses the interval
    assert result["elo_high"] - result["elo_low"] < 1e-6


def test_run_sprt_drops_truncated_pairs():
    stream = [4, None, 4, None, 4]
    result = sprt.run_sprt(stream, elo0=0.0, elo1=5.0, max_pairs=10)
    assert result["pairs"] == 3  # the two None pairs were dropped


# --- Pair scoring ---


def test_score_pair_categories():
    assert sprt.score_pair("1-0", "0-1") == 4  # candidate wins both (WW)
    assert sprt.score_pair("0-1", "1-0") == 0  # candidate loses both (LL)
    assert sprt.score_pair("1/2-1/2", "1/2-1/2") == 2  # both drawn
    assert sprt.score_pair("1-0", "1-0") == 2  # win as White, loss as Black


# --- Cost gate ---


def test_cost_gate_passes_within_tolerance():
    assert sprt.cost_gate(960_000, 1_000_000, max_slowdown=0.05) is True


def test_cost_gate_fails_a_slow_candidate():
    assert sprt.cost_gate(800_000, 1_000_000, max_slowdown=0.05) is False


def test_cost_gate_passes_a_faster_candidate():
    assert sprt.cost_gate(1_200_000, 1_000_000) is True


# Local approx helper to avoid importing pytest just for approx in a plain assert.
def pytest_approx(value, rel=None, abs=None):

    return pytest.approx(value, rel=rel, abs=abs)
