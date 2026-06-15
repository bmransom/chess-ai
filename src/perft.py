import time
from board import Board
from move_sorter import prioritize_legal_moves

def perft(depth, board):
    if depth == 1:
        return board.legal_moves.count()
    elif depth > 1:
        count = 0

        for move in prioritize_legal_moves(board):
            board.push(move)
            count += perft(depth - 1, board)
            board.pop()

        return count
    else:
        return 1

if __name__ == '__main__':
    tic = time.perf_counter()
    board = Board()
    nodes = perft(5, board)
    toc = time.perf_counter()
    print(f"Searched {nodes} moves in {toc - tic:0.4f} seconds")
