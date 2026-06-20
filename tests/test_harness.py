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
import match_core  # noqa: E402
import selfplay  # noqa: E402
import sprt  # noqa: E402


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


def test_adjudicator_resigns_a_won_position():
    adjudicator = match_core.Adjudicator(resign_cp=900, resign_plies=3)
    assert adjudicator.update(10, 1000) is None
    assert adjudicator.update(11, 1000) is None
    assert adjudicator.update(12, 1000) == "1-0"


def test_adjudicator_resigns_for_black():
    adjudicator = match_core.Adjudicator(resign_cp=900, resign_plies=2)
    assert adjudicator.update(10, -1000) is None
    assert adjudicator.update(11, -1000) == "0-1"


def test_adjudicator_draws_a_dead_equal_position():
    adjudicator = match_core.Adjudicator(draw_cp=8, draw_after_ply=4, draw_plies=3)
    assert adjudicator.update(3, 0) is None  # before draw_after_ply: does not count
    assert adjudicator.update(4, 0) is None
    assert adjudicator.update(5, 0) is None
    assert adjudicator.update(6, 0) == "1/2-1/2"


def test_adjudicator_run_resets_on_a_swing():
    adjudicator = match_core.Adjudicator(resign_cp=900, resign_plies=3)
    adjudicator.update(10, 1000)
    adjudicator.update(11, 1000)
    assert adjudicator.update(12, 50) is None  # the swing back clears the run
    assert adjudicator.update(13, 1000) is None


def test_play_game_is_reproducible_after_ucinewgame():
    command = [sys.executable, str(REPO_ROOT / "src" / "main.py")]
    limit = match_core.make_limit(None, None, nodes=3000)
    with (
        chess.engine.SimpleEngine.popen_uci(command) as white,
        chess.engine.SimpleEngine.popen_uci(command) as black,
    ):
        first = match_core.play_game(
            white, black, chess.STARTING_FEN, limit, max_moves=12, game=("g", 1)
        )
        second = match_core.play_game(
            white, black, chess.STARTING_FEN, limit, max_moves=12, game=("g", 2)
        )
    assert first.moves, "the engines played at least one move"
    assert first.moves == second.moves  # ucinewgame clears the TT, so the game repeats


def test_load_openings_normalizes_fen_and_epd(tmp_path):
    book = tmp_path / "book.epd"
    book.write_text(
        "# a UHO-style book mixes full FENs and EPD lines with operations\n"
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1\n"
        'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - bm Nf6; id "x";\n'
    )
    openings = match_core.load_openings(str(book))
    assert len(openings) == 2
    for fen in openings:
        chess.Board(fen)  # every loaded opening is a valid FEN


def test_measure_nps_reports_a_positive_rate():
    engine = [sys.executable, str(REPO_ROOT / "src" / "main.py")]
    nps = sprt.measure_nps(engine, sprt.COST_BENCH_FEN, node_limit=2000, repeats=3)
    assert nps > 0


def test_sprt_runs_a_two_pair_node_limited_mini_match():
    engine = [sys.executable, str(REPO_ROOT / "src" / "main.py")]
    limit = match_core.make_limit(None, None, nodes=2000)
    openings = [chess.STARTING_FEN, chess.STARTING_FEN]
    pairs = sprt._engine_pairs(
        engine,
        engine,
        openings,
        limit,
        max_moves=16,
        adjudicator_factory=match_core.Adjudicator,
    )
    result = sprt.run_sprt(
        pairs, elo0=0.0, elo1=5.0, alpha=0.05, beta=0.05, max_pairs=2, population=2
    )
    assert result["pairs"] <= 2
    assert len(result["counts"]) == 5
    assert result["verdict"] in {sprt.ACCEPT_H1, sprt.ACCEPT_H0, sprt.INCONCLUSIVE}
