//! MoveSorter — orders legal moves to improve pruning, a port of
//! `src/move_sorter.py`.
//!
//! Full search order: checks, then captures by MVV-LVA, then quiet moves by
//! their position-value change. Quiescence uses checks + captures only (or every
//! evasion when in check). `is_endgame` is the frozen root value.

use std::cmp::Reverse;

use crate::attacks::is_square_attacked;
use crate::board::Board;
use crate::chess_move::Move;
use crate::eval::{position_value, PIECE_VALUES};
use crate::movegen::generate_legal;
use crate::types::{Color, PieceType, Square};

pub fn in_check(board: &Board) -> bool {
    let us = board.side_to_move();
    is_square_attacked(board, board.king_square(us), us.opponent())
}

/// Does playing `mv` give check to the opponent?
fn gives_check(board: &mut Board, mv: Move) -> bool {
    let mover = board.side_to_move();
    let opponent = mover.opponent();
    let undo = board.make_move(mv);
    let opponent_king = board.king_square(opponent);
    let checked = is_square_attacked(board, opponent_king, mover);
    board.unmake_move(mv, undo);
    checked
}

fn capture_value(board: &Board, mv: Move) -> i32 {
    if mv.is_en_passant() {
        return PIECE_VALUES[PieceType::Pawn.index()];
    }
    let aggressor = board.piece_at(mv.from()).expect("mover present").piece_type;
    let victim = board.piece_at(mv.to()).expect("victim present").piece_type;
    PIECE_VALUES[victim.index()] - PIECE_VALUES[aggressor.index()]
}

fn position_value_change(
    piece: PieceType,
    color: Color,
    from: Square,
    to: Square,
    is_endgame: bool,
) -> i32 {
    position_value(piece, color, to, is_endgame) - position_value(piece, color, from, is_endgame)
}

/// The ordering score for a non-MVV-LVA move: promotion is a queen's worth;
/// otherwise capture gain plus the piece-square change.
pub fn evaluate_move_value(board: &Board, mv: Move, is_endgame: bool) -> i32 {
    if mv.promotion().is_some() {
        return PIECE_VALUES[PieceType::Queen.index()];
    }
    let mut value = 0;
    if mv.is_capture() {
        value += capture_value(board, mv);
    }
    let color = board.side_to_move();
    let piece = board.piece_at(mv.from()).expect("mover present").piece_type;
    value += position_value_change(piece, color, mv.from(), mv.to(), is_endgame);
    value
}

fn sort_by_value(board: &Board, mut moves: Vec<Move>, is_endgame: bool) -> Vec<Move> {
    moves.sort_by_key(|&mv| Reverse(evaluate_move_value(board, mv, is_endgame)));
    moves
}

/// Most Valuable Victim, Least Valuable Aggressor: highest victim first, then
/// lowest aggressor.
fn sort_mvv_lva(board: &Board, mut moves: Vec<Move>) -> Vec<Move> {
    moves.sort_by_key(|&mv| {
        let (victim, aggressor) = victim_and_aggressor(board, mv);
        (Reverse(victim), aggressor)
    });
    moves
}

fn victim_and_aggressor(board: &Board, mv: Move) -> (i32, i32) {
    if mv.is_en_passant() {
        let pawn = PIECE_VALUES[PieceType::Pawn.index()];
        return (pawn, pawn);
    }
    let aggressor = board.piece_at(mv.from()).expect("mover present").piece_type;
    let victim = board.piece_at(mv.to()).expect("victim present").piece_type;
    (
        PIECE_VALUES[victim.index()],
        PIECE_VALUES[aggressor.index()],
    )
}

fn group(board: &mut Board, moves: &[Move]) -> (Vec<Move>, Vec<Move>, Vec<Move>) {
    let mut checks = Vec::new();
    let mut captures = Vec::new();
    let mut quiets = Vec::new();
    for &mv in moves {
        if gives_check(board, mv) {
            checks.push(mv);
        } else if mv.is_capture() {
            captures.push(mv);
        } else {
            quiets.push(mv);
        }
    }
    (checks, captures, quiets)
}

/// Legal moves ordered checks → captures (MVV-LVA) → quiet (by value).
pub fn prioritize_legal_moves(board: &mut Board, is_endgame: bool) -> Vec<Move> {
    let moves = generate_legal(board);
    let (checks, captures, quiets) = group(board, &moves);
    let mut ordered = Vec::with_capacity(moves.len());
    ordered.extend(sort_by_value(board, checks, is_endgame));
    ordered.extend(sort_mvv_lva(board, captures));
    ordered.extend(sort_by_value(board, quiets, is_endgame));
    ordered
}

/// Moves searched in quiescence: every evasion when in check, else checks +
/// captures.
pub fn get_moves_to_dequiet(board: &mut Board, is_endgame: bool) -> Vec<Move> {
    if in_check(board) {
        return prioritize_legal_moves(board, is_endgame);
    }
    let moves = generate_legal(board);
    let (checks, captures, _quiets) = group(board, &moves);
    let mut ordered = Vec::with_capacity(checks.len() + captures.len());
    ordered.extend(sort_by_value(board, checks, is_endgame));
    ordered.extend(sort_mvv_lva(board, captures));
    ordered
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ordering_groups_checks_then_captures_then_quiets() {
        let mut board =
            Board::from_fen("rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1")
                .unwrap();
        let ordered = prioritize_legal_moves(&mut board, false);
        // Rank each move by its group; the sequence must be non-decreasing.
        let ranks: Vec<u8> = ordered
            .iter()
            .map(|&mv| {
                if gives_check(&mut board.clone(), mv) {
                    0
                } else if mv.is_capture() {
                    1
                } else {
                    2
                }
            })
            .collect();
        let mut sorted = ranks.clone();
        sorted.sort_unstable();
        assert_eq!(
            ranks, sorted,
            "moves must be grouped checks, captures, quiets"
        );
    }

    #[test]
    fn mvv_lva_prefers_capturing_the_higher_value_victim() {
        // White can play e4xd5 (pawn takes queen) or Qa1xa7 (queen takes pawn).
        let mut board = Board::from_fen("6k1/p7/8/3q4/4P3/8/8/Q3K3 w - - 0 1").unwrap();
        let captures: Vec<Move> = generate_legal(&mut board)
            .into_iter()
            .filter(|mv| mv.is_capture())
            .collect();
        let ordered = sort_mvv_lva(&board, captures);
        assert_eq!(ordered[0].to_uci(), "e4d5");
    }
}
