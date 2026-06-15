//! Searcher — negamax with alpha-beta pruning, quiescence search, and the
//! transposition table, a port of `src/searcher.py`.
//!
//! `is_endgame` is frozen at the root and threaded through evaluation, matching
//! the original (which fixes it when the Board is built). Mate scores are flat
//! ±99999 with no distance-to-mate term, as in the original.

use crate::board::Board;
use crate::chess_move::Move;
use crate::eval;
use crate::movegen::generate_legal;
use crate::movesort::{get_moves_to_dequiet, in_check, prioritize_legal_moves};
use crate::tt::{Flag, HashEntry, TranspositionTable};
use crate::types::Color;

const MATE: i32 = 99999;
/// Quiescence stops descending captures below this depth.
const QUIESCENCE_FLOOR: i32 = -5;

pub struct Searcher<'a> {
    transposition_table: &'a mut TranspositionTable,
    is_endgame: bool,
    /// Zobrist keys along the current line, for threefold-repetition detection.
    history: Vec<u64>,
}

impl<'a> Searcher<'a> {
    pub fn new(transposition_table: &'a mut TranspositionTable, is_endgame: bool) -> Searcher<'a> {
        Searcher {
            transposition_table,
            is_endgame,
            history: Vec::new(),
        }
    }

    /// The best move for the side to move. When checkmate is unavoidable and the
    /// search names no move, fall back to the first ordered move — we must move.
    pub fn best_move(&mut self, board: &mut Board, depth: i32) -> Option<Move> {
        let (best, _value) = self.negamax(board, depth, -MATE, MATE);
        best.or_else(|| {
            prioritize_legal_moves(board, self.is_endgame)
                .into_iter()
                .next()
        })
    }

    /// Each root move paired with its negamax value — the data behind the
    /// decision-tree debug endpoint. Each move is searched with a full window,
    /// so every score is exact.
    pub fn root_scores(&mut self, board: &mut Board, depth: i32) -> Vec<(Move, i32)> {
        let moves = prioritize_legal_moves(board, self.is_endgame);
        let mut scores = Vec::with_capacity(moves.len());
        for mv in moves {
            let undo = board.make_move(mv);
            let (_, child) = self.negamax(board, depth - 1, -MATE, MATE);
            board.unmake_move(mv, undo);
            scores.push((mv, -child));
        }
        scores
    }

    fn negamax(
        &mut self,
        board: &mut Board,
        depth: i32,
        alpha: i32,
        beta: i32,
    ) -> (Option<Move>, i32) {
        let key = board.zobrist();
        self.history.push(key);
        let result = self.search_node(board, depth, alpha, beta, key);
        self.history.pop();
        result
    }

    fn search_node(
        &mut self,
        board: &mut Board,
        depth: i32,
        mut alpha: i32,
        mut beta: i32,
        key: u64,
    ) -> (Option<Move>, i32) {
        let checked = in_check(board);
        let has_legal_move = !generate_legal(board).is_empty();

        if !has_legal_move && checked {
            return (None, -MATE);
        }
        if depth > 0 && ((!has_legal_move && !checked) || self.is_draw(board, key)) {
            return (None, 0);
        }

        let alpha_orig = alpha;

        if let Some(stored) = self.transposition_table.get(key, depth) {
            if stored.depth <= depth {
                match stored.flag {
                    Flag::Exact => return (stored.best_move, stored.value),
                    Flag::LowerBound => alpha = alpha.max(stored.value),
                    Flag::UpperBound => beta = beta.min(stored.value),
                }
                if alpha >= beta {
                    return (stored.best_move, stored.value);
                }
            }
        }

        let moves = if depth <= 0 {
            let sign = if board.side_to_move() == Color::White {
                1
            } else {
                -1
            };
            let stand_pat = eval::value(board, self.is_endgame) * sign;
            if !checked {
                if stand_pat >= beta {
                    return (None, beta);
                }
                alpha = alpha.max(stand_pat);
            }
            if depth < QUIESCENCE_FLOOR {
                return (None, stand_pat);
            }
            let captures_and_checks = get_moves_to_dequiet(board, self.is_endgame);
            if captures_and_checks.is_empty() {
                return (None, stand_pat);
            }
            captures_and_checks
        } else {
            prioritize_legal_moves(board, self.is_endgame)
        };

        let mut max_val = -MATE;
        let mut best_move: Option<Move> = None;
        for mv in moves {
            let undo = board.make_move(mv);
            let (_, child) = self.negamax(board, depth - 1, -beta, -alpha);
            board.unmake_move(mv, undo);
            let move_eval = -child;

            if depth <= 0 && move_eval >= beta {
                return (best_move, beta);
            }
            if move_eval > max_val {
                best_move = Some(mv);
            }
            max_val = max_val.max(move_eval);
            alpha = alpha.max(max_val);
            if alpha >= beta {
                break;
            }
        }

        let flag = if max_val <= alpha_orig {
            Flag::UpperBound
        } else if max_val >= beta {
            Flag::LowerBound
        } else {
            Flag::Exact
        };
        self.transposition_table.replace(HashEntry {
            zobrist: key,
            best_move,
            depth,
            value: max_val,
            flag,
            age: board.halfmove_clock(),
        });

        (best_move, max_val)
    }

    fn is_draw(&self, board: &Board, key: u64) -> bool {
        if board.halfmove_clock() >= 100 {
            return true;
        }
        self.history.iter().filter(|&&seen| seen == key).count() >= 3
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn best(fen: &str, depth: i32) -> String {
        let mut board = Board::from_fen(fen).unwrap();
        let mut table = TranspositionTable::new();
        let is_endgame = eval::is_endgame(&board);
        let mut searcher = Searcher::new(&mut table, is_endgame);
        searcher
            .best_move(&mut board, depth)
            .expect("a legal move exists")
            .to_uci()
    }

    #[test]
    fn blocks_the_threatened_mate() {
        assert_eq!(
            best(
                "1r3rk1/p1p3pp/3bp3/1p1P1q2/P3pP2/2B1P2P/1P4Q1/4K1NR b K - 0 1",
                3
            ),
            "f8f7"
        );
    }

    #[test]
    fn moves_the_king_out_of_a_mating_net() {
        assert_eq!(
            best(
                "1r1qr3/pppbbQ1k/2n1p1p1/2PpP3/3P4/2P2N2/P1B2PP1/1RB1K3 b - - 0 1",
                3
            ),
            "h7h8"
        );
    }

    #[test]
    fn finds_the_mate_in_three() {
        assert_eq!(best("r5rk/5p1p/5R2/4B3/8/8/7P/7K w", 3), "f6a6");
    }

    #[test]
    fn declines_to_sacrifice_the_rook() {
        assert_ne!(
            best("2r3k1/6p1/5p1p/p2r4/3p4/6B1/PPP2PPP/R3R1K1 w - - 0 1", 3),
            "e1e8"
        );
    }
}
