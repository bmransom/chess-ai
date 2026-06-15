//! Attack generation: precomputed leaper tables (knight, king, pawn) and magic
//! bitboards for the sliders (bishop, rook, queen).
//!
//! Magic numbers are searched once at startup with a fixed-seed PRNG, so the
//! tables are deterministic. The on-the-fly ray generator that fills the magic
//! tables doubles as a reference the tests check the magic lookups against.

use std::sync::OnceLock;

use crate::board::Board;
use crate::types::{file_of, make_square, rank_of, square_bb, Bitboard, Color, PieceType, Square};
use crate::zobrist::SplitMix64;

const ROOK_DELTAS: [(i8, i8); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];
const BISHOP_DELTAS: [(i8, i8); 4] = [(1, 1), (1, -1), (-1, 1), (-1, -1)];

struct SliderMagic {
    mask: Bitboard,
    magic: u64,
    shift: u32,
    table: Vec<Bitboard>,
}

impl SliderMagic {
    #[inline]
    fn attacks(&self, occupancy: Bitboard) -> Bitboard {
        let index = ((occupancy & self.mask).wrapping_mul(self.magic) >> self.shift) as usize;
        self.table[index]
    }
}

struct Attacks {
    knight: [Bitboard; 64],
    king: [Bitboard; 64],
    pawn: [[Bitboard; 64]; 2],
    rook: [SliderMagic; 64],
    bishop: [SliderMagic; 64],
}

static ATTACKS: OnceLock<Attacks> = OnceLock::new();

fn tables() -> &'static Attacks {
    ATTACKS.get_or_init(|| {
        let mut rng = SplitMix64::new(0xF00D_CAFE_1234_5678);
        let rook = std::array::from_fn(|square| {
            find_magic(
                square as Square,
                &ROOK_DELTAS,
                slider_mask(square as Square, &ROOK_DELTAS),
                &mut rng,
            )
        });
        let bishop = std::array::from_fn(|square| {
            find_magic(
                square as Square,
                &BISHOP_DELTAS,
                slider_mask(square as Square, &BISHOP_DELTAS),
                &mut rng,
            )
        });
        Attacks {
            knight: leaper_table(&KNIGHT_DELTAS),
            king: leaper_table(&KING_DELTAS),
            pawn: [pawn_table(Color::White), pawn_table(Color::Black)],
            rook,
            bishop,
        }
    })
}

const KNIGHT_DELTAS: [(i8, i8); 8] = [
    (1, 2),
    (2, 1),
    (2, -1),
    (1, -2),
    (-1, -2),
    (-2, -1),
    (-2, 1),
    (-1, 2),
];

const KING_DELTAS: [(i8, i8); 8] = [
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
];

fn leaper_table(deltas: &[(i8, i8)]) -> [Bitboard; 64] {
    std::array::from_fn(|square| {
        let file = file_of(square as Square) as i8;
        let rank = rank_of(square as Square) as i8;
        let mut bitboard = 0u64;
        for &(df, dr) in deltas {
            let (nf, nr) = (file + df, rank + dr);
            if (0..=7).contains(&nf) && (0..=7).contains(&nr) {
                bitboard |= square_bb(make_square(nf as u8, nr as u8));
            }
        }
        bitboard
    })
}

fn pawn_table(color: Color) -> [Bitboard; 64] {
    let forward: i8 = if color == Color::White { 1 } else { -1 };
    std::array::from_fn(|square| {
        let file = file_of(square as Square) as i8;
        let rank = rank_of(square as Square) as i8;
        let mut bitboard = 0u64;
        for df in [-1, 1] {
            let (nf, nr) = (file + df, rank + forward);
            if (0..=7).contains(&nf) && (0..=7).contains(&nr) {
                bitboard |= square_bb(make_square(nf as u8, nr as u8));
            }
        }
        bitboard
    })
}

/// All squares a slider on `square` attacks given `occupancy`, walking each ray
/// until it hits an occupied square (inclusive). Reference generator used to
/// build the magic tables.
fn slider_attacks_on_the_fly(square: Square, occupancy: Bitboard, deltas: &[(i8, i8)]) -> Bitboard {
    let file = file_of(square) as i8;
    let rank = rank_of(square) as i8;
    let mut attacks = 0u64;
    for &(df, dr) in deltas {
        let (mut f, mut r) = (file + df, rank + dr);
        while (0..=7).contains(&f) && (0..=7).contains(&r) {
            let target = make_square(f as u8, r as u8);
            attacks |= square_bb(target);
            if occupancy & square_bb(target) != 0 {
                break;
            }
            f += df;
            r += dr;
        }
    }
    attacks
}

/// The relevant-occupancy mask for a slider: ray squares excluding the board
/// edges (a blocker on the edge never changes the attack set).
fn slider_mask(square: Square, deltas: &[(i8, i8)]) -> Bitboard {
    let file = file_of(square) as i8;
    let rank = rank_of(square) as i8;
    let mut mask = 0u64;
    for &(df, dr) in deltas {
        let (mut f, mut r) = (file + df, rank + dr);
        while (0..=7).contains(&(f + df)) && (0..=7).contains(&(r + dr)) {
            mask |= square_bb(make_square(f as u8, r as u8));
            f += df;
            r += dr;
        }
    }
    mask
}

fn find_magic(
    square: Square,
    deltas: &[(i8, i8)],
    mask: Bitboard,
    rng: &mut SplitMix64,
) -> SliderMagic {
    let relevant_bits = mask.count_ones();
    let size = 1usize << relevant_bits;
    let shift = 64 - relevant_bits;

    let mut blockers = vec![0u64; size];
    let mut references = vec![0u64; size];
    let mut subset = 0u64;
    for index in 0..size {
        blockers[index] = subset;
        references[index] = slider_attacks_on_the_fly(square, subset, deltas);
        subset = subset.wrapping_sub(mask) & mask;
    }

    loop {
        let magic = rng.next() & rng.next() & rng.next();
        if (mask.wrapping_mul(magic) & 0xFF00_0000_0000_0000).count_ones() < 6 {
            continue;
        }
        let mut table = vec![u64::MAX; size];
        let mut collision = false;
        for index in 0..size {
            let slot = ((blockers[index].wrapping_mul(magic)) >> shift) as usize;
            if table[slot] == u64::MAX {
                table[slot] = references[index];
            } else if table[slot] != references[index] {
                collision = true;
                break;
            }
        }
        if !collision {
            return SliderMagic {
                mask,
                magic,
                shift,
                table,
            };
        }
    }
}

#[inline]
pub fn knight_attacks(square: Square) -> Bitboard {
    tables().knight[square as usize]
}

#[inline]
pub fn king_attacks(square: Square) -> Bitboard {
    tables().king[square as usize]
}

#[inline]
pub fn pawn_attacks(color: Color, square: Square) -> Bitboard {
    tables().pawn[color.index()][square as usize]
}

#[inline]
pub fn bishop_attacks(square: Square, occupancy: Bitboard) -> Bitboard {
    tables().bishop[square as usize].attacks(occupancy)
}

#[inline]
pub fn rook_attacks(square: Square, occupancy: Bitboard) -> Bitboard {
    tables().rook[square as usize].attacks(occupancy)
}

#[inline]
pub fn queen_attacks(square: Square, occupancy: Bitboard) -> Bitboard {
    bishop_attacks(square, occupancy) | rook_attacks(square, occupancy)
}

/// Is `square` attacked by any piece of color `by`?
pub fn is_square_attacked(board: &Board, square: Square, by: Color) -> bool {
    // A `by` pawn attacks `square` from where the opposite-colored pawn on
    // `square` would attack — hence `by.opponent()` here.
    if pawn_attacks(by.opponent(), square) & board.pieces(by, PieceType::Pawn) != 0 {
        return true;
    }
    if knight_attacks(square) & board.pieces(by, PieceType::Knight) != 0 {
        return true;
    }
    if king_attacks(square) & board.pieces(by, PieceType::King) != 0 {
        return true;
    }
    let occupancy = board.occupied();
    let diagonal = board.pieces(by, PieceType::Bishop) | board.pieces(by, PieceType::Queen);
    if bishop_attacks(square, occupancy) & diagonal != 0 {
        return true;
    }
    let orthogonal = board.pieces(by, PieceType::Rook) | board.pieces(by, PieceType::Queen);
    if rook_attacks(square, occupancy) & orthogonal != 0 {
        return true;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn magic_lookup_matches_on_the_fly() {
        let mut rng = SplitMix64::new(7);
        for square in 0u8..64 {
            for _ in 0..64 {
                let occupancy = rng.next() & rng.next();
                assert_eq!(
                    rook_attacks(square, occupancy),
                    slider_attacks_on_the_fly(square, occupancy, &ROOK_DELTAS),
                    "rook on {square}"
                );
                assert_eq!(
                    bishop_attacks(square, occupancy),
                    slider_attacks_on_the_fly(square, occupancy, &BISHOP_DELTAS),
                    "bishop on {square}"
                );
            }
        }
    }

    #[test]
    fn knight_in_a_corner_has_two_moves() {
        assert_eq!(knight_attacks(0).count_ones(), 2);
    }
}
