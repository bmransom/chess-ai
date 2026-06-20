import argparse
import sys

import brandobot_core

# UCI `go` token -> core search parameter. UCI tokens live only here.
GO_PARAMETERS = {
    "depth": "max_depth",
    "movetime": "move_time_ms",
    "nodes": "node_limit",
    "wtime": "white_time_ms",
    "btime": "black_time_ms",
    "winc": "white_increment_ms",
    "binc": "black_increment_ms",
    "movestogo": "moves_to_go",
}


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
        go(searcher, depth, message)
        return


def go(searcher, default_depth, message):
    """Run a search for a `go` command and report `info` then `bestmove`."""
    limits = parse_go(message)
    if limits is None:
        result = searcher.search(max_depth=default_depth)
    else:
        result = searcher.search(**limits)

    print(info_line(result))
    print(f"bestmove {result['best_move']}")


def parse_go(message):
    """Translate the `go` time-control tokens into core search parameters, or
    None for a bare `go` (or one with no recognized limits)."""
    tokens = message.split()[1:]
    limits = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in GO_PARAMETERS and index + 1 < len(tokens):
            try:
                limits[GO_PARAMETERS[token]] = int(tokens[index + 1])
            except ValueError:
                pass
            index += 2
        else:
            index += 1
    return limits or None


def info_line(result):
    """Format a search result as a UCI `info` line."""
    if result["mate_in_moves"] is not None:
        score = f"mate {result['mate_in_moves']}"
    else:
        score = f"cp {result['score_centipawns']}"
    pv = " ".join(result["principal_variation"])
    return (
        f"info depth {result['depth']} score {score} "
        f"nodes {result['nodes']} time {result['elapsed_ms']} pv {pv}"
    )


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
    parser.add_argument("--depth", default=3, help="default search depth (default: 3)")
    args, _ = parser.parse_known_args()
    return int(args.depth)
