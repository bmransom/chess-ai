//! Evaluation — tapered material and piece-square tables from PeSTO.
//!
//! PeSTO values and tables come from Chessprogramming Wiki's "PeSTO's
//! Evaluation Function". The source tables are rank-8-first; this module
//! converts them to the engine's a1=0 square mapping and mirrors black by rank.

use std::sync::OnceLock;

use crate::attacks;
use crate::board::Board;
use crate::types::{
    file_of, make_square, pop_lsb, rank_of, square_bb, Bitboard, Color, PieceType, Square,
    NUM_COLORS, NUM_PIECE_TYPES,
};

const PHASE_MAX: i32 = 24;
const PHASE_VALUES: [i32; NUM_PIECE_TYPES] = [0, 1, 1, 2, 4, 0];
const KING_SHIELD_MG: i32 = 12;
const KING_RING_ATTACK_MG: [i32; NUM_PIECE_TYPES] = [4, 10, 10, 14, 24, 0];
/// Per available-square mobility weight, indexed by `PieceType`; pawns and kings
/// score no mobility.
const MOBILITY_MG: [i32; NUM_PIECE_TYPES] = [0, 4, 4, 2, 1, 0];
const MOBILITY_EG: [i32; NUM_PIECE_TYPES] = [0, 4, 5, 4, 2, 0];

pub const MG_PIECE_VALUES: [i32; NUM_PIECE_TYPES] = [82, 337, 365, 477, 1025, 0];
pub const EG_PIECE_VALUES: [i32; NUM_PIECE_TYPES] = [94, 281, 297, 512, 936, 0];
/// Indexed by `PieceType` (pawn, knight, bishop, rook, queen, king).
pub const PIECE_VALUES: [i32; NUM_PIECE_TYPES] = MG_PIECE_VALUES;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Score {
    pub mg: i32,
    pub eg: i32,
}

impl Score {
    fn tapered(self, phase: i32) -> i32 {
        (self.mg * phase + self.eg * (PHASE_MAX - phase)) / PHASE_MAX
    }
}

#[rustfmt::skip]
const MG_PAWN_HUMAN: [i32; 64] = [
      0,   0,   0,   0,   0,   0,   0,   0,
     98, 134,  61,  95,  68, 126,  34, -11,
     -6,   7,  26,  31,  65,  56,  25, -20,
    -14,  13,   6,  21,  23,  12,  17, -23,
    -27,  -2,  -5,  12,  17,   6,  10, -25,
    -26,  -4,  -4, -10,   3,   3,  33, -12,
    -35,  -1, -20, -23, -15,  24,  38, -22,
      0,   0,   0,   0,   0,   0,   0,   0,
];

#[rustfmt::skip]
const EG_PAWN_HUMAN: [i32; 64] = [
      0,   0,   0,   0,   0,   0,   0,   0,
    178, 173, 158, 134, 147, 132, 165, 187,
     94, 100,  85,  67,  56,  53,  82,  84,
     32,  24,  13,   5,  -2,   4,  17,  17,
     13,   9,  -3,  -7,  -7,  -8,   3,  -1,
      4,   7,  -6,   1,   0,  -5,  -1,  -8,
     13,   8,   8,  10,  13,   0,   2,  -7,
      0,   0,   0,   0,   0,   0,   0,   0,
];

#[rustfmt::skip]
const MG_KNIGHT_HUMAN: [i32; 64] = [
    -167, -89, -34, -49,  61, -97, -15, -107,
     -73, -41,  72,  36,  23,  62,   7,  -17,
     -47,  60,  37,  65,  84, 129,  73,   44,
      -9,  17,  19,  53,  37,  69,  18,   22,
     -13,   4,  16,  13,  28,  19,  21,   -8,
     -23,  -9,  12,  10,  19,  17,  25,  -16,
     -29, -53, -12,  -3,  -1,  18, -14,  -19,
    -105, -21, -58, -33, -17, -28, -19,  -23,
];

#[rustfmt::skip]
const EG_KNIGHT_HUMAN: [i32; 64] = [
    -58, -38, -13, -28, -31, -27, -63, -99,
    -25,  -8, -25,  -2,  -9, -25, -24, -52,
    -24, -20,  10,   9,  -1,  -9, -19, -41,
    -17,   3,  22,  22,  22,  11,   8, -18,
    -18,  -6,  16,  25,  16,  17,   4, -18,
    -23,  -3,  -1,  15,  10,  -3, -20, -22,
    -42, -20, -10,  -5,  -2, -20, -23, -44,
    -29, -51, -23, -15, -22, -18, -50, -64,
];

#[rustfmt::skip]
const MG_BISHOP_HUMAN: [i32; 64] = [
    -29,   4, -82, -37, -25, -42,   7,  -8,
    -26,  16, -18, -13,  30,  59,  18, -47,
    -16,  37,  43,  40,  35,  50,  37,  -2,
     -4,   5,  19,  50,  37,  37,   7,  -2,
     -6,  13,  13,  26,  34,  12,  10,   4,
      0,  15,  15,  15,  14,  27,  18,  10,
      4,  15,  16,   0,   7,  21,  33,   1,
    -33,  -3, -14, -21, -13, -12, -39, -21,
];

#[rustfmt::skip]
const EG_BISHOP_HUMAN: [i32; 64] = [
    -14, -21, -11,  -8,  -7,  -9, -17, -24,
     -8,  -4,   7, -12,  -3, -13,  -4, -14,
      2,  -8,   0,  -1,  -2,   6,   0,   4,
     -3,   9,  12,   9,  14,  10,   3,   2,
     -6,   3,  13,  19,   7,  10,  -3,  -9,
    -12,  -3,   8,  10,  13,   3,  -7, -15,
    -14, -18,  -7,  -1,   4,  -9, -15, -27,
    -23,  -9, -23,  -5,  -9, -16,  -5, -17,
];

#[rustfmt::skip]
const MG_ROOK_HUMAN: [i32; 64] = [
     32,  42,  32,  51,  63,   9,  31,  43,
     27,  32,  58,  62,  80,  67,  26,  44,
     -5,  19,  26,  36,  17,  45,  61,  16,
    -24, -11,   7,  26,  24,  35,  -8, -20,
    -36, -26, -12,  -1,   9,  -7,   6, -23,
    -45, -25, -16, -17,   3,   0,  -5, -33,
    -44, -16, -20,  -9,  -1,  11,  -6, -71,
    -19, -13,   1,  17,  16,   7, -37, -26,
];

#[rustfmt::skip]
const EG_ROOK_HUMAN: [i32; 64] = [
     13,  10,  18,  15,  12,  12,   8,   5,
     11,  13,  13,  11,  -3,   3,   8,   3,
      7,   7,   7,   5,   4,  -3,  -5,  -3,
      4,   3,  13,   1,   2,   1,  -1,   2,
      3,   5,   8,   4,  -5,  -6,  -8, -11,
     -4,   0,  -5,  -1,  -7, -12,  -8, -16,
     -6,  -6,   0,   2,  -9,  -9, -11,  -3,
     -9,   2,   3,  -1,  -5, -13,   4, -20,
];

#[rustfmt::skip]
const MG_QUEEN_HUMAN: [i32; 64] = [
    -28,   0,  29,  12,  59,  44,  43,  45,
    -24, -39,  -5,   1, -16,  57,  28,  54,
    -13, -17,   7,   8,  29,  56,  47,  57,
    -27, -27, -16, -16,  -1,  17,  -2,   1,
     -9, -26,  -9, -10,  -2,  -4,   3,  -3,
    -14,   2, -11,  -2,  -5,   2,  14,   5,
    -35,  -8,  11,   2,   8,  15,  -3,   1,
     -1, -18,  -9,  10, -15, -25, -31, -50,
];

#[rustfmt::skip]
const EG_QUEEN_HUMAN: [i32; 64] = [
     -9,  22,  22,  27,  27,  19,  10,  20,
    -17,  20,  32,  41,  58,  25,  30,   0,
    -20,   6,   9,  49,  47,  35,  19,   9,
      3,  22,  24,  45,  57,  40,  57,  36,
    -18,  28,  19,  47,  31,  34,  39,  23,
    -16, -27,  15,   6,   9,  17,  10,   5,
    -22, -23, -30, -16, -16, -23, -36, -32,
    -33, -28, -22, -43,  -5, -32, -20, -41,
];

#[rustfmt::skip]
const MG_KING_HUMAN: [i32; 64] = [
    -65,  23,  16, -15, -56, -34,   2,  13,
     29,  -1, -20,  -7,  -8,  -4, -38, -29,
     -9,  24,   2, -16, -20,   6,  22, -22,
    -17, -20, -12, -27, -30, -25, -14, -36,
    -49,  -1, -27, -39, -46, -44, -33, -51,
    -14, -14, -22, -46, -44, -30, -15, -27,
      1,   7,  -8, -64, -43, -16,   9,   8,
    -15,  36,  12, -54,   8, -28,  24,  14,
];

#[rustfmt::skip]
const EG_KING_HUMAN: [i32; 64] = [
    -74, -35, -18, -18, -11,  15,   4, -17,
    -12,  17,  14,  17,  17,  38,  23,  11,
     10,  17,  23,  15,  20,  45,  44,  13,
     -8,  22,  24,  27,  26,  33,  26,   3,
    -18,  -4,  21,  24,  27,  23,   9, -11,
    -19,  -3,  11,  21,  23,  16,   7,  -9,
    -27, -11,   4,  13,  14,   4,  -5, -17,
    -53, -34, -21, -11, -28, -14, -24, -43,
];

struct Tables {
    middlegame: [[[i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS],
    endgame: [[[i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS],
}

static TABLES: OnceLock<Tables> = OnceLock::new();

fn tables() -> &'static Tables {
    TABLES.get_or_init(|| {
        let middlegame_human = [
            MG_PAWN_HUMAN,
            MG_KNIGHT_HUMAN,
            MG_BISHOP_HUMAN,
            MG_ROOK_HUMAN,
            MG_QUEEN_HUMAN,
            MG_KING_HUMAN,
        ];
        let endgame_human = [
            EG_PAWN_HUMAN,
            EG_KNIGHT_HUMAN,
            EG_BISHOP_HUMAN,
            EG_ROOK_HUMAN,
            EG_QUEEN_HUMAN,
            EG_KING_HUMAN,
        ];
        let mut middlegame = [[[0i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS];
        let mut endgame = [[[0i32; 64]; NUM_PIECE_TYPES]; NUM_COLORS];
        for piece in 0..NUM_PIECE_TYPES {
            let mg_white = flip_vertical(&middlegame_human[piece]);
            middlegame[Color::White.index()][piece] = mg_white;
            middlegame[Color::Black.index()][piece] = mirror_vertical(&mg_white);

            let eg_white = flip_vertical(&endgame_human[piece]);
            endgame[Color::White.index()][piece] = eg_white;
            endgame[Color::Black.index()][piece] = mirror_vertical(&eg_white);
        }
        Tables {
            middlegame,
            endgame,
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
fn mirror_vertical(values: &[i32; 64]) -> [i32; 64] {
    let mut out = [0i32; 64];
    for (square, slot) in out.iter_mut().enumerate() {
        *slot = values[square ^ 56];
    }
    out
}

pub fn mg_position_value(piece: PieceType, color: Color, square: Square) -> i32 {
    tables().middlegame[color.index()][piece.index()][square as usize]
}

pub fn eg_position_value(piece: PieceType, color: Color, square: Square) -> i32 {
    tables().endgame[color.index()][piece.index()][square as usize]
}

pub fn game_phase(board: &Board) -> i32 {
    let mut phase = 0;
    for color in [Color::White, Color::Black] {
        for piece in PieceType::ALL {
            phase += board.pieces(color, piece).count_ones() as i32 * PHASE_VALUES[piece.index()];
        }
    }
    phase.min(PHASE_MAX)
}

fn material_placement(board: &Board) -> Score {
    let mut total = Score::default();
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        for piece in PieceType::ALL {
            let mut bitboard = board.pieces(color, piece);
            while bitboard != 0 {
                let square = pop_lsb(&mut bitboard);
                total.mg += (MG_PIECE_VALUES[piece.index()]
                    + mg_position_value(piece, color, square))
                    * sign;
                total.eg += (EG_PIECE_VALUES[piece.index()]
                    + eg_position_value(piece, color, square))
                    * sign;
            }
        }
    }
    total
}

fn attack_map(piece: PieceType, color: Color, square: Square, occupancy: Bitboard) -> Bitboard {
    match piece {
        PieceType::Pawn => attacks::pawn_attacks(color, square),
        PieceType::Knight => attacks::knight_attacks(square),
        PieceType::Bishop => attacks::bishop_attacks(square, occupancy),
        PieceType::Rook => attacks::rook_attacks(square, occupancy),
        PieceType::Queen => attacks::queen_attacks(square, occupancy),
        PieceType::King => attacks::king_attacks(square),
    }
}

fn pawn_shield_mask(color: Color, king: Square) -> Bitboard {
    let shield_rank = match color {
        Color::White => rank_of(king).checked_add(1),
        Color::Black => rank_of(king).checked_sub(1),
    };
    let Some(rank) = shield_rank else {
        return 0;
    };

    let file = file_of(king) as i8;
    let mut mask = 0;
    for df in -1..=1 {
        let shield_file = file + df;
        if (0..=7).contains(&shield_file) {
            mask |= square_bb(make_square(shield_file as u8, rank));
        }
    }
    mask
}

fn king_ring_pressure(board: &Board, attacker: Color, ring: Bitboard) -> i32 {
    let mut pressure = 0;
    let occupancy = board.occupied();
    for piece in PieceType::ALL {
        let weight = KING_RING_ATTACK_MG[piece.index()];
        if weight == 0 {
            continue;
        }
        let mut bitboard = board.pieces(attacker, piece);
        while bitboard != 0 {
            let square = pop_lsb(&mut bitboard);
            let attacked_ring = attack_map(piece, attacker, square, occupancy) & ring;
            pressure += attacked_ring.count_ones() as i32 * weight;
        }
    }
    pressure
}

fn king_safety(board: &Board) -> Score {
    let mut total = Score::default();
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let king = board.king_square(color);
        let shield = (pawn_shield_mask(color, king) & board.pieces(color, PieceType::Pawn))
            .count_ones() as i32
            * KING_SHIELD_MG;
        let pressure = king_ring_pressure(board, color.opponent(), attacks::king_attacks(king));
        total.mg += (shield - pressure) * sign;
    }
    total
}

/// Mobility: each knight, bishop, rook, and queen scores its count of attack
/// squares not blocked by a friendly piece, weighted per piece type.
fn mobility(board: &Board) -> Score {
    let mut total = Score::default();
    let occupancy = board.occupied();
    for color in [Color::White, Color::Black] {
        let sign = if color == Color::White { 1 } else { -1 };
        let mut friendly: Bitboard = 0;
        for piece in PieceType::ALL {
            friendly |= board.pieces(color, piece);
        }
        for piece in [
            PieceType::Knight,
            PieceType::Bishop,
            PieceType::Rook,
            PieceType::Queen,
        ] {
            let mut bitboard = board.pieces(color, piece);
            while bitboard != 0 {
                let square = pop_lsb(&mut bitboard);
                let available =
                    (attack_map(piece, color, square, occupancy) & !friendly).count_ones() as i32;
                total.mg += available * MOBILITY_MG[piece.index()] * sign;
                total.eg += available * MOBILITY_EG[piece.index()] * sign;
            }
        }
    }
    total
}

/// Absolute (white-positive) evaluation: tapered material plus piece-square bonus.
pub fn evaluate(board: &Board) -> i32 {
    let mut total = material_placement(board);
    let king_safety = king_safety(board);
    let mobility = mobility(board);
    total.mg += king_safety.mg + mobility.mg;
    total.eg += king_safety.eg + mobility.eg;
    total.tapered(game_phase(board))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn game_phase_tracks_non_pawn_material() {
        assert_eq!(game_phase(&Board::startpos()), 24);
        let bare_kings = Board::from_fen("8/8/8/4k3/8/8/4K3/8 w - - 0 1").unwrap();
        assert_eq!(game_phase(&bare_kings), 0);
    }

    #[test]
    fn start_position_evaluates_to_zero() {
        assert_eq!(evaluate(&Board::startpos()), 0);
    }

    #[test]
    fn color_mirror_negates_evaluation() {
        let white_knight = Board::from_fen("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1").unwrap();
        let black_knight = Board::from_fen("4k3/8/8/3n4/8/8/8/4K3 w - - 0 1").unwrap();

        assert_eq!(evaluate(&black_knight), -evaluate(&white_knight));
    }

    #[test]
    fn tapered_evaluation_uses_pesto_material_and_position() {
        let board = Board::from_fen("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1").unwrap();

        assert_eq!(material_placement(&board).tapered(game_phase(&board)), 307);
    }

    #[test]
    fn mobility_rewards_the_freer_side() {
        let central = Board::from_fen("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1").unwrap();
        let cornered = Board::from_fen("4k3/8/8/8/8/8/8/N3K3 w - - 0 1").unwrap();

        assert!(mobility(&central).mg > mobility(&cornered).mg);
    }

    #[test]
    fn mobility_is_symmetric_at_the_start() {
        assert_eq!(mobility(&Board::startpos()), Score::default());
    }

    #[test]
    fn king_safety_rewards_pawn_shield() {
        let sheltered = Board::from_fen("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1").unwrap();
        let exposed = Board::from_fen("6k1/8/8/8/5PPP/8/8/6K1 w - - 0 1").unwrap();

        assert!(king_safety(&sheltered).mg > king_safety(&exposed).mg);
        assert_eq!(king_safety(&sheltered).eg, 0);
    }

    #[test]
    fn king_safety_penalizes_attacks_on_king_ring() {
        let sheltered = Board::from_fen("6k1/8/8/8/8/8/5PPP/6K1 w - - 0 1").unwrap();
        let attacked = Board::from_fen("6k1/8/8/8/8/8/5PPP/r5K1 w - - 0 1").unwrap();

        assert!(king_safety(&attacked).mg < king_safety(&sheltered).mg);
    }
}
