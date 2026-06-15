"""Eval parity: the Rust evaluation must match the values the original Python
engine produced.

The expected numbers below were captured from the Python `Board.value()` and
`Board.is_endgame` before the engine was ported to Rust, so this test stays a
parity regression guard for AC-3.x after the Python engine is removed.
"""

import unittest

import brandobot_core

# (fen, expected white-positive value, expected is_endgame)
GOLDEN = [
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 0, False),
    ("5k2/8/4p3/4Np2/3P4/7r/P3p3/6K1 b - - 0 1", -290, True),
    (
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        105,
        False,
    ),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", -20, True),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", 65, False),
    ("4k3/8/8/8/8/4P3/8/4K3 w - - 0 1", 100, True),
    ("8/8/8/4k3/8/8/4K3/8 w - - 0 1", -40, True),
    (
        "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 1",
        -30,
        False,
    ),
    ("8/5k2/8/8/8/8/2Q5/4K3 w - - 0 1", 895, True),
    (
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
        0,
        False,
    ),
]


class EvalParityTest(unittest.TestCase):
    def test_values_match_golden(self):
        for fen, value, _ in GOLDEN:
            self.assertEqual(brandobot_core.evaluate(fen), value, fen)

    def test_endgame_flag_matches_golden(self):
        for fen, _, endgame in GOLDEN:
            self.assertEqual(brandobot_core.is_endgame(fen), endgame, fen)


if __name__ == "__main__":
    unittest.main()
