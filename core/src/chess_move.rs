//! Move — one move in UCI long algebraic notation, packed into 16 bits.
//!
//! Layout (Chess Programming Wiki "Encoding Moves"): bits 0–5 the from square,
//! bits 6–11 the to square, bits 12–15 a flag. Flag bit 3 marks a promotion and
//! bit 2 marks a capture, so `is_capture` / `is_promotion` are single-bit tests.

use crate::types::{square_from_uci, square_to_uci, PieceType, Square};

pub mod flag {
    pub const QUIET: u16 = 0;
    pub const DOUBLE_PAWN_PUSH: u16 = 1;
    pub const KING_CASTLE: u16 = 2;
    pub const QUEEN_CASTLE: u16 = 3;
    pub const CAPTURE: u16 = 4;
    pub const EN_PASSANT: u16 = 5;
    pub const PROMO_KNIGHT: u16 = 8;
    pub const PROMO_BISHOP: u16 = 9;
    pub const PROMO_ROOK: u16 = 10;
    pub const PROMO_QUEEN: u16 = 11;
    pub const PROMO_KNIGHT_CAPTURE: u16 = 12;
    pub const PROMO_BISHOP_CAPTURE: u16 = 13;
    pub const PROMO_ROOK_CAPTURE: u16 = 14;
    pub const PROMO_QUEEN_CAPTURE: u16 = 15;

    pub const CAPTURE_BIT: u16 = 4;
    pub const PROMOTION_BIT: u16 = 8;
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Move(pub u16);

impl Move {
    #[inline]
    pub fn new(from: Square, to: Square, flag: u16) -> Move {
        Move((from as u16) | ((to as u16) << 6) | (flag << 12))
    }

    #[inline]
    pub fn from(self) -> Square {
        (self.0 & 0x3F) as Square
    }

    #[inline]
    pub fn to(self) -> Square {
        ((self.0 >> 6) & 0x3F) as Square
    }

    #[inline]
    pub fn flag(self) -> u16 {
        self.0 >> 12
    }

    #[inline]
    pub fn is_capture(self) -> bool {
        self.flag() & flag::CAPTURE_BIT != 0
    }

    #[inline]
    pub fn is_promotion(self) -> bool {
        self.flag() & flag::PROMOTION_BIT != 0
    }

    #[inline]
    pub fn is_en_passant(self) -> bool {
        self.flag() == flag::EN_PASSANT
    }

    #[inline]
    pub fn is_king_castle(self) -> bool {
        self.flag() == flag::KING_CASTLE
    }

    #[inline]
    pub fn is_queen_castle(self) -> bool {
        self.flag() == flag::QUEEN_CASTLE
    }

    #[inline]
    pub fn is_double_pawn_push(self) -> bool {
        self.flag() == flag::DOUBLE_PAWN_PUSH
    }

    /// The piece a pawn promotes to, if this move is a promotion.
    pub fn promotion(self) -> Option<PieceType> {
        if !self.is_promotion() {
            return None;
        }
        Some(match self.flag() & 0b11 {
            0 => PieceType::Knight,
            1 => PieceType::Bishop,
            2 => PieceType::Rook,
            _ => PieceType::Queen,
        })
    }

    /// UCI long algebraic notation, e.g. `e2e4` or `e7e8q`.
    pub fn to_uci(self) -> String {
        let mut text = square_to_uci(self.from());
        text.push_str(&square_to_uci(self.to()));
        if let Some(promotion) = self.promotion() {
            text.push(promotion.to_char());
        }
        text
    }
}

/// Parse the from/to/promotion of a UCI move string. The flag is resolved
/// against the position when the move is matched to a legal move, so this
/// returns only the raw fields.
pub fn parse_uci(text: &str) -> Option<(Square, Square, Option<PieceType>)> {
    if text.len() < 4 {
        return None;
    }
    let from = square_from_uci(&text[0..2])?;
    let to = square_from_uci(&text[2..4])?;
    let promotion = match text.as_bytes().get(4) {
        None => None,
        Some(&letter) => Some(PieceType::from_char(letter as char)?),
    };
    Some((from, to, promotion))
}
