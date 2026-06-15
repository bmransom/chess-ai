"""Benchmark: brandobot_core (Rust) move generation vs python-chess.

python-chess is the library the old Python engine used for move generation, so it
is a fair proxy for the pre-port baseline. Both count the same nodes; we compare
wall-clock. Run: .venv/bin/python scripts/bench_perft.py
"""

import time

import chess

import brandobot_core

STARTPOS_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def python_chess_perft(board, depth):
    if depth == 0:
        return 1
    if depth == 1:
        return board.legal_moves.count()
    nodes = 0
    for move in board.legal_moves:
        board.push(move)
        nodes += python_chess_perft(board, depth - 1)
        board.pop()
    return nodes


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def main(max_depth=5):
    # Warm the Rust magic-bitboard init so it does not skew the first timing.
    brandobot_core.perft(STARTPOS_FEN, 1)

    header = (
        f"{'depth':>5} {'nodes':>12} {'rust (s)':>10} {'python (s)':>12} {'speedup':>9}"
    )
    print(header)
    print("-" * len(header))
    for depth in range(1, max_depth + 1):
        rust_nodes, rust_time = timed(
            lambda d=depth: brandobot_core.perft(STARTPOS_FEN, d)
        )
        py_nodes, py_time = timed(lambda d=depth: python_chess_perft(chess.Board(), d))
        assert rust_nodes == py_nodes, (depth, rust_nodes, py_nodes)
        speedup = py_time / rust_time if rust_time > 0 else float("inf")
        print(
            f"{depth:>5} {rust_nodes:>12,} {rust_time:>10.4f} {py_time:>12.4f} {speedup:>8.1f}x"
        )


if __name__ == "__main__":
    main()
