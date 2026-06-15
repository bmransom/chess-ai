import time
import json
import chess
import chess.polyglot
from evaluate import color_multiplier
from transposition_table import HashEntry, Flag
from decorators import call_counter, generate_move_tree
from move_sorter import get_moves_to_dequiet, prioritize_legal_moves
from json_encoder import JSONEncoder

def handle_search_complete(pline, transposition_table, kwargs):
    print(f"Principal Variation: {pline}")

    nodes = kwargs.get("nodes")
    with open('tree.json', 'w') as f:
        f.write(json.dumps(nodes, indent=4, cls=JSONEncoder))

    table = getattr(transposition_table, 'table')
    json_table = list(map(lambda x: x.json(), filter(lambda entry: entry is not None, table)))
    with open('transposition_table.json', 'w') as f:
        f.write(json.dumps(json_table, indent=4, cls=JSONEncoder))

# TODO: Future enhancement... rotate the board so that the bot can play vs itself
class Searcher():
    def __init__(self, board, depth, transposition_table):
        self.board = board
        self.depth = depth
        self.transposition_table = transposition_table

    # https://en.wikipedia.org/wiki/Negamax#Negamax_with_alpha_beta_pruning_and_transposition_tables
    # only need to return best move at the top of the tree
    @call_counter
    @generate_move_tree
    def negamax(self, board, depth, alpha, beta, pline = [], **kwargs):
        line = []
        best_move = None

        if board.is_checkmate():
            return ( best_move, -99999 )
        # can_claim_draw() is slow, due to 3-fold repetition check... limiting it to non-quiescence search to improve perf
        elif depth > 0 and (board.is_stalemate() or board.can_claim_draw()):
            return ( best_move, 0 )

        alpha_orig = alpha

        zobrist = chess.polyglot.zobrist_hash(board)
        stored_entry = self.transposition_table.get(zobrist, depth)

        if stored_entry is not None and stored_entry.depth <= depth:
            if stored_entry.flag == Flag.EXACT:
                return ( stored_entry.best_move, stored_entry.value )
            elif stored_entry.flag == Flag.LOWER_BOUND:
                alpha = max(alpha, stored_entry.value)
            elif stored_entry.flag == Flag.UPPER_BOUND:
                beta = min(beta, stored_entry.value)

            if alpha >= beta:
                return ( stored_entry.best_move, stored_entry.value )

        if depth <= 0:
            color = board.turn
            stand_pat = board.value() * color_multiplier[color]
            if not board.is_check():
                if stand_pat >= beta:
                    return ( best_move, beta )
                alpha = max(alpha, stand_pat)

            if depth < -5:
                return ( best_move, stand_pat )

            moves = get_moves_to_dequiet(board)

            if not moves:
                return ( best_move, stand_pat )
        else:
            moves = prioritize_legal_moves(board)

        max_val = -99999
        for move in moves:
            board.push(move)
            result = self.negamax(board, depth - 1, -beta, -alpha, line, **kwargs)
            move_eval = -result[1]
            board.pop()

            if depth <= 0 and move_eval >= beta:
                return ( best_move, beta )

            if move_eval > max_val:
                best_move = move
                pline[:] = [str(move)] + line

            max_val = max(max_val, move_eval)
            alpha = max(alpha, max_val)

            if alpha >= beta:
                break

        flag_to_store = None
        if max_val <= alpha_orig:
            flag_to_store = Flag.UPPER_BOUND
        elif max_val >= beta:
            flag_to_store = Flag.LOWER_BOUND
        else:
            flag_to_store = Flag.EXACT
        
        # TODO: store principal variation in transposition_table
        new_entry = HashEntry(zobrist, best_move, depth, max_val, flag_to_store, board.halfmove_clock)
        self.transposition_table.replace(new_entry)

        if depth == self.depth:
            handle_search_complete(pline, self.transposition_table, kwargs)

        return ( best_move, max_val )

    def next_move(self):
        best_move = None
        alpha = -99999
        beta = 99999

        prioritized_moves = prioritize_legal_moves(self.board)

        tic = time.perf_counter()

        best_move, best_move_value = self.negamax(self.board, self.depth, alpha, beta)

        # handle case where checkmate is impending... we still need to move
        if best_move is None:
            best_move = prioritized_moves[0]

        toc = time.perf_counter()
        print(f"Searched {self.negamax.calls} moves, and found best move {best_move} with value: {best_move_value} in {toc - tic:0.4f} seconds")

        return best_move
