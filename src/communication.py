import argparse
import sys

import brandobot_core


def talk():
    """The UCI input/output loop — a slice of the protocol that delegates all
    chess to brandobot_core. A single Searcher holds the game's position and
    transposition table."""
    searcher = brandobot_core.Searcher()
    depth = parse_depth()

    while True:
        message = input()
        print(f">>> {message}", file=sys.stderr)

        if message == "quit":
            break

        command(searcher, depth, message)


def command(searcher, depth, message):
    """Accept a UCI command and respond, updating the searcher's position."""
    if message == "uci":
        print("id name brandobot")
        print("id author Brandon Ransom")
        print("uciok")
        return

    if message == "isready":
        print("readyok")
        return

    if message == "ucinewgame":
        searcher.new_game()
        return

    if message.startswith("position"):
        set_position(searcher, message)
        return

    if message.startswith("go"):
        search_depth = depth + 4 if brandobot_core.is_endgame(searcher.fen()) else depth
        print(f"bestmove {searcher.next_move(search_depth)}")
        return


def set_position(searcher, message):
    """Apply `position startpos [moves ...]` or `position fen <FEN> [moves ...]`."""
    tokens = message.split()
    moves = []
    if "moves" in tokens:
        moves_index = tokens.index("moves")
        moves = tokens[moves_index + 1 :]
        head = tokens[1:moves_index]
    else:
        head = tokens[1:]

    if not head:
        return
    if head[0] == "startpos":
        searcher.set_position(fen=None, moves=moves)
    elif head[0] == "fen":
        searcher.set_position(fen=" ".join(head[1:]), moves=moves)


def parse_depth():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depth", default=3, help="search depth (default: 3)")
    args, _ = parser.parse_known_args()
    return int(args.depth)
