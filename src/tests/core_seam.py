"""Walking-skeleton seam test: Python imports the Rust core and it answers.

Proves the PyO3 boundary is wired — the module imports, the Searcher class and
perft function exist, and a coarse call returns the right shape. Move-quality and
movegen correctness are covered by later waves, not here.
"""

import unittest

import brandobot_core

STARTPOS_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class CoreSeamTest(unittest.TestCase):
    def test_module_exposes_searcher_and_perft(self):
        self.assertTrue(hasattr(brandobot_core, "Searcher"))
        self.assertTrue(hasattr(brandobot_core, "perft"))

    def test_searcher_next_move_returns_a_uci_string(self):
        searcher = brandobot_core.Searcher()
        searcher.set_position(moves=["e2e4", "e7e5"])
        move = searcher.next_move(1)
        self.assertIsInstance(move, str)
        self.assertGreaterEqual(len(move), 4)

    def test_searcher_round_trips_a_fen(self):
        searcher = brandobot_core.Searcher()
        searcher.set_fen(STARTPOS_FEN)
        self.assertEqual(searcher.fen(), STARTPOS_FEN)

    def test_perft_returns_an_int(self):
        self.assertIsInstance(brandobot_core.perft(STARTPOS_FEN, 1), int)


if __name__ == "__main__":
    unittest.main()
