"""EPD tactical suite: search each position and report the solve-rate.

A position is solved when the engine's searched move is among the position's `bm`
(best-move) operations. python-chess parses the EPD and converts each `bm` from
SAN to UCI, so the suite's known answers are the independent ground truth.

    python scripts/epd_suite.py --movetime 100 bench/wac.epd
"""

import argparse

import chess

import brandobot_core


def solved_move(searcher, fen, movetime, depth):
    """Search `fen` and return the engine's best move in UCI."""
    searcher.set_fen(fen)
    if depth is not None:
        return searcher.search(max_depth=depth)["best_move"]
    return searcher.search(move_time_ms=movetime)["best_move"]


def run(epd_lines, movetime=None, depth=None):
    """Return (solved, total, failures) for the EPD lines. Each failure is
    (fen, expected_uci_moves, played_uci)."""
    searcher = brandobot_core.Searcher()
    solved = 0
    total = 0
    failures = []
    for line in epd_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        board = chess.Board()
        operations = board.set_epd(line)
        best_moves = operations.get("bm")
        if not best_moves:
            continue
        total += 1
        expected = sorted(move.uci() for move in best_moves)
        played = solved_move(searcher, board.fen(), movetime, depth)
        if played in expected:
            solved += 1
        else:
            failures.append((board.fen(), expected, played))
    return solved, total, failures


def main():
    parser = argparse.ArgumentParser(description="Run an EPD tactical suite.")
    parser.add_argument("epd_file", help="path to an EPD file")
    parser.add_argument("--movetime", type=int, help="milliseconds per position")
    parser.add_argument("--depth", type=int, help="fixed search depth per position")
    args = parser.parse_args()
    if args.movetime is None and args.depth is None:
        args.movetime = 100

    with open(args.epd_file) as epd:
        solved, total, failures = run(epd, args.movetime, args.depth)

    rate = 100 * solved / total if total else 0.0
    print(f"{solved}/{total} solved ({rate:.1f}%)")
    for fen, expected, played in failures:
        print(f"  FAIL {fen} expected {' '.join(expected)} played {played}")


if __name__ == "__main__":
    main()
