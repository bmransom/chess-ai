"""Fast self-test for the strength harness: exercise both runners on tiny inputs
so the gate guards the tools without running a full suite or match."""

import sys
from pathlib import Path

import chess
import chess.engine

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import epd_suite  # noqa: E402
import selfplay  # noqa: E402

MINI_EPD = [
    '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - bm Ra8; id "mini.1";',
    '3q3k/8/8/8/8/8/8/3Q3K w - - bm Qxd8; id "mini.2";',
]


def test_epd_runner_solves_easy_tactics():
    solved, total, failures = epd_suite.run(MINI_EPD, depth=4)
    assert total == 2
    assert solved == 2, failures


def test_elo_estimate_even_match_is_zero():
    elo, _margin = selfplay.elo_estimate(10, 10, 0)
    assert abs(elo) < 1e-6


def test_elo_estimate_favors_the_winner():
    elo, margin = selfplay.elo_estimate(75, 25, 0)
    assert 180 < elo < 200
    assert margin > 0


def test_selfplay_reports_a_single_game_result():
    engine = [sys.executable, str(REPO_ROOT / "src" / "main.py")]
    wins, losses, draws = selfplay.run_match(
        engine,
        engine,
        [chess.STARTING_FEN],
        games=1,
        limit=chess.engine.Limit(depth=1),
        max_moves=20,
    )
    assert wins + losses + draws == 1
