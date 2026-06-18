"""Fast self-test for the strength harness: exercise both runners on tiny inputs
so the gate guards the tools without running a full suite or match."""

import io
import sys
from pathlib import Path

import chess
import chess.engine

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import epd_suite  # noqa: E402
import selfplay  # noqa: E402


class PlayedMove:
    def __init__(self, uci):
        self.move = chess.Move.from_uci(uci)


class ScriptedEngine:
    def __init__(self, moves):
        self.moves = iter(moves)

    def play(self, _board, _limit):
        return PlayedMove(next(self.moves))


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


def test_selfplay_reports_game_progress():
    engine = [sys.executable, str(REPO_ROOT / "src" / "main.py")]
    progress = io.StringIO()
    wins, losses, draws = selfplay.run_match(
        engine,
        engine,
        [chess.STARTING_FEN],
        games=1,
        limit=chess.engine.Limit(depth=1),
        max_moves=20,
        progress=progress,
        progress_mode="game",
    )

    lines = progress.getvalue().splitlines()
    assert lines[0] == "game 1/1 start: opening=1 engine1=white"
    assert lines[1] == f"game 1/1 result: 1/2-1/2 score +{wins} -{losses} ={draws}"


def test_selfplay_reports_move_progress_before_and_after_engine_calls():
    progress = io.StringIO()

    selfplay.play_game(
        ScriptedEngine(["e2e4"]),
        ScriptedEngine(["e7e5"]),
        chess.STARTING_FEN,
        chess.engine.Limit(depth=1),
        max_moves=2,
        progress=progress,
        progress_mode="move",
        game_label="game 3",
    )

    lines = progress.getvalue().splitlines()
    assert lines[0] == "game 3 ply 1 white thinking..."
    assert lines[1].startswith("game 3 ply 1 white played e2e4 in ")
    assert lines[2] == "game 3 ply 2 black thinking..."
    assert lines[3].startswith("game 3 ply 2 black played e7e5 in ")
