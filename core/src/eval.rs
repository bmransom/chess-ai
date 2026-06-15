//! Evaluation — material plus piece-square tables, a verbatim port of
//! `src/evaluate.py` and `Board.value` from `src/board.py`.
//!
//! Two quirks of the original are reproduced exactly for parity: the middlegame
//! tables are flipped to a1=0 order while the endgame-king table is used in raw
//! rank-8-first order, and the black tables are the white tables fully reversed
//! (a 180° rotation, equal to a vertical flip for these left-right-symmetric
//! tables). `is_endgame` is computed once at the search root and frozen.

use std::sync::OnceLock;

use crate::board::Board;
use crate::types::{pop_lsb, Color, PieceType, Square, NUM_COLORS, NUM_PIECE_TYPES};

/// Indexed by `PieceType` (pawn, knight, bishop, rook, queen, king).
pub const PIECE_VALUES: [i32; NUM_PIECE_TYPES] = [100, 320, 330, 500, 900, 20000];

#[rustfmt::skip]
const PAWN_HUMAN: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
];

#[rustfmt::skip]
const KNIGHT_HUMAN: [i32; 64] = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
];

#[rustfmt::skip]
const BISHOP_HUMAN: [i32; 64] = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
];

#[rustfmt::skip]
const ROOK_HUMAN: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
];

#[rustfmt::skip]
const QUEEN_HUMAN: [i32; 64] = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
];

#[rustfmt::skip]
const KING_MIDDLEGAME_HUMAN: [i32; 64] = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
];

#[rustfmt::skip]
const KING_ENDGAME_HUMAN: [i32; 64] = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
];

struct Tables {
    middlegame: [[[i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS],
    king_endgame: [[i32; 64]; NUM_COLORS],
}

static TABLES: OnceLock<Tables> = OnceLock::new();

fn tables() -> &'static Tables {
    TABLES.get_or_init(|| {
        let human = [
            PAWN_HUMAN,
            KNIGHT_HUMAN,
            BISHOP_HUMAN,
            ROOK_HUMAN,
            QUEEN_HUMAN,
            KING_MIDDLEGAME_HUMAN,
        ];
        let mut middlegame = [[[0i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS];
        for piece in 0..NUM_PIECE_TYPES {
            let flipped = flip_vertical(&human[piece]);
            middlegame[Color::White.index()][piece] = flipped;
            middlegame[Color::Black.index()][piece] = reverse(&flipped);
        }
        let mut king_endgame = [[0i32; 64]; NUM_COLORS];
        king_endgame[Color::White.index()] = KING_ENDGAME_HUMAN;
        king_endgame[Color::Black.index()] = reverse(&KING_ENDGAME_HUMAN);
        Tables {
            middlegame,
            king_endgame,
        }
    })
}

/// Convert a rank-8-first human table to a1=0 order (np.flip along ranks).
fn flip_vertical(human: &[i32; 64]) -> [i32; 64] {
    let mut out = [0i32; 64];
    for (square, slot) in out.iter_mut().enumerate() {
        let rank = square / 8;
        let file = square % 8;
        *slot = human[(7 - rank) * 8 + file];
    }
    out
}

/// Reverse the 64 entries — the original's `values[::-1]` for black.
fn reverse(values: &[i32; 64]) -> [i32; 64] {
    let mut out = [0i32; 64];
    for (square, slot) in out.iter_mut().enumerate() {
        *slot = values[63 - square];
    }
    out
}

pub fn position_value(piece: PieceType, color: Color, square: Square, is_endgame: bool) -> i32 {
    let tables = tables();
    if is_endgame && piece == PieceType::King {
        tables.king_endgame[color.index()][square as usize]
    } else {
        tables.middlegame[color.index()][piece.index()][square as usize]
    }
}

/// The endgame predicate from `Board.__is_endgame`: for each side, no queen or
/// at most one minor piece — true only when it holds for both.
pub fn is_endgame(board: &Board) -> bool {
    fn quiet_side(board: &Board, color: Color) -> bool {
        let queens = board.pieces(color, PieceType::Queen).count_ones();
        let minors = board.pieces(color, PieceType::Bishop).count_ones()
            + board.pieces(color, PieceType::Knight).count_ones();
        queens == 0 || minors <= 1
    }
    quiet_side(board, Color::White) && quiet_side(board, Color::Black)
}

/// Absolute (white-positive) evaluation: material plus piece-square bonus.
pub fn value(board: &Board, is_endgame: bool) -> i32 {
    let mut total = 0i32;
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        for piece in PieceType::ALL {
            let mut bitboard = board.pieces(color, piece);
            while bitboard != 0 {
                let square = pop_lsb(&mut bitboard);
                total += (PIECE_VALUES[piece.index()]
                    + position_value(piece, color, square, is_endgame))
                    * sign;
            }
        }
    }
    total
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_endgame_value_matches_python() {
        let board = Board::from_fen("5k2/8/4p3/4Np2/3P4/7r/P3p3/6K1 b - - 0 1").unwrap();
        assert!(is_endgame(&board));
        assert_eq!(value(&board, true), -290);
    }
}
