"""Differential test: brandobot_core move generation must agree with python-chess.

python-chess is an independent implementation, so this is a genuine oracle — not
the engine checking itself. We walk random games and, at each position, compare
the two engines' legal-move sets exactly.
"""

import random
import unittest

import chess

import brandobot_core

SEED_FENS = [
    chess.STARTING_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
]


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


class MovegenDifferentialTest(unittest.TestCase):
    def test_legal_moves_match_python_chess(self):
        # Hundreds of varied positions are ample as an independent cross-check;
        # cargo's perft suite already validates generation to millions of nodes.
        rng = random.Random(20260615)
        for fen in random_positions(rng, plies=30, games_per_seed=4):
            expected = sorted(move.uci() for move in chess.Board(fen).legal_moves)
            actual = sorted(brandobot_core.legal_moves(fen))
            self.assertEqual(actual, expected, f"mismatch at {fen}")


if __name__ == "__main__":
    unittest.main()
