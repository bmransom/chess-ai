"""Self-play match: two UCI engines play a match; report the result and Elo.

python-chess drives each engine as a UCI subprocess and arbitrates the games
(legality, draws, adjudication), so the referee shares no code with the engine
under test. Build a baseline in a git worktree to compare against a candidate.

    python scripts/selfplay.py --games 200 --movetime 100 \\
      --engine1 "python src/main.py" --engine2 "python ../base/src/main.py"
"""

import argparse
import math
import shlex
import sys

import chess
import chess.engine


def elo_estimate(wins, losses, draws):
    """Return (elo, margin): the rating difference favoring the first engine and a
    95% error margin, from the match score."""
    games = wins + losses + draws
    if games == 0:
        return 0.0, 0.0
    score = (wins + 0.5 * draws) / games
    if score <= 0.0:
        return -800.0, 0.0
    if score >= 1.0:
        return 800.0, 0.0
    elo = -400.0 * math.log10(1.0 / score - 1.0)
    score_variance = (
        wins * (1.0 - score) ** 2
        + draws * (0.5 - score) ** 2
        + losses * (0.0 - score) ** 2
    ) / games
    standard_error = math.sqrt(score_variance / games)
    elo_per_score = 400.0 / (math.log(10.0) * score * (1.0 - score))
    margin = 1.96 * standard_error * elo_per_score
    return elo, margin


def play_game(white, black, opening_fen, limit, max_moves):
    """Play one game and return its result string (`1-0`, `0-1`, `1/2-1/2`)."""
    board = chess.Board(opening_fen)
    engines = {chess.WHITE: white, chess.BLACK: black}
    moves = 0
    while not board.is_game_over(claim_draw=True) and moves < max_moves:
        played = engines[board.turn].play(board, limit)
        if played.move is None:
            break
        board.push(played.move)
        moves += 1
    result = board.result(claim_draw=True)
    return result if result != "*" else "1/2-1/2"


def run_match(engine1_command, engine2_command, openings, games, limit, max_moves):
    """Play `games` games and return (wins, losses, draws) from engine1's view."""
    wins = losses = draws = 0
    with (
        chess.engine.SimpleEngine.popen_uci(engine1_command) as engine1,
        chess.engine.SimpleEngine.popen_uci(engine2_command) as engine2,
    ):
        for game_index in range(games):
            opening_fen = openings[(game_index // 2) % len(openings)]
            engine1_is_white = game_index % 2 == 0
            if engine1_is_white:
                result = play_game(engine1, engine2, opening_fen, limit, max_moves)
            else:
                result = play_game(engine2, engine1, opening_fen, limit, max_moves)

            if result == "1/2-1/2":
                draws += 1
            elif (result == "1-0") == engine1_is_white:
                wins += 1
            else:
                losses += 1
    return wins, losses, draws


def load_openings(path):
    openings = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                openings.append(line)
    return openings


def make_limit(movetime, depth):
    if depth is not None:
        return chess.engine.Limit(depth=depth)
    if movetime is not None:
        return chess.engine.Limit(time=movetime / 1000.0)
    return chess.engine.Limit(depth=4)


def main():
    default_engine = f"{sys.executable} src/main.py"
    parser = argparse.ArgumentParser(
        description="Play a self-play match and report Elo."
    )
    parser.add_argument(
        "--engine1", default=default_engine, help="candidate UCI command"
    )
    parser.add_argument(
        "--engine2", default=default_engine, help="baseline UCI command"
    )
    parser.add_argument(
        "--games", type=int, help="games to play (default: openings x2)"
    )
    parser.add_argument("--movetime", type=int, help="milliseconds per move")
    parser.add_argument(
        "--depth", type=int, help="fixed depth per move (deterministic)"
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=200,
        help="adjudicate a draw after this many moves",
    )
    parser.add_argument(
        "--openings",
        default="bench/openings.epd",
        help="opening positions (FEN per line)",
    )
    args = parser.parse_args()

    openings = load_openings(args.openings)
    games = args.games if args.games is not None else len(openings) * 2
    limit = make_limit(args.movetime, args.depth)

    wins, losses, draws = run_match(
        shlex.split(args.engine1),
        shlex.split(args.engine2),
        openings,
        games,
        limit,
        args.max_moves,
    )
    score = 100 * (wins + 0.5 * draws) / games if games else 0.0
    elo, margin = elo_estimate(wins, losses, draws)
    print(
        f"engine1 vs engine2: +{wins} -{losses} ={draws}, "
        f"{score:.1f}%, Elo {elo:+.0f} ± {margin:.0f}"
    )


if __name__ == "__main__":
    main()
