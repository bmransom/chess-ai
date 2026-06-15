"""Move-generation benchmark — counts leaf nodes via the Rust core."""

import time

import brandobot_core

STARTPOS_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def main():
    for depth in range(1, 6):
        start = time.perf_counter()
        nodes = brandobot_core.perft(STARTPOS_FEN, depth)
        elapsed = time.perf_counter() - start
        print(f"perft({depth}) = {nodes}  ({elapsed:.4f}s)")


if __name__ == "__main__":
    main()
