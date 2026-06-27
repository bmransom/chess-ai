"""Generate teacher-labeled training data for the NNUE net (distillation).

Plays brandobot self-play games from varied openings, keeps the quiet positions,
and labels each with the Stockfish teacher's white-positive eval. Each record also
carries the game's result (WDL, White's view) so the trainer can blend score and
result by its own lambda. Writes one record per line: ``<fen> | <cp> | <wdl>``.

Opening variety is the diversity source — fixed-depth self-play is deterministic,
so a large book (e.g. the UHO book via fetch_uho.py) yields one distinct game per
opening. Converting this intermediate to bulletformat is a separate step, paired
with the bullet trainer. See the nnue-eval spec, Wave 2.

    .venv/bin/python scripts/gen_data.py --games 50 --out data/train.txt
"""

import argparse
import random
import subprocess
import sys
from pathlib import Path

import chess
import chess.engine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label import is_quiet, open_teacher, teacher_eval  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENGINE = [sys.executable, str(ROOT / "src" / "main.py")]


def load_openings(path):
    """FEN/EPD openings, one per line; falls back to the start position."""
    if not path.exists():
        return [chess.STARTING_FEN]
    openings = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            openings.append(line.split(" bm ")[0].split(" ; ")[0].strip())
    return openings or [chess.STARTING_FEN]


def play_game(engine, opening, play_depth, max_plies):
    """Self-play from `opening`; return the quiet positions seen and the game's
    WDL from White's view (1.0 win, 0.5 draw, 0.0 loss)."""
    board = chess.Board(opening)
    quiet = []
    while not board.is_game_over(claim_draw=True) and len(board.move_stack) < max_plies:
        if is_quiet(board):
            quiet.append(board.fen())
        board.push(engine.play(board, chess.engine.Limit(depth=play_depth)).move)
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        wdl = 0.5
    else:
        wdl = 1.0 if outcome.winner == chess.WHITE else 0.0
    return quiet, wdl


def main():
    parser = argparse.ArgumentParser(
        description="Generate teacher-labeled NNUE training data."
    )
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument(
        "--play-depth", type=int, default=4, help="brandobot self-play search depth"
    )
    parser.add_argument(
        "--label-depth", type=int, default=8, help="teacher labeling depth"
    )
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument(
        "--openings", type=Path, default=ROOT / "bench" / "openings.epd"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "train.txt")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    random.seed(args.seed)
    openings = load_openings(args.openings)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with (
        chess.engine.SimpleEngine.popen_uci(ENGINE, stderr=subprocess.DEVNULL) as engine,
        open_teacher() as teacher,
        args.out.open("w") as out,
    ):
        for game in range(args.games):
            quiet, wdl = play_game(
                engine, random.choice(openings), args.play_depth, args.max_plies
            )
            for fen in quiet:
                cp = teacher_eval(chess.Board(fen), teacher, depth=args.label_depth)
                out.write(f"{fen} | {cp} | {wdl}\n")
            written += len(quiet)
            print(
                f"game {game + 1}/{args.games}: +{len(quiet)} quiet ({written} total)",
                file=sys.stderr,
            )
    print(f"wrote {written} positions to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
