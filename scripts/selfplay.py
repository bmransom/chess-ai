"""Self-play match: two UCI engines play a match; report the result and Elo.

python-chess drives each engine as a UCI subprocess and arbitrates the games, so
the referee shares no code with the engine under test. Build a baseline in a git
worktree to compare against a candidate. Game playing, the opening book, and
`ucinewgame` hygiene live in `match_core`; this script is the fixed-N Elo
reporter. For a sequential, bounded-error verdict, use `sprt.py`.

    python scripts/selfplay.py --games 200 --movetime 100 \\
      --engine1 "python src/main.py" --engine2 "python ../base/src/main.py"
"""

import argparse
import math
import shlex
import sys

from match_core import load_openings, make_limit, play_game, run_match  # noqa: F401


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
        "--nodes", type=int, help="fixed node budget per move (deterministic)"
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
    parser.add_argument(
        "--progress",
        choices=("none", "game", "move"),
        default="none",
        help="print progress to stderr while the match runs",
    )
    args = parser.parse_args()

    openings = load_openings(args.openings)
    games = args.games if args.games is not None else len(openings) * 2
    limit = make_limit(args.movetime, args.depth, args.nodes)
    progress = sys.stderr if args.progress != "none" else None

    wins, losses, draws = run_match(
        shlex.split(args.engine1),
        shlex.split(args.engine2),
        openings,
        games,
        limit,
        args.max_moves,
        progress=progress,
        progress_mode=args.progress,
    )
    score = 100 * (wins + 0.5 * draws) / games if games else 0.0
    elo, margin = elo_estimate(wins, losses, draws)
    print(
        f"engine1 vs engine2: +{wins} -{losses} ={draws}, "
        f"{score:.1f}%, Elo {elo:+.0f} ± {margin:.0f}"
    )


if __name__ == "__main__":
    main()
