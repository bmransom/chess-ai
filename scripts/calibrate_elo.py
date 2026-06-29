"""Estimate brandobot's absolute Elo from matches vs Stockfish at calibrated levels.

Stockfish's `UCI_LimitStrength` + `UCI_Elo` make it play at a target rating.
brandobot (with its NNUE net) plays colour-balanced games against Stockfish at a
spread of levels; from each level's score we back out an implied brandobot Elo, and
the levels nearest 50% give the estimate. The number is for the chosen move-time on
this machine, and Stockfish's `UCI_Elo` calibration is approximate — so read it as a
ballpark, not a rating-list figure.

    .venv/bin/python scripts/calibrate_elo.py --net nets/net.nnue
"""

import argparse
import math
import random
import subprocess
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parent.parent
BRANDOBOT = [sys.executable, str(ROOT / "src" / "main.py")]
STOCKFISH = str(ROOT / "bin" / "stockfish")
SF_ELO_RANGE = (1320, 3190)


def load_openings(path, count, seed):
    if not path.exists():
        return [chess.STARTING_FEN]
    fens = [
        line.split(" bm ")[0].split(" ; ")[0].strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return random.Random(seed).sample(fens, min(count, len(fens))) or [chess.STARTING_FEN]


def play(white, black, opening, limit, max_plies, game_id):
    """One game; return White's score (1.0 / 0.5 / 0.0)."""
    board = chess.Board(opening)
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < max_plies:
        engine = white if board.turn == chess.WHITE else black
        board.push(engine.play(board, limit, game=game_id).move)
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return 0.5
    return 1.0 if outcome.winner == chess.WHITE else 0.0


def implied_elo(level, score):
    score = min(max(score, 1e-4), 1.0 - 1e-4)
    return level - 400.0 * math.log10(1.0 / score - 1.0)


def main():
    parser = argparse.ArgumentParser(description="Estimate brandobot's absolute Elo.")
    parser.add_argument("--net", default=str(ROOT / "nets" / "net.nnue"))
    parser.add_argument("--levels", type=int, nargs="+", default=[1500, 1900, 2300, 2700])
    parser.add_argument("--games", type=int, default=20, help="games per level")
    parser.add_argument("--movetime", type=float, default=0.3, help="seconds per move")
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--openings", type=Path, default=ROOT / "bench" / "uho_4060_v4.epd")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    command = BRANDOBOT + (["--net", args.net] if args.net else [])
    openings = load_openings(args.openings, 64, args.seed)
    limit = chess.engine.Limit(time=args.movetime)

    results = []
    with (
        chess.engine.SimpleEngine.popen_uci(command, stderr=subprocess.DEVNULL) as bot,
        chess.engine.SimpleEngine.popen_uci(STOCKFISH, stderr=subprocess.DEVNULL) as stockfish,
    ):
        for level in args.levels:
            stockfish.configure(
                {"UCI_LimitStrength": True, "UCI_Elo": max(SF_ELO_RANGE[0], min(SF_ELO_RANGE[1], level))}
            )
            wins = draws = losses = 0
            for game in range(args.games):
                opening = openings[game % len(openings)]
                bot_white = game % 2 == 0
                white, black = (bot, stockfish) if bot_white else (stockfish, bot)
                white_score = play(white, black, opening, limit, args.max_plies, (level, game))
                bot_score = white_score if bot_white else 1.0 - white_score
                wins += bot_score == 1.0
                draws += bot_score == 0.5
                losses += bot_score == 0.0
            score = (wins + 0.5 * draws) / args.games
            elo = implied_elo(level, score)
            results.append((level, score, elo))
            print(
                f"vs SF {level}: +{wins} ={draws} -{losses}  ({score*100:.0f}%)  "
                f"-> implied brandobot Elo ~{elo:.0f}",
                file=sys.stderr,
            )

    informative = [elo for _, score, elo in results if 0.10 < score < 0.90]
    estimate = sum(informative) / len(informative) if informative else sum(e for *_, e in results) / len(results)
    print(f"\nestimated brandobot Elo ≈ {estimate:.0f}  (at {args.movetime*1000:.0f}ms/move vs Stockfish UCI_Elo)")


if __name__ == "__main__":
    sys.exit(main())
