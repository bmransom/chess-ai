import time
import uuid
import sys
import chess.polyglot

def call_counter(func):
    def helper(*args, **kwargs):
        helper.calls += 1
        return func(*args, **kwargs)
    helper.calls = 0
    helper.__name__= func.__name__

    return helper

def timer(func):
    def helper(*args, **kwargs):
        tic = time.perf_counter()
        result = func(*args, **kwargs)
        toc = time.perf_counter()
        print(f"{func.__name__} took {toc - tic:0.4f} seconds to execute")
        return result
    helper.__name__= func.__name__

    return helper

def generate_move_tree(func):
    def helper(*args, **kwargs):
        node_id = uuid.uuid4()
        board = args[1]
        alpha = args[3]
        beta = args[4]
        try:
            move = board.peek()
        except IndexError:
            move = 'root'
            node_id = 'root'

        # caller function (parent)
        parent_kwargs = sys._getframe(0).f_locals["kwargs"]
        parent_id = parent_kwargs.get("node_id", "root")
        nodes = parent_kwargs.get("nodes", None)
        if nodes is None:
            nodes = []

        node = { "name": f"{move}", "id": node_id, "parent": parent_id, "alpha": -beta, "beta": -alpha, "is_white": not board.turn, "zobrist": chess.polyglot.zobrist_hash(board) }

        if move != 'root':
            nodes.append(node)

        kwargs.update({ "node_id": node_id, "nodes": nodes })
        result = func(*args, **kwargs)

        # Find a better way to do this
        if (type(result) is not tuple):
            node["value"] = -result

        return result

    helper.__name__= func.__name__

    return helper
