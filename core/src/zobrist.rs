//! Zobrist hashing — the key identifying a position in the transposition table.
//!
//! Keys are generated once from a fixed seed, so hashes are stable across runs
//! (transposition-table persistence and tests depend on that). The Board keeps
//! its key incrementally; [`super::board::Board::compute_zobrist`] recomputes it
//! from scratch as a cross-check.

use std::sync::OnceLock;

use crate::types::{NUM_COLORS, NUM_PIECE_TYPES, NUM_SQUARES};

pub struct Zobrist {
    pub piece_square: [[[u64; NUM_SQUARES]; NUM_PIECE_TYPES]; NUM_COLORS],
    pub side_to_move: u64,
    /// Indexed by the 4-bit castling-rights mask.
    pub castling: [u64; 16],
    /// Indexed by the file of the en-passant square.
    pub en_passant_file: [u64; 8],
}

static ZOBRIST: OnceLock<Zobrist> = OnceLock::new();

pub fn keys() -> &'static Zobrist {
    ZOBRIST.get_or_init(Zobrist::new)
}

impl Zobrist {
    fn new() -> Zobrist {
        let mut rng = SplitMix64::new(0x0BAD_C0DE_DEAD_BEEF);
        let mut piece_square = [[[0u64; NUM_SQUARES]; NUM_PIECE_TYPES]; NUM_COLORS];
        for color in piece_square.iter_mut() {
            for piece in color.iter_mut() {
                for square in piece.iter_mut() {
                    *square = rng.next();
                }
            }
        }
        let side_to_move = rng.next();
        let mut castling = [0u64; 16];
        for value in castling.iter_mut() {
            *value = rng.next();
        }
        let mut en_passant_file = [0u64; 8];
        for value in en_passant_file.iter_mut() {
            *value = rng.next();
        }
        Zobrist {
            piece_square,
            side_to_move,
            castling,
            en_passant_file,
        }
    }
}

/// A small, fast, fully deterministic PRNG (Vigna's SplitMix64) used to seed the
/// Zobrist keys and the magic-number search.
pub struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    pub fn new(seed: u64) -> SplitMix64 {
        SplitMix64 { state: seed }
    }

    pub fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}
