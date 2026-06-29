//! NNUE evaluation — a borrowed 768 perspective network read inside the search.
//!
//! Architecture: `(768 -> 256)x2 -> 1`. A feature is a `(piece type, color,
//! square)` triple — 6 x 2 x 64 = 768 binary inputs. Two accumulators share one
//! feature transformer: one from the side-to-move's orientation, one from the
//! opponent's (the board vertically mirrored). A squared clipped-ReLU activates
//! each, the two concatenate, and a single output neuron produces a score.
//!
//! Integer-quantized: feature weights scale by `QA`, output weights by `QB`,
//! and the network output dequantizes to centipawns by `SCALE`. The 768
//! perspective net, the squared clipped-ReLU, and these constants follow the
//! `bullet` trainer's conventions; see `knowledge/glossary.md`.
//!
//! The accumulator supports incremental update — `add_piece` / `remove_piece`
//! adjust both perspectives by a single weight column, so make/unmake need no full
//! recompute. The search maintains it across make/unmake via `apply_move`;
//! `evaluate` reads the maintained accumulator, falling back to a full refresh
//! where none is initialized (the decision-tree scout and the flag-off engine).

use crate::board::Board;
use crate::chess_move::Move;
use crate::types::{pop_lsb, Color, PieceType, Square, NUM_PIECE_TYPES};

/// Input features: piece type x color x square.
pub const INPUT: usize = 768;
/// Accumulator width per perspective.
pub const HIDDEN: usize = 256;
/// Feature-transformer quantization scale (accumulator weights and bias).
const QA: i32 = 255;
/// Output-layer quantization scale (output weights).
const QB: i32 = 64;
/// Dequantization scale: network output to centipawns.
const SCALE: i32 = 400;
/// The evaluation is clamped to `±EVAL_LIMIT` centipawns — far above any real
/// material score, yet well below the search's mate threshold, so no network
/// output is ever mistaken for a forced mate.
const EVAL_LIMIT: i32 = 30_000;

/// File magic: brandobot network, format 1.
const MAGIC: [u8; 4] = *b"BNN1";
/// Feature-transformer weight count (feature-major: feature `f` owns `[f*HIDDEN..]`).
const FEATURE_WEIGHTS: usize = INPUT * HIDDEN;
/// Output weight count: one block per perspective.
const OUTPUT_WEIGHTS: usize = 2 * HIDDEN;
/// Header: magic(4) + input(4) + hidden(4) + qa(4) + qb(4) + scale(4).
const HEADER_LEN: usize = 24;
/// Total network file length, in bytes.
const FILE_LEN: usize = HEADER_LEN + (FEATURE_WEIGHTS + HIDDEN + OUTPUT_WEIGHTS) * 2 + 4;

/// A quantized 768 perspective network.
pub struct Network {
    /// Feature-transformer weights, feature-major: `[feature * HIDDEN + h]`.
    feature_weights: Vec<i16>,
    /// Feature-transformer bias, one per accumulator unit.
    feature_bias: Vec<i16>,
    /// Output weights: the first `HIDDEN` for the side-to-move accumulator, the
    /// next `HIDDEN` for the opponent's.
    output_weights: Vec<i16>,
    /// Output bias, at the `QA * QB` scale.
    output_bias: i32,
}

/// The two perspective accumulators — White's and Black's — each the
/// feature-transformer bias plus the column of every active feature from that
/// perspective's orientation. A piece add or remove updates both by a single
/// weight column, so make/unmake need no full recompute.
#[derive(Clone, PartialEq, Eq, Debug)]
pub(crate) struct Accumulator {
    white: [i32; HIDDEN],
    black: [i32; HIDDEN],
}

/// The 768 feature index for a piece, from `perspective`'s orientation. The
/// perspective side's pieces fill the first block; the opponent's the second.
/// Black's perspective mirrors the board vertically (`sq ^ 56`).
#[inline]
fn feature_index(
    perspective: Color,
    piece_color: Color,
    piece_type: PieceType,
    square: Square,
) -> usize {
    let color_block = if piece_color == perspective { 0 } else { 1 };
    let square = if perspective == Color::White {
        square
    } else {
        square ^ 56
    } as usize;
    color_block * (NUM_PIECE_TYPES * 64) + piece_type.index() * 64 + square
}

/// Squared clipped-ReLU: clamp to `[0, QA]`, then square.
#[inline]
fn screlu(value: i32) -> i32 {
    let clamped = value.clamp(0, QA);
    clamped * clamped
}

impl Network {
    /// Parse a quantized network from its little-endian byte image. Rejects a
    /// file whose magic, dimensions, or quantization scales do not match this
    /// compiled architecture, or whose length is wrong.
    pub fn from_bytes(bytes: &[u8]) -> Result<Network, String> {
        if bytes.len() != FILE_LEN {
            return Err(format!(
                "network file is {} bytes, expected {FILE_LEN}",
                bytes.len()
            ));
        }
        if bytes[0..4] != MAGIC {
            return Err("network file has a bad magic header".to_string());
        }
        let header = |at: usize| {
            i32::from_le_bytes([bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]])
        };
        let checks = [
            ("input dimension", header(4), INPUT as i32),
            ("hidden dimension", header(8), HIDDEN as i32),
            ("QA", header(12), QA),
            ("QB", header(16), QB),
            ("SCALE", header(20), SCALE),
        ];
        for (name, found, expected) in checks {
            if found != expected {
                return Err(format!("network {name} is {found}, expected {expected}"));
            }
        }

        let mut cursor = HEADER_LEN;
        let mut take_i16 = |count: usize| -> Vec<i16> {
            let values = bytes[cursor..cursor + count * 2]
                .chunks_exact(2)
                .map(|pair| i16::from_le_bytes([pair[0], pair[1]]))
                .collect();
            cursor += count * 2;
            values
        };
        let feature_weights = take_i16(FEATURE_WEIGHTS);
        let feature_bias = take_i16(HIDDEN);
        let output_weights = take_i16(OUTPUT_WEIGHTS);
        let output_bias = i32::from_le_bytes([
            bytes[cursor],
            bytes[cursor + 1],
            bytes[cursor + 2],
            bytes[cursor + 3],
        ]);

        Ok(Network {
            feature_weights,
            feature_bias,
            output_weights,
            output_bias,
        })
    }

    /// Serialize to the little-endian byte image `from_bytes` reads. Test-only
    /// until the Wave 2 trainer-export converter consumes it in production.
    #[cfg(test)]
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(FILE_LEN);
        bytes.extend_from_slice(&MAGIC);
        for value in [INPUT as i32, HIDDEN as i32, QA, QB, SCALE] {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        for weight in self
            .feature_weights
            .iter()
            .chain(&self.feature_bias)
            .chain(&self.output_weights)
        {
            bytes.extend_from_slice(&weight.to_le_bytes());
        }
        bytes.extend_from_slice(&self.output_bias.to_le_bytes());
        bytes
    }

    /// A fresh accumulator built from every piece — the full refresh. The
    /// incremental path (`add_piece` / `remove_piece`) must agree with this for
    /// any reachable position; the equivalence is the fast path's correctness gate.
    pub(crate) fn fresh_accumulator(&self, board: &Board) -> Accumulator {
        let mut bias = [0i32; HIDDEN];
        for (unit, value) in bias.iter_mut().zip(&self.feature_bias) {
            *unit = *value as i32;
        }
        let mut accumulator = Accumulator {
            white: bias,
            black: bias,
        };
        for &color in &[Color::White, Color::Black] {
            for &piece_type in &PieceType::ALL {
                let mut pieces = board.pieces(color, piece_type);
                while pieces != 0 {
                    let square = pop_lsb(&mut pieces);
                    self.add_piece(&mut accumulator, color, piece_type, square);
                }
            }
        }
        accumulator
    }

    /// Add a piece's feature column to both perspectives.
    fn add_piece(&self, acc: &mut Accumulator, color: Color, piece: PieceType, square: Square) {
        self.update_piece(acc, color, piece, square, 1);
    }

    /// Remove a piece's feature column from both perspectives — the exact inverse
    /// of `add_piece`, so unmake restores the accumulator bit-for-bit.
    fn remove_piece(&self, acc: &mut Accumulator, color: Color, piece: PieceType, square: Square) {
        self.update_piece(acc, color, piece, square, -1);
    }

    fn update_piece(
        &self,
        acc: &mut Accumulator,
        color: Color,
        piece: PieceType,
        square: Square,
        sign: i32,
    ) {
        let white = feature_index(Color::White, color, piece, square) * HIDDEN;
        for (unit, weight) in acc
            .white
            .iter_mut()
            .zip(&self.feature_weights[white..white + HIDDEN])
        {
            *unit += sign * *weight as i32;
        }
        let black = feature_index(Color::Black, color, piece, square) * HIDDEN;
        for (unit, weight) in acc
            .black
            .iter_mut()
            .zip(&self.feature_weights[black..black + HIDDEN])
        {
            *unit += sign * *weight as i32;
        }
    }

    /// Update both accumulators for `mv`, mirroring `Board::make_move`'s piece
    /// changes — capture, en passant, promotion, and castling each shift the same
    /// pieces the board does, so the result equals a full refresh of the position
    /// after the move. `board` is the position *before* `mv`. The search calls
    /// this around its make/unmake to maintain the accumulator incrementally.
    pub(crate) fn apply_move(&self, acc: &mut Accumulator, board: &Board, mv: Move) {
        let us = board.side_to_move();
        let them = us.opponent();
        let from = mv.from();
        let to = mv.to();
        let moving = board.piece_at(from).expect("from holds a piece").piece_type;

        if mv.is_en_passant() {
            let captured = if us == Color::White { to - 8 } else { to + 8 };
            self.remove_piece(acc, them, PieceType::Pawn, captured);
        } else if mv.is_capture() {
            let victim = board.piece_at(to).expect("capture has a target");
            self.remove_piece(acc, victim.color, victim.piece_type, to);
        }

        match mv.promotion() {
            Some(promotion) => {
                self.remove_piece(acc, us, PieceType::Pawn, from);
                self.add_piece(acc, us, promotion, to);
            }
            None => {
                self.remove_piece(acc, us, moving, from);
                self.add_piece(acc, us, moving, to);
            }
        }

        if mv.is_king_castle() {
            let (rook_from, rook_to) = if us == Color::White { (7, 5) } else { (63, 61) };
            self.remove_piece(acc, us, PieceType::Rook, rook_from);
            self.add_piece(acc, us, PieceType::Rook, rook_to);
        } else if mv.is_queen_castle() {
            let (rook_from, rook_to) = if us == Color::White { (0, 3) } else { (56, 59) };
            self.remove_piece(acc, us, PieceType::Rook, rook_from);
            self.add_piece(acc, us, PieceType::Rook, rook_to);
        }
    }

    /// The white-positive evaluation from a built accumulator. The network output
    /// is side-to-move relative; this negates it for Black so it matches the
    /// hand-written evaluation's sign, a drop-in at the search seam.
    pub(crate) fn evaluate_accumulator(&self, acc: &Accumulator, side: Color) -> i32 {
        let (stm, nstm) = match side {
            Color::White => (&acc.white, &acc.black),
            Color::Black => (&acc.black, &acc.white),
        };
        let (stm_weights, nstm_weights) = self.output_weights.split_at(HIDDEN);
        let mut sum: i64 = 0;
        for (unit, weight) in stm.iter().zip(stm_weights) {
            sum += screlu(*unit) as i64 * *weight as i64;
        }
        for (unit, weight) in nstm.iter().zip(nstm_weights) {
            sum += screlu(*unit) as i64 * *weight as i64;
        }

        // The squared activation carries an extra QA factor; divide it out, add
        // the bias at the QA*QB scale, then dequantize to centipawns.
        let activated = sum / QA as i64 + self.output_bias as i64;
        let relative = (activated * SCALE as i64) / (QA as i64 * QB as i64);
        // Clamp well below the search's mate threshold so no network output is
        // ever misread as a forced mate.
        let relative = relative.clamp(-(EVAL_LIMIT as i64), EVAL_LIMIT as i64) as i32;
        if side == Color::White {
            relative
        } else {
            -relative
        }
    }

    /// The white-positive static evaluation in centipawns, by full refresh.
    pub fn evaluate(&self, board: &Board) -> i32 {
        let accumulator = self.fresh_accumulator(board);
        self.evaluate_accumulator(&accumulator, board.side_to_move())
    }
}

/// A deterministic, non-trivial network for tests — varied small weights so the
/// equivalence and symmetry checks are meaningful (all-zero would pass them
/// vacuously). Crate-visible so the search tests can load a net too.
#[cfg(test)]
pub(crate) fn test_network() -> Network {
    let pattern =
        |index: usize| ((index as u64).wrapping_mul(2_654_435_761) >> 8).rem_euclid(17) as i16 - 8;
    Network {
        feature_weights: (0..FEATURE_WEIGHTS).map(pattern).collect(),
        feature_bias: (0..HIDDEN).map(|i| pattern(i + 7)).collect(),
        output_weights: (0..OUTPUT_WEIGHTS).map(|i| pattern(i + 3)).collect(),
        output_bias: 25,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::movegen::generate_legal;
    use crate::types::make_square;

    fn deterministic() -> Network {
        test_network()
    }

    #[test]
    fn start_position_evaluates_to_a_bounded_score() {
        let score = deterministic().evaluate(&Board::startpos());
        assert!(score.abs() < 30_000, "score {score} is out of sane range");
    }

    #[test]
    fn color_mirror_swapping_side_to_move_negates() {
        // White knight d4, white to move; and its vertical-flip + color-swap with
        // Black to move. The perspective design makes the white-positive score
        // antisymmetric, independent of the weights.
        let net = deterministic();
        let position = Board::from_fen("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1").unwrap();
        let mirror = Board::from_fen("4k3/8/8/3n4/8/8/8/4K3 b - - 0 1").unwrap();

        assert_eq!(net.evaluate(&mirror), -net.evaluate(&position));
    }

    #[test]
    fn incremental_add_remove_matches_a_full_refresh() {
        // Move a white knight d4 -> f5 by remove + add; the incrementally updated
        // accumulator must equal a fresh accumulator of the knight-on-f5 position.
        let net = deterministic();
        let before = Board::from_fen("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1").unwrap();
        let after = Board::from_fen("4k3/8/8/5N2/8/8/8/4K3 w - - 0 1").unwrap();

        let mut accumulator = net.fresh_accumulator(&before);
        net.remove_piece(
            &mut accumulator,
            Color::White,
            PieceType::Knight,
            make_square(3, 3),
        );
        net.add_piece(
            &mut accumulator,
            Color::White,
            PieceType::Knight,
            make_square(5, 4),
        );

        assert_eq!(accumulator, net.fresh_accumulator(&after));
    }

    #[test]
    fn add_then_remove_restores_the_accumulator() {
        // Unmake must restore the accumulator exactly: remove inverts add.
        let net = deterministic();
        let original = net.fresh_accumulator(&Board::startpos());

        let mut accumulator = original.clone();
        net.add_piece(
            &mut accumulator,
            Color::Black,
            PieceType::Rook,
            make_square(3, 3),
        );
        net.remove_piece(
            &mut accumulator,
            Color::Black,
            PieceType::Rook,
            make_square(3, 3),
        );

        assert_eq!(accumulator, original);
    }

    /// Apply `uci` to a fresh accumulator via the incremental `apply_move`, then
    /// assert it equals a full refresh of the resulting position.
    fn assert_incremental(net: &Network, fen: &str, uci: &str) {
        let mut board = Board::from_fen(fen).unwrap();
        let mv = generate_legal(&mut board)
            .iter()
            .copied()
            .find(|candidate| candidate.to_uci() == uci)
            .unwrap_or_else(|| panic!("{uci} is not legal in {fen}"));

        let mut accumulator = net.fresh_accumulator(&board);
        net.apply_move(&mut accumulator, &board, mv);
        board.make_move(mv);

        assert_eq!(
            accumulator,
            net.fresh_accumulator(&board),
            "after {uci} from {fen}"
        );
    }

    #[test]
    fn apply_move_matches_a_full_refresh_for_every_move_type() {
        let net = deterministic();
        // quiet, capture, en passant, both castles, promotion, promotion-capture.
        assert_incremental(
            &net,
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "e2e4",
        );
        assert_incremental(
            &net,
            "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2",
            "e4d5",
        );
        assert_incremental(
            &net,
            "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3",
            "e5d6",
        );
        assert_incremental(
            &net,
            "rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
            "e1g1",
        );
        assert_incremental(
            &net,
            "r3k2r/pppqbppp/2npbn2/4p3/4P3/2NPBN2/PPPQBPPP/R3K2R w KQkq - 0 1",
            "e1c1",
        );
        assert_incremental(&net, "4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q");
        assert_incremental(&net, "1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7b8q");
    }

    #[test]
    fn apply_move_stays_consistent_through_a_game() {
        // A Ruy Lopez line — quiet moves, two captures, and both sides castling —
        // applied incrementally must match a full refresh at every ply.
        let net = deterministic();
        let mut board = Board::startpos();
        let mut accumulator = net.fresh_accumulator(&board);
        for uci in [
            "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5c6", "d7c6", "e1g1", "f8d6", "d2d4",
            "e5d4", "f3d4", "g8f6", "b1c3", "e8g8",
        ] {
            let mv = generate_legal(&mut board)
                .iter()
                .copied()
                .find(|candidate| candidate.to_uci() == uci)
                .unwrap_or_else(|| panic!("{uci} is not legal"));
            net.apply_move(&mut accumulator, &board, mv);
            board.make_move(mv);
            assert_eq!(accumulator, net.fresh_accumulator(&board), "after {uci}");
        }
    }

    #[test]
    fn output_is_clamped_below_the_mate_threshold() {
        let mut net = deterministic();
        net.output_bias = 10_000_000; // forces the raw score past the limit
        assert_eq!(net.evaluate(&Board::startpos()), EVAL_LIMIT);
    }

    #[test]
    fn to_bytes_round_trips_through_from_bytes() {
        let net = deterministic();
        let loaded = Network::from_bytes(&net.to_bytes()).unwrap();

        let board =
            Board::from_fen("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1")
                .unwrap();
        assert_eq!(loaded.evaluate(&board), net.evaluate(&board));
    }

    #[test]
    fn from_bytes_rejects_a_bad_magic() {
        let mut bytes = deterministic().to_bytes();
        bytes[0] = b'X';
        assert!(Network::from_bytes(&bytes).is_err());
    }

    #[test]
    fn from_bytes_rejects_a_wrong_dimension() {
        let mut bytes = deterministic().to_bytes();
        bytes[4..8].copy_from_slice(&512i32.to_le_bytes()); // input dimension
        assert!(Network::from_bytes(&bytes).is_err());
    }

    #[test]
    fn from_bytes_rejects_a_truncated_file() {
        let mut bytes = deterministic().to_bytes();
        bytes.truncate(bytes.len() - 1);
        assert!(Network::from_bytes(&bytes).is_err());
    }
}
