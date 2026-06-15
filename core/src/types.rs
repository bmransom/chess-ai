//! Core value types: colors, piece kinds, squares, and bitboard helpers.
//!
//! Squares use Little-Endian Rank-File mapping: a1 = 0, h1 = 7, a8 = 56,
//! h8 = 63. Rank = square / 8, file = square % 8. White advances toward higher
//! ranks (north, +8).

pub type Bitboard = u64;
pub type Square = u8;

pub const NUM_SQUARES: usize = 64;
pub const NUM_PIECE_TYPES: usize = 6;
pub const NUM_COLORS: usize = 2;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum Color {
    White = 0,
    Black = 1,
}

impl Color {
    #[inline]
    pub const fn opponent(self) -> Color {
        match self {
            Color::White => Color::Black,
            Color::Black => Color::White,
        }
    }

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum PieceType {
    Pawn = 0,
    Knight = 1,
    Bishop = 2,
    Rook = 3,
    Queen = 4,
    King = 5,
}

impl PieceType {
    pub const ALL: [PieceType; NUM_PIECE_TYPES] = [
        PieceType::Pawn,
        PieceType::Knight,
        PieceType::Bishop,
        PieceType::Rook,
        PieceType::Queen,
        PieceType::King,
    ];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    /// The lowercase FEN letter for this piece kind.
    pub const fn to_char(self) -> char {
        match self {
            PieceType::Pawn => 'p',
            PieceType::Knight => 'n',
            PieceType::Bishop => 'b',
            PieceType::Rook => 'r',
            PieceType::Queen => 'q',
            PieceType::King => 'k',
        }
    }

    pub const fn from_char(letter: char) -> Option<PieceType> {
        match letter {
            'p' => Some(PieceType::Pawn),
            'n' => Some(PieceType::Knight),
            'b' => Some(PieceType::Bishop),
            'r' => Some(PieceType::Rook),
            'q' => Some(PieceType::Queen),
            'k' => Some(PieceType::King),
            _ => None,
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Piece {
    pub color: Color,
    pub piece_type: PieceType,
}

impl Piece {
    /// The FEN letter: uppercase for white, lowercase for black.
    pub fn to_char(self) -> char {
        let letter = self.piece_type.to_char();
        match self.color {
            Color::White => letter.to_ascii_uppercase(),
            Color::Black => letter,
        }
    }
}

#[inline]
pub const fn make_square(file: u8, rank: u8) -> Square {
    rank * 8 + file
}

#[inline]
pub const fn file_of(square: Square) -> u8 {
    square % 8
}

#[inline]
pub const fn rank_of(square: Square) -> u8 {
    square / 8
}

pub fn square_to_uci(square: Square) -> String {
    let file = (b'a' + file_of(square)) as char;
    let rank = (b'1' + rank_of(square)) as char;
    format!("{file}{rank}")
}

pub fn square_from_uci(text: &str) -> Option<Square> {
    let bytes = text.as_bytes();
    if bytes.len() != 2 {
        return None;
    }
    let file = bytes[0].checked_sub(b'a')?;
    let rank = bytes[1].checked_sub(b'1')?;
    if file > 7 || rank > 7 {
        return None;
    }
    Some(make_square(file, rank))
}

/// A one-bit bitboard for `square`.
#[inline]
pub const fn square_bb(square: Square) -> Bitboard {
    1u64 << square
}

/// The index of the least significant set bit.
#[inline]
pub fn lsb(bitboard: Bitboard) -> Square {
    bitboard.trailing_zeros() as Square
}

/// Clear and return the least significant set bit's index.
#[inline]
pub fn pop_lsb(bitboard: &mut Bitboard) -> Square {
    let square = lsb(*bitboard);
    *bitboard &= *bitboard - 1;
    square
}
