import sys
sys.path.insert(0, 'src')
import unittest
from board import Board

class BoardTest(unittest.TestCase):

    def test_board_value(self):
        board = Board('5k2/8/4p3/4Np2/3P4/7r/P3p3/6K1 b - - 0 1')
        self.assertEqual(board.value(), -290)

if __name__ == '__main__':
    unittest.main()
