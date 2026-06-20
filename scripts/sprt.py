"""Pentanomial SPRT for the fair-match harness.

Engine-free: takes the five-count vector of color-swapped game-pair outcomes and
returns the running log-likelihood ratio (LLR) and a verdict. The LLR is the
generalized SPRT — a constrained multinomial maximum-likelihood estimate, the
Fishtest `LLRcalc` method — not a trinomial game count, which would assume a
pair's two games are independent (the i.i.d. error this harness exists to fix).

The five categories index pair outcomes by their normalized score:

    index  0    1        2            3       4
    pair   LL   LD+DL    LW+DD+WL     DW+WD   WW
    score  0.0  0.25     0.5          0.75    1.0   (= average game score)
"""

import logging
import math
import random
import shlex
import sys
import time

import chess.engine

import match_core

# Normalized pair scores: the average of the pair's two game scores.
PAIR_SCORES = (0.0, 0.25, 0.5, 0.75, 1.0)

ACCEPT_H1 = "accept-H1"
ACCEPT_H0 = "accept-H0"
INCONCLUSIVE = "inconclusive"

# Pseudo-count added to the extreme categories only when the observed outcomes
# cannot reach a hypothesis mean (a degenerate early state); negligible once real
# counts accumulate, and never triggered once both extremes are observed.
_REGULARIZATION = 1e-7


def elo_to_score(elo):
    """Logistic expected score for an Elo difference."""
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def score_to_elo(score):
    """Logistic Elo for an expected score, clamped away from 0 and 1."""
    score = min(max(score, 1e-6), 1.0 - 1e-6)
    return -400.0 * math.log10(1.0 / score - 1.0)


def sprt_bounds(alpha, beta):
    """Wald's acceptance bounds (lower, upper) for the LLR."""
    return math.log(beta / (1.0 - alpha)), math.log((1.0 - beta) / alpha)


def _solve_lambda(probabilities, mean):
    """The Lagrange scalar for the mean-constrained MLE: the root of
    g(L) = sum p_i (x_i - mean) / (1 + L (x_i - mean)), which is strictly
    decreasing, found by bisection within the interval that keeps every
    1 + L (x_i - mean) positive."""
    lower, upper = -math.inf, math.inf
    for probability, score in zip(probabilities, PAIR_SCORES):
        if probability <= 0.0:
            continue
        delta = score - mean
        if delta > 0.0:
            lower = max(lower, -1.0 / delta)
        elif delta < 0.0:
            upper = min(upper, -1.0 / delta)
    if lower == -math.inf and upper == math.inf:
        return 0.0  # every observed outcome sits exactly at the mean

    def g(lam):
        return sum(
            probability * (score - mean) / (1.0 + lam * (score - mean))
            for probability, score in zip(probabilities, PAIR_SCORES)
            if probability > 0.0
        )

    low = lower + 1e-12 if lower > -math.inf else -1e12
    high = upper - 1e-12 if upper < math.inf else 1e12
    for _ in range(200):
        mid = 0.5 * (low + high)
        if g(mid) > 0.0:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def _constrained_loglik(counts, probabilities, mean):
    """The maximized log-likelihood of the observed counts under the constraint
    that the distribution's mean equals `mean`."""
    lam = _solve_lambda(probabilities, mean)
    loglik = 0.0
    for count, score, probability in zip(counts, PAIR_SCORES, probabilities):
        if count > 0:
            loglik += count * math.log(probability / (1.0 + lam * (score - mean)))
    return loglik


def log_likelihood_ratio(counts, elo0, elo1):
    """The GSPRT log-likelihood ratio of H1 (Elo = elo1) over H0 (Elo = elo0).

    When both hypothesis means sit strictly inside the observed support the
    estimate is exact (the binomial case collapses to the closed-form Wald LLR).
    When an outcome is so one-sided that a mean is unreachable, the two extremes
    are regularized identically for both endpoints — symmetric, so the LLR stays
    finite and correctly signed, never the asymmetric blow-up of a one-sided fix.
    """
    if sum(counts) == 0:
        return 0.0
    mean0 = elo_to_score(elo0)
    mean1 = elo_to_score(elo1)
    support = [score for count, score in zip(counts, PAIR_SCORES) if count > 0]
    lo, hi = min(support), max(support)
    weights = [float(count) for count in counts]
    if not (lo < mean0 < hi and lo < mean1 < hi):
        weights[0] += _REGULARIZATION
        weights[4] += _REGULARIZATION
    total = sum(weights)
    probabilities = [weight / total for weight in weights]
    return _constrained_loglik(counts, probabilities, mean1) - _constrained_loglik(
        counts, probabilities, mean0
    )


def classify(llr, alpha, beta):
    """The verdict for an LLR, or None while the test is still open."""
    lower, upper = sprt_bounds(alpha, beta)
    if llr >= upper:
        return ACCEPT_H1
    if llr <= lower:
        return ACCEPT_H0
    return None


def score_pair(candidate_white_result, candidate_black_result):
    """The pentanomial category (0..4) of one color-swapped pair, from the
    candidate's view, given the candidate-White and candidate-Black game results
    ("1-0" / "0-1" / "1/2-1/2")."""
    points = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}
    white_points = points[candidate_white_result]
    black_points = 1.0 - points[candidate_black_result]
    return round((white_points + black_points) * 2)


def census_estimate(counts, population=None):
    """The point-estimate Elo and a finite-population 95% confidence interval from
    the observed pairs. On full exhaustion (pairs == population) the correction
    collapses the interval: deterministic play has measured the whole book."""
    pairs = sum(counts)
    if pairs == 0:
        return 0.0, 0.0, 0.0
    mean = sum(count * score for count, score in zip(counts, PAIR_SCORES)) / pairs
    variance = (
        sum(count * (score - mean) ** 2 for count, score in zip(counts, PAIR_SCORES))
        / pairs
    )
    correction = 1.0
    if population and population > 1:
        correction = max(0.0, (population - pairs) / (population - 1))
    standard_error = math.sqrt(variance * correction / pairs)
    margin = 1.96 * standard_error
    return (
        score_to_elo(mean),
        score_to_elo(mean - margin),
        score_to_elo(mean + margin),
    )


# --- Cost gate ---
#
# Fixed-node SPRT gives both engines the same node budget, so it is blind to a
# term's per-node cost: a +4-Elo term that runs 20% slower is net-negative at a
# real time control. An accept-H1 verdict is therefore necessary but not
# sufficient -- the keep/drop rule is accept-H1 AND a passing node-rate check.

COST_BENCH_FEN = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 1"


def cost_gate(candidate_nps, baseline_nps, max_slowdown=0.05):
    """True if the candidate's node rate stays within `max_slowdown` of the
    baseline's — the second half of the keep/drop rule."""
    if baseline_nps <= 0:
        return True
    return candidate_nps >= baseline_nps * (1.0 - max_slowdown)


def measure_nps(engine_command, fen, node_limit, repeats=10):
    """Search `fen` at a fixed node budget `repeats` times and return the engine's
    node rate (nodes per second)."""
    limit = match_core.make_limit(None, None, nodes=node_limit)
    board = chess.Board(fen)
    total_nodes = 0
    elapsed = 0.0
    with chess.engine.SimpleEngine.popen_uci(engine_command) as engine:
        for index in range(repeats):
            started = time.monotonic()
            info = engine.analyse(board, limit, game=index)
            elapsed += time.monotonic() - started
            total_nodes += info.get("nodes", 0)
    return total_nodes / elapsed if elapsed > 0.0 else 0.0


class Sprt:
    """Accumulates pentanomial counts and reports the running LLR and verdict."""

    def __init__(self, elo0=0.0, elo1=5.0, alpha=0.05, beta=0.05):
        self.elo0 = elo0
        self.elo1 = elo1
        self.alpha = alpha
        self.beta = beta
        self.counts = [0, 0, 0, 0, 0]

    def record(self, category):
        """Add one pair outcome; return the current verdict, or None if open."""
        self.counts[category] += 1
        return classify(self.llr(), self.alpha, self.beta)

    def llr(self):
        return log_likelihood_ratio(self.counts, self.elo0, self.elo1)

    @property
    def pairs(self):
        return sum(self.counts)


def run_sprt(
    pairs,
    elo0=0.0,
    elo1=5.0,
    alpha=0.05,
    beta=0.05,
    max_pairs=None,
    population=None,
    progress=None,
    progress_every=0,
):
    """Stream `pairs` (each a pentanomial category 0..4, or None for a truncated
    pair to drop) into the SPRT. Stop at a verdict, or report `inconclusive` with
    the census estimate when the pairs run out or `max_pairs` is reached. With
    `progress_every`, emit a running snapshot to `progress` every N pairs."""
    test = Sprt(elo0, elo1, alpha, beta)
    verdict = None
    for category in pairs:
        if category is None:
            continue  # a truncated pair adds no likelihood
        verdict = test.record(category)
        if progress_every and progress is not None and test.pairs % progress_every == 0:
            elo, low, high = census_estimate(test.counts, population)
            print(
                f"progress pairs={test.pairs} llr={test.llr():+.3f} "
                f"counts={test.counts} elo={elo:+.1f} ci=[{low:+.1f},{high:+.1f}]",
                file=progress,
                flush=True,
            )
        if verdict is not None:
            break
        if max_pairs is not None and test.pairs >= max_pairs:
            break
    if verdict is None:
        verdict = INCONCLUSIVE
    elo, elo_low, elo_high = census_estimate(test.counts, population)
    return {
        "verdict": verdict,
        "llr": test.llr(),
        "pairs": test.pairs,
        "counts": list(test.counts),
        "elo": elo,
        "elo_low": elo_low,
        "elo_high": elo_high,
    }


def _engine_pairs(candidate, baseline, openings, limit, max_moves, adjudicator_factory):
    """Yield the pentanomial category of each color-swapped pair, dropping a pair
    if either of its games truncates."""
    with (
        chess.engine.SimpleEngine.popen_uci(candidate) as engine1,
        chess.engine.SimpleEngine.popen_uci(baseline) as engine2,
    ):
        for pair_index, opening in enumerate(openings):
            white_game, black_game = match_core.play_pair(
                engine1,
                engine2,
                opening,
                limit,
                max_moves,
                pair_index=pair_index,
                adjudicator_factory=adjudicator_factory,
            )
            if not white_game.moves or not black_game.moves:
                yield None
                continue
            yield score_pair(white_game.result, black_game.result)


def main():
    import argparse

    default_engine = f"{sys.executable} src/main.py"
    parser = argparse.ArgumentParser(
        description="Run a pentanomial SPRT and report the verdict."
    )
    parser.add_argument(
        "--engine1", default=default_engine, help="candidate UCI command"
    )
    parser.add_argument(
        "--engine2", default=default_engine, help="baseline UCI command"
    )
    parser.add_argument(
        "--nodes", type=int, default=200_000, help="fixed node budget per move"
    )
    parser.add_argument("--elo0", type=float, default=0.0, help="H0 Elo bound")
    parser.add_argument("--elo1", type=float, default=5.0, help="H1 Elo bound")
    parser.add_argument("--alpha", type=float, default=0.05, help="type-I error rate")
    parser.add_argument("--beta", type=float, default=0.05, help="type-II error rate")
    parser.add_argument("--max-pairs", type=int, default=None, help="unique-pair cap")
    parser.add_argument("--max-moves", type=int, default=200, help="move-cap fallback")
    parser.add_argument(
        "--openings",
        default="bench/uho_4060_v4.epd",
        help="UHO opening book (run scripts/fetch_uho.py to provision it)",
    )
    parser.add_argument("--seed", type=int, default=0, help="opening-shuffle seed")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="print a running LLR/census snapshot to stderr every N pairs",
    )
    parser.add_argument(
        "--cost-check",
        action="store_true",
        help="also measure node rate and report the keep/drop decision",
    )
    parser.add_argument(
        "--max-slowdown",
        type=float,
        default=0.05,
        help="max node-rate slowdown the candidate may cost",
    )
    args = parser.parse_args()

    # Quiet python-chess's per-command engine logging so long runs stay readable.
    logging.getLogger("chess.engine").setLevel(logging.WARNING)

    openings = match_core.load_openings(args.openings)
    random.Random(args.seed).shuffle(openings)
    # The full book is the population for the finite-population correction; the
    # pair source is lazy, so run_sprt's max_pairs caps the run without truncating
    # the book (truncating it would collapse the census CI at exhaustion).
    population = len(openings)
    limit = match_core.make_limit(None, None, nodes=args.nodes)

    pairs = _engine_pairs(
        shlex.split(args.engine1),
        shlex.split(args.engine2),
        openings,
        limit,
        args.max_moves,
        match_core.Adjudicator,
    )
    result = run_sprt(
        pairs,
        elo0=args.elo0,
        elo1=args.elo1,
        alpha=args.alpha,
        beta=args.beta,
        max_pairs=args.max_pairs,
        population=population,
        progress=sys.stderr,
        progress_every=args.progress_every,
    )
    print(
        f"SPRT [{args.elo0:.0f}, {args.elo1:.0f}] a={args.alpha} b={args.beta}: "
        f"{result['verdict']} after {result['pairs']} pairs; "
        f"LLR {result['llr']:+.2f}; counts {result['counts']}; "
        f"Elo {result['elo']:+.1f} [{result['elo_low']:+.1f}, {result['elo_high']:+.1f}]"
    )

    if args.cost_check:
        candidate_nps = measure_nps(
            shlex.split(args.engine1), COST_BENCH_FEN, args.nodes
        )
        baseline_nps = measure_nps(
            shlex.split(args.engine2), COST_BENCH_FEN, args.nodes
        )
        passed = cost_gate(candidate_nps, baseline_nps, args.max_slowdown)
        keep = result["verdict"] == ACCEPT_H1 and passed
        print(
            f"cost: candidate {candidate_nps:,.0f} nps vs baseline {baseline_nps:,.0f} nps "
            f"-> {'pass' if passed else 'fail'}"
        )
        print(f"keep: {keep} (accept-H1 and a passing cost gate)")


if __name__ == "__main__":
    main()
