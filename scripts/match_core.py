"""Shared self-play engine for the fair-match harness.

UCI driving, opening-book loading, color-swapped pair play, `ucinewgame` before
every game, and eval-based win/draw adjudication. The fixed-N Elo reporter
(`selfplay.py`) and the pentanomial SPRT (`sprt.py`) both build on this. The
referee is python-chess, which shares no code with the engine under test.
"""

import time
from collections import namedtuple

import chess
import chess.engine

# A played game: the result string and the UCI moves played from the opening.
GameResult = namedtuple("GameResult", ["result", "moves"])

# A mate is mapped to this magnitude so a forced mate triggers resign adjudication.
MATE_CP = 100_000


class Adjudicator:
    """Eval-based win/draw adjudication, fed the White-relative score (centipawns)
    after each ply. Returns a result once a threshold holds for its span, else
    None. Defaults follow cutechess-cli's `-resign` / `-draw` conventions and
    replace a fixed move cap, which scores winning positions as draws and so
    deflates the decisive rate that an unbalanced book exists to raise."""

    def __init__(
        self,
        resign_cp=900,
        resign_plies=6,
        draw_cp=8,
        draw_after_ply=80,
        draw_plies=10,
    ):
        self.resign_cp = resign_cp
        self.resign_plies = resign_plies
        self.draw_cp = draw_cp
        self.draw_after_ply = draw_after_ply
        self.draw_plies = draw_plies
        self._white_run = 0
        self._black_run = 0
        self._draw_run = 0

    def update(self, ply, white_cp):
        """Record one ply's White-relative score; return a result string to end
        the game, or None to keep playing."""
        self._white_run = self._white_run + 1 if white_cp >= self.resign_cp else 0
        self._black_run = self._black_run + 1 if white_cp <= -self.resign_cp else 0
        near_draw = abs(white_cp) <= self.draw_cp and ply >= self.draw_after_ply
        self._draw_run = self._draw_run + 1 if near_draw else 0

        if self._white_run >= self.resign_plies:
            return "1-0"
        if self._black_run >= self.resign_plies:
            return "0-1"
        if self._draw_run >= self.draw_plies:
            return "1/2-1/2"
        return None


def white_relative_cp(score):
    """Centipawns from White's view, a mate mapped to +/-MATE_CP."""
    return score.white().score(mate_score=MATE_CP)


def write_progress(progress, message):
    if progress is not None:
        print(message, file=progress, flush=True)


def color_name(color):
    return "white" if color == chess.WHITE else "black"


def play_game(
    white,
    black,
    opening_fen,
    limit,
    max_moves,
    *,
    game=None,
    adjudicator=None,
    progress=None,
    progress_mode="none",
    game_label="game",
):
    """Play one game and return its GameResult. `game`, when set, is forwarded to
    python-chess so it sends `ucinewgame` (clearing the engine's transposition
    table) at the game's start. With an `adjudicator`, the engines' reported
    scores end the game on a decisive or dead-drawn evaluation."""
    board = chess.Board(opening_fen)
    engines = {chess.WHITE: white, chess.BLACK: black}
    play_kwargs = {}
    if game is not None:
        play_kwargs["game"] = game
    if adjudicator is not None:
        play_kwargs["info"] = chess.engine.INFO_SCORE
    moves = []
    verdict = None
    while not board.is_game_over(claim_draw=True) and len(moves) < max_moves:
        ply = len(moves) + 1
        side = color_name(board.turn)
        if progress_mode == "move":
            write_progress(progress, f"{game_label} ply {ply} {side} thinking...")
        started = time.monotonic()
        played = engines[board.turn].play(board, limit, **play_kwargs)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if played.move is None:
            if progress_mode == "move":
                write_progress(
                    progress,
                    f"{game_label} ply {ply} {side} returned no move in {elapsed_ms}ms",
                )
            break
        if progress_mode == "move":
            write_progress(
                progress,
                f"{game_label} ply {ply} {side} played {played.move.uci()} in {elapsed_ms}ms",
            )
        board.push(played.move)
        moves.append(played.move.uci())
        if adjudicator is not None and played.info.get("score") is not None:
            verdict = adjudicator.update(
                len(moves), white_relative_cp(played.info["score"])
            )
            if verdict is not None:
                break
    if verdict is None:
        verdict = board.result(claim_draw=True)
        if verdict == "*":
            verdict = "1/2-1/2"
    return GameResult(verdict, moves)


def play_pair(
    engine1,
    engine2,
    opening_fen,
    limit,
    max_moves,
    *,
    pair_index=0,
    adjudicator_factory=None,
):
    """Play one opening twice with the colors swapped (engine1 White, then
    engine1 Black). Returns (engine1_white_game, engine1_black_game) as
    GameResults from each game's own view — the unit the pentanomial SPRT scores.
    `ucinewgame` is sent before each game via a unique `game` token."""
    first = play_game(
        engine1,
        engine2,
        opening_fen,
        limit,
        max_moves,
        game=(pair_index, 0),
        adjudicator=adjudicator_factory() if adjudicator_factory else None,
    )
    second = play_game(
        engine2,
        engine1,
        opening_fen,
        limit,
        max_moves,
        game=(pair_index, 1),
        adjudicator=adjudicator_factory() if adjudicator_factory else None,
    )
    return first, second


def run_match(
    engine1_command,
    engine2_command,
    openings,
    games,
    limit,
    max_moves,
    progress=None,
    progress_mode="none",
    adjudicator_factory=None,
):
    """Play `games` games alternating colors and return (wins, losses, draws)
    from engine1's view. `ucinewgame` is sent before every game."""
    wins = losses = draws = 0
    with (
        chess.engine.SimpleEngine.popen_uci(engine1_command) as engine1,
        chess.engine.SimpleEngine.popen_uci(engine2_command) as engine2,
    ):
        for game_index in range(games):
            opening_fen = openings[(game_index // 2) % len(openings)]
            opening_number = (game_index // 2) % len(openings) + 1
            engine1_is_white = game_index % 2 == 0
            game_label = f"game {game_index + 1}/{games}"
            if progress_mode in {"game", "move"}:
                engine1_color = "white" if engine1_is_white else "black"
                write_progress(
                    progress,
                    f"{game_label} start: opening={opening_number} engine1={engine1_color}",
                )
            white, black = (
                (engine1, engine2) if engine1_is_white else (engine2, engine1)
            )
            played = play_game(
                white,
                black,
                opening_fen,
                limit,
                max_moves,
                game=game_index,
                adjudicator=adjudicator_factory() if adjudicator_factory else None,
                progress=progress,
                progress_mode=progress_mode,
                game_label=game_label,
            )
            result = played.result
            if result == "1/2-1/2":
                draws += 1
            elif (result == "1-0") == engine1_is_white:
                wins += 1
            else:
                losses += 1
            if progress_mode in {"game", "move"}:
                write_progress(
                    progress,
                    f"{game_label} result: {result} score +{wins} -{losses} ={draws}",
                )
    return wins, losses, draws


def opening_fen(line):
    """Return a FEN for an opening line, accepting either a full FEN or an EPD
    line with operations (the format of the UHO books)."""
    try:
        return chess.Board(line).fen()
    except ValueError:
        board = chess.Board()
        board.set_epd(line)
        return board.fen()


def load_openings(path):
    openings = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                openings.append(opening_fen(line))
    return openings


def make_limit(movetime, depth, nodes=None):
    if nodes is not None:
        return chess.engine.Limit(nodes=nodes)
    if depth is not None:
        return chess.engine.Limit(depth=depth)
    if movetime is not None:
        return chess.engine.Limit(time=movetime / 1000.0)
    return chess.engine.Limit(depth=4)
