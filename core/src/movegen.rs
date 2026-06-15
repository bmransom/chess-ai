//! Move generation: pseudo-legal moves filtered to legal by make/unmake plus a
//! king-safety check, and `perft` — the leaf-node count that validates it all.

use crate::attacks::{
    bishop_attacks, is_square_attacked, king_attacks, knight_attacks, pawn_attacks, queen_attacks,
    rook_attacks,
};
use crate::board::{Board, CASTLE_BK, CASTLE_BQ, CASTLE_WK, CASTLE_WQ};
use crate::chess_move::{flag, Move};
use crate::types::{pop_lsb, rank_of, square_bb, Bitboard, Color, PieceType, Square};

/// Every legal move for the side to move.
pub fn generate_legal(board: &mut Board) -> Vec<Move> {
    let mut pseudo = Vec::with_capacity(48);
    generate_pseudo_legal(board, &mut pseudo);

    let us = board.side_to_move();
    let opponent = us.opponent();
    let mut legal = Vec::with_capacity(pseudo.len());
    for mv in pseudo {
        let undo = board.make_move(mv);
        let king = board.king_square(us);
        if !is_square_attacked(board, king, opponent) {
            legal.push(mv);
        }
        board.unmake_move(mv, undo);
    }
    legal
}

fn generate_pseudo_legal(board: &Board, moves: &mut Vec<Move>) {
    let us = board.side_to_move();
    generate_pawn_moves(board, us, moves);
    generate_knight_moves(board, us, moves);
    generate_slider_moves(board, us, PieceType::Bishop, moves);
    generate_slider_moves(board, us, PieceType::Rook, moves);
    generate_slider_moves(board, us, PieceType::Queen, moves);
    generate_king_moves(board, us, moves);
    generate_castling(board, us, moves);
}

fn generate_pawn_moves(board: &Board, us: Color, moves: &mut Vec<Move>) {
    let enemy = board.occupancy(us.opponent());
    let empty = !board.occupied();
    let forward: i8 = if us == Color::White { 8 } else { -8 };
    let start_rank: u8 = if us == Color::White { 1 } else { 6 };
    let promo_rank: u8 = if us == Color::White { 7 } else { 0 };

    let mut pawns = board.pieces(us, PieceType::Pawn);
    while pawns != 0 {
        let from = pop_lsb(&mut pawns);
        let push = (from as i8 + forward) as Square;

        if empty & square_bb(push) != 0 {
            if rank_of(push) == promo_rank {
                push_promotions(moves, from, push, false);
            } else {
                moves.push(Move::new(from, push, flag::QUIET));
                if rank_of(from) == start_rank {
                    let double = (push as i8 + forward) as Square;
                    if empty & square_bb(double) != 0 {
                        moves.push(Move::new(from, double, flag::DOUBLE_PAWN_PUSH));
                    }
                }
            }
        }

        let mut captures = pawn_attacks(us, from) & enemy;
        while captures != 0 {
            let to = pop_lsb(&mut captures);
            if rank_of(to) == promo_rank {
                push_promotions(moves, from, to, true);
            } else {
                moves.push(Move::new(from, to, flag::CAPTURE));
            }
        }

        if let Some(ep_square) = board.en_passant() {
            if pawn_attacks(us, from) & square_bb(ep_square) != 0 {
                moves.push(Move::new(from, ep_square, flag::EN_PASSANT));
            }
        }
    }
}

fn push_promotions(moves: &mut Vec<Move>, from: Square, to: Square, capture: bool) {
    let flags = if capture {
        [
            flag::PROMO_KNIGHT_CAPTURE,
            flag::PROMO_BISHOP_CAPTURE,
            flag::PROMO_ROOK_CAPTURE,
            flag::PROMO_QUEEN_CAPTURE,
        ]
    } else {
        [
            flag::PROMO_KNIGHT,
            flag::PROMO_BISHOP,
            flag::PROMO_ROOK,
            flag::PROMO_QUEEN,
        ]
    };
    for flag in flags {
        moves.push(Move::new(from, to, flag));
    }
}

fn generate_knight_moves(board: &Board, us: Color, moves: &mut Vec<Move>) {
    let own = board.occupancy(us);
    let enemy = board.occupancy(us.opponent());
    let mut knights = board.pieces(us, PieceType::Knight);
    while knights != 0 {
        let from = pop_lsb(&mut knights);
        push_targets(moves, from, knight_attacks(from) & !own, enemy);
    }
}

fn generate_king_moves(board: &Board, us: Color, moves: &mut Vec<Move>) {
    let own = board.occupancy(us);
    let enemy = board.occupancy(us.opponent());
    let from = board.king_square(us);
    push_targets(moves, from, king_attacks(from) & !own, enemy);
}

fn generate_slider_moves(board: &Board, us: Color, piece_type: PieceType, moves: &mut Vec<Move>) {
    let own = board.occupancy(us);
    let enemy = board.occupancy(us.opponent());
    let occupied = board.occupied();
    let mut sliders = board.pieces(us, piece_type);
    while sliders != 0 {
        let from = pop_lsb(&mut sliders);
        let attacks = match piece_type {
            PieceType::Bishop => bishop_attacks(from, occupied),
            PieceType::Rook => rook_attacks(from, occupied),
            PieceType::Queen => queen_attacks(from, occupied),
            _ => 0,
        };
        push_targets(moves, from, attacks & !own, enemy);
    }
}

fn push_targets(moves: &mut Vec<Move>, from: Square, mut targets: Bitboard, enemy: Bitboard) {
    while targets != 0 {
        let to = pop_lsb(&mut targets);
        let flag = if enemy & square_bb(to) != 0 {
            flag::CAPTURE
        } else {
            flag::QUIET
        };
        moves.push(Move::new(from, to, flag));
    }
}

fn generate_castling(board: &Board, us: Color, moves: &mut Vec<Move>) {
    let them = us.opponent();
    let king_square: Square = if us == Color::White { 4 } else { 60 };
    if is_square_attacked(board, king_square, them) {
        return;
    }
    let occupied = board.occupied();
    let rights = board.castling_rights();
    let (kingside, queenside) = if us == Color::White {
        (CASTLE_WK, CASTLE_WQ)
    } else {
        (CASTLE_BK, CASTLE_BQ)
    };

    if rights & kingside != 0 {
        let (bishop_square, knight_square) = if us == Color::White { (5, 6) } else { (61, 62) };
        let between = square_bb(bishop_square) | square_bb(knight_square);
        if occupied & between == 0
            && !is_square_attacked(board, bishop_square, them)
            && !is_square_attacked(board, knight_square, them)
        {
            moves.push(Move::new(king_square, knight_square, flag::KING_CASTLE));
        }
    }

    if rights & queenside != 0 {
        let (queen_square, bishop_square, knight_square) = if us == Color::White {
            (3, 2, 1)
        } else {
            (59, 58, 57)
        };
        let between = square_bb(queen_square) | square_bb(bishop_square) | square_bb(knight_square);
        if occupied & between == 0
            && !is_square_attacked(board, queen_square, them)
            && !is_square_attacked(board, bishop_square, them)
        {
            moves.push(Move::new(king_square, bishop_square, flag::QUEEN_CASTLE));
        }
    }
}

/// Count leaf nodes to `depth` — the move-generation gate.
pub fn perft(board: &mut Board, depth: u32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let moves = generate_legal(board);
    if depth == 1 {
        return moves.len() as u64;
    }
    let mut nodes = 0;
    for mv in moves {
        let undo = board.make_move(mv);
        nodes += perft(board, depth - 1);
        board.unmake_move(mv, undo);
    }
    nodes
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(fen: &str, expected: &[u64]) {
        let mut board = Board::from_fen(fen).unwrap();
        for (index, &nodes) in expected.iter().enumerate() {
            let depth = index as u32 + 1;
            assert_eq!(perft(&mut board, depth), nodes, "{fen} at depth {depth}");
        }
    }

    #[test]
    fn perft_matches_published_counts() {
        // The six canonical Chess Programming Wiki positions, to published counts.
        check(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            &[20, 400, 8902, 197281, 4865609],
        );
        check(
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            &[48, 2039, 97862, 4085603],
        );
        check(
            "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
            &[14, 191, 2812, 43238, 674624],
        );
        check(
            "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
            &[6, 264, 9467, 422333],
        );
        check(
            "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
            &[44, 1486, 62379, 2103487],
        );
        check(
            "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
            &[46, 2079, 89890],
        );
    }
}
