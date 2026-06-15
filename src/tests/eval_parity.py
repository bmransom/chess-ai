"""Eval parity: the Rust evaluation must match the Python evaluation exactly.

The Python `Board.value()` is the independent oracle. We compare it to
`brandobot_core.evaluate` across random positions, including endgames, so any
divergence — material, piece-square tables, or the endgame quirks — is caught.
"""

import random
import sys
import unittest

import chess

import brandobot_core

KNOWN_ENDGAME_FEN = "5k2/8/4p3/4Np2/3P4/7r/P3p3/6K1 b - - 0 1"

SEED_FENS = [
    chess.STARTING_FEN,
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "4k3/8/8/8/8/4P3/8/4K3 w - - 0 1",
]


def python_board_class():
    """Import the Python engine's Board lazily (keeps src off the import path
    until needed, so module-level imports stay clean)."""
    if "src" not in sys.path:
        sys.path.insert(0, "src")
    import board

    return board.Board


def random_positions(rng, plies, games_per_seed):
    for seed in SEED_FENS:
        for _ in range(games_per_seed):
            board = chess.Board(seed)
            for _ in range(plies):
                yield board.fen()
                moves = list(board.legal_moves)
                if not moves:
                    break
                board.push(rng.choice(moves))
            yield board.fen()


class EvalParityTest(unittest.TestCase):
    def test_known_endgame_value(self):
        self.assertEqual(brandobot_core.evaluate(KNOWN_ENDGAME_FEN), -290)

    def test_eval_matches_python(self):
        board_class = python_board_class()
        rng = random.Random(4242)
        for fen in random_positions(rng, plies=24, games_per_seed=3):
            python_board = board_class(fen)
            self.assertEqual(brandobot_core.evaluate(fen), python_board.value(), fen)
            self.assertEqual(
                brandobot_core.is_endgame(fen), python_board.is_endgame, fen
            )


if __name__ == "__main__":
    unittest.main()
