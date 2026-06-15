//! Board — a chess position in bitboards, with FEN parsing/formatting and
//! make/unmake that maintains the Zobrist key incrementally.

use crate::chess_move::Move;
use crate::types::{
    file_of, make_square, square_bb, square_from_uci, square_to_uci, Bitboard, Color, Piece,
    PieceType, Square, NUM_COLORS, NUM_PIECE_TYPES,
};
use crate::zobrist::keys;

pub const STARTPOS_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

pub const CASTLE_WK: u8 = 1;
pub const CASTLE_WQ: u8 = 2;
pub const CASTLE_BK: u8 = 4;
pub const CASTLE_BQ: u8 = 8;

/// State needed to reverse a move.
#[derive(Clone, Copy)]
pub struct Undo {
    captured: Option<Piece>,
    castling_rights: u8,
    en_passant: Option<Square>,
    halfmove_clock: u16,
    zobrist: u64,
}

#[derive(Clone)]
pub struct Board {
    pieces: [[Bitboard; NUM_PIECE_TYPES]; NUM_COLORS],
    color_occupancy: [Bitboard; NUM_COLORS],
    squares: [Option<Piece>; 64],
    side_to_move: Color,
    castling_rights: u8,
    en_passant: Option<Square>,
    halfmove_clock: u16,
    fullmove_number: u16,
    zobrist: u64,
}

impl Board {
    pub fn startpos() -> Board {
        Board::from_fen(STARTPOS_FEN).expect("the start position FEN is valid")
    }

    pub fn from_fen(fen: &str) -> Result<Board, String> {
        // Lenient like python-chess: placement and side are required; castling,
        // en passant, and the clocks default when omitted.
        let fields: Vec<&str> = fen.split_whitespace().collect();
        if fields.len() < 2 {
            return Err(format!(
                "FEN needs at least placement and side, got {}",
                fields.len()
            ));
        }

        let mut board = Board {
            pieces: [[0; NUM_PIECE_TYPES]; NUM_COLORS],
            color_occupancy: [0; NUM_COLORS],
            squares: [None; 64],
            side_to_move: Color::White,
            castling_rights: 0,
            en_passant: None,
            halfmove_clock: 0,
            fullmove_number: 1,
            zobrist: 0,
        };

        let ranks: Vec<&str> = fields[0].split('/').collect();
        if ranks.len() != 8 {
            return Err(format!("FEN board needs 8 ranks, got {}", ranks.len()));
        }
        for (row, rank_text) in ranks.iter().enumerate() {
            let rank = 7 - row as u8;
            let mut file = 0u8;
            for symbol in rank_text.chars() {
                if let Some(skip) = symbol.to_digit(10) {
                    file += skip as u8;
                } else {
                    let color = if symbol.is_ascii_uppercase() {
                        Color::White
                    } else {
                        Color::Black
                    };
                    let piece_type = PieceType::from_char(symbol.to_ascii_lowercase())
                        .ok_or_else(|| format!("bad piece letter '{symbol}'"))?;
                    if file > 7 {
                        return Err(format!("rank '{rank_text}' overflows"));
                    }
                    board.add_piece(color, piece_type, make_square(file, rank));
                    file += 1;
                }
            }
        }

        board.side_to_move = match fields[1] {
            "w" => Color::White,
            "b" => Color::Black,
            other => return Err(format!("bad side to move '{other}'")),
        };

        let castling_field = fields.get(2).copied().unwrap_or("-");
        if castling_field != "-" {
            for symbol in castling_field.chars() {
                board.castling_rights |= match symbol {
                    'K' => CASTLE_WK,
                    'Q' => CASTLE_WQ,
                    'k' => CASTLE_BK,
                    'q' => CASTLE_BQ,
                    other => return Err(format!("bad castling right '{other}'")),
                };
            }
        }

        let en_passant_field = fields.get(3).copied().unwrap_or("-");
        if en_passant_field != "-" {
            board.en_passant = Some(
                square_from_uci(en_passant_field)
                    .ok_or_else(|| format!("bad ep '{en_passant_field}'"))?,
            );
        }

        if let Some(text) = fields.get(4) {
            board.halfmove_clock = text.parse().unwrap_or(0);
        }
        if let Some(text) = fields.get(5) {
            board.fullmove_number = text.parse().unwrap_or(1);
        }

        board.zobrist = board.compute_zobrist();
        Ok(board)
    }

    pub fn to_fen(&self) -> String {
        let mut placement = String::new();
        for row in 0..8 {
            let rank = 7 - row;
            let mut empty = 0;
            for file in 0..8 {
                match self.squares[make_square(file, rank) as usize] {
                    None => empty += 1,
                    Some(piece) => {
                        if empty > 0 {
                            placement.push(char::from_digit(empty, 10).unwrap());
                            empty = 0;
                        }
                        placement.push(piece.to_char());
                    }
                }
            }
            if empty > 0 {
                placement.push(char::from_digit(empty, 10).unwrap());
            }
            if row < 7 {
                placement.push('/');
            }
        }

        let side = match self.side_to_move {
            Color::White => "w",
            Color::Black => "b",
        };

        let mut castling = String::new();
        if self.castling_rights & CASTLE_WK != 0 {
            castling.push('K');
        }
        if self.castling_rights & CASTLE_WQ != 0 {
            castling.push('Q');
        }
        if self.castling_rights & CASTLE_BK != 0 {
            castling.push('k');
        }
        if self.castling_rights & CASTLE_BQ != 0 {
            castling.push('q');
        }
        if castling.is_empty() {
            castling.push('-');
        }

        let en_passant = match self.en_passant {
            Some(square) => square_to_uci(square),
            None => "-".to_string(),
        };

        format!(
            "{placement} {side} {castling} {en_passant} {} {}",
            self.halfmove_clock, self.fullmove_number
        )
    }

    pub fn compute_zobrist(&self) -> u64 {
        let z = keys();
        let mut hash = 0u64;
        for color in [Color::White, Color::Black] {
            for piece_type in PieceType::ALL {
                let mut bitboard = self.pieces[color.index()][piece_type.index()];
                while bitboard != 0 {
                    let square = bitboard.trailing_zeros() as usize;
                    hash ^= z.piece_square[color.index()][piece_type.index()][square];
                    bitboard &= bitboard - 1;
                }
            }
        }
        if self.side_to_move == Color::Black {
            hash ^= z.side_to_move;
        }
        hash ^= z.castling[self.castling_rights as usize];
        if let Some(square) = self.en_passant {
            hash ^= z.en_passant_file[file_of(square) as usize];
        }
        hash
    }

    #[inline]
    pub fn pieces(&self, color: Color, piece_type: PieceType) -> Bitboard {
        self.pieces[color.index()][piece_type.index()]
    }

    #[inline]
    pub fn occupancy(&self, color: Color) -> Bitboard {
        self.color_occupancy[color.index()]
    }

    #[inline]
    pub fn occupied(&self) -> Bitboard {
        self.color_occupancy[0] | self.color_occupancy[1]
    }

    #[inline]
    pub fn piece_at(&self, square: Square) -> Option<Piece> {
        self.squares[square as usize]
    }

    #[inline]
    pub fn side_to_move(&self) -> Color {
        self.side_to_move
    }

    #[inline]
    pub fn en_passant(&self) -> Option<Square> {
        self.en_passant
    }

    #[inline]
    pub fn castling_rights(&self) -> u8 {
        self.castling_rights
    }

    #[inline]
    pub fn zobrist(&self) -> u64 {
        self.zobrist
    }

    #[inline]
    pub fn halfmove_clock(&self) -> u16 {
        self.halfmove_clock
    }

    pub fn king_square(&self, color: Color) -> Square {
        self.pieces(color, PieceType::King).trailing_zeros() as Square
    }

    fn add_piece(&mut self, color: Color, piece_type: PieceType, square: Square) {
        let mask = square_bb(square);
        self.pieces[color.index()][piece_type.index()] |= mask;
        self.color_occupancy[color.index()] |= mask;
        self.squares[square as usize] = Some(Piece { color, piece_type });
        self.zobrist ^= keys().piece_square[color.index()][piece_type.index()][square as usize];
    }

    fn remove_piece(&mut self, color: Color, piece_type: PieceType, square: Square) {
        let mask = square_bb(square);
        self.pieces[color.index()][piece_type.index()] &= !mask;
        self.color_occupancy[color.index()] &= !mask;
        self.squares[square as usize] = None;
        self.zobrist ^= keys().piece_square[color.index()][piece_type.index()][square as usize];
    }

    fn move_piece(&mut self, color: Color, piece_type: PieceType, from: Square, to: Square) {
        let mask = square_bb(from) | square_bb(to);
        self.pieces[color.index()][piece_type.index()] ^= mask;
        self.color_occupancy[color.index()] ^= mask;
        self.squares[from as usize] = None;
        self.squares[to as usize] = Some(Piece { color, piece_type });
        let z = keys();
        self.zobrist ^= z.piece_square[color.index()][piece_type.index()][from as usize]
            ^ z.piece_square[color.index()][piece_type.index()][to as usize];
    }

    pub fn make_move(&mut self, mv: Move) -> Undo {
        let z = keys();
        let mut undo = Undo {
            captured: None,
            castling_rights: self.castling_rights,
            en_passant: self.en_passant,
            halfmove_clock: self.halfmove_clock,
            zobrist: self.zobrist,
        };

        let us = self.side_to_move;
        let them = us.opponent();
        let from = mv.from();
        let to = mv.to();
        let moving = self.squares[from as usize]
            .expect("from square holds a piece")
            .piece_type;

        if let Some(square) = self.en_passant {
            self.zobrist ^= z.en_passant_file[file_of(square) as usize];
        }
        self.en_passant = None;

        if mv.is_en_passant() {
            let captured_square = if us == Color::White { to - 8 } else { to + 8 };
            undo.captured = Some(Piece {
                color: them,
                piece_type: PieceType::Pawn,
            });
            self.remove_piece(them, PieceType::Pawn, captured_square);
        } else if mv.is_capture() {
            let victim = self.squares[to as usize].expect("capture has a target");
            undo.captured = Some(victim);
            self.remove_piece(victim.color, victim.piece_type, to);
        }

        if let Some(promotion) = mv.promotion() {
            self.remove_piece(us, PieceType::Pawn, from);
            self.add_piece(us, promotion, to);
        } else {
            self.move_piece(us, moving, from, to);
        }

        if mv.is_king_castle() {
            let (rook_from, rook_to) = if us == Color::White { (7, 5) } else { (63, 61) };
            self.move_piece(us, PieceType::Rook, rook_from, rook_to);
        } else if mv.is_queen_castle() {
            let (rook_from, rook_to) = if us == Color::White { (0, 3) } else { (56, 59) };
            self.move_piece(us, PieceType::Rook, rook_from, rook_to);
        }

        if mv.is_double_pawn_push() {
            let square = if us == Color::White {
                from + 8
            } else {
                from - 8
            };
            self.en_passant = Some(square);
            self.zobrist ^= z.en_passant_file[file_of(square) as usize];
        }

        let old_rights = self.castling_rights;
        self.castling_rights &= castling_mask(from) & castling_mask(to);
        if self.castling_rights != old_rights {
            self.zobrist ^=
                z.castling[old_rights as usize] ^ z.castling[self.castling_rights as usize];
        }

        if moving == PieceType::Pawn || mv.is_capture() {
            self.halfmove_clock = 0;
        } else {
            self.halfmove_clock += 1;
        }

        if us == Color::Black {
            self.fullmove_number += 1;
        }
        self.side_to_move = them;
        self.zobrist ^= z.side_to_move;

        undo
    }

    pub fn unmake_move(&mut self, mv: Move, undo: Undo) {
        let us = self.side_to_move.opponent();
        let them = us.opponent();
        let from = mv.from();
        let to = mv.to();

        if let Some(promotion) = mv.promotion() {
            self.remove_piece(us, promotion, to);
            self.add_piece(us, PieceType::Pawn, from);
        } else {
            let moved = self.squares[to as usize]
                .expect("a piece sits on the destination")
                .piece_type;
            self.move_piece(us, moved, to, from);
        }

        if mv.is_king_castle() {
            let (rook_from, rook_to) = if us == Color::White { (7, 5) } else { (63, 61) };
            self.move_piece(us, PieceType::Rook, rook_to, rook_from);
        } else if mv.is_queen_castle() {
            let (rook_from, rook_to) = if us == Color::White { (0, 3) } else { (56, 59) };
            self.move_piece(us, PieceType::Rook, rook_to, rook_from);
        }

        if mv.is_en_passant() {
            let captured_square = if us == Color::White { to - 8 } else { to + 8 };
            self.add_piece(them, PieceType::Pawn, captured_square);
        } else if let Some(victim) = undo.captured {
            self.add_piece(victim.color, victim.piece_type, to);
        }

        self.castling_rights = undo.castling_rights;
        self.en_passant = undo.en_passant;
        self.halfmove_clock = undo.halfmove_clock;
        if us == Color::Black {
            self.fullmove_number -= 1;
        }
        self.side_to_move = us;
        self.zobrist = undo.zobrist;
    }
}

/// The castling rights to keep when a piece leaves or lands on `square`.
fn castling_mask(square: Square) -> u8 {
    match square {
        0 => 0xF & !CASTLE_WQ,
        4 => 0xF & !(CASTLE_WK | CASTLE_WQ),
        7 => 0xF & !CASTLE_WK,
        56 => 0xF & !CASTLE_BQ,
        60 => 0xF & !(CASTLE_BK | CASTLE_BQ),
        63 => 0xF & !CASTLE_BK,
        _ => 0xF,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fen_round_trips() {
        for fen in [
            STARTPOS_FEN,
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
            "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
            "4k3/8/8/8/8/8/8/4K3 b - - 5 39",
        ] {
            let board = Board::from_fen(fen).unwrap();
            assert_eq!(board.to_fen(), fen, "round trip for {fen}");
        }
    }

    #[test]
    fn zobrist_initialized_from_scratch_matches() {
        let board =
            Board::from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
                .unwrap();
        assert_eq!(board.zobrist, board.compute_zobrist());
    }

    #[test]
    fn make_unmake_restores_board_and_zobrist() {
        fn walk(board: &mut Board, depth: u32) {
            if depth == 0 {
                return;
            }
            for mv in crate::movegen::generate_legal(board) {
                let fen_before = board.to_fen();
                let zobrist_before = board.zobrist;
                let undo = board.make_move(mv);
                // The incrementally maintained key equals a from-scratch recompute.
                assert_eq!(
                    board.zobrist,
                    board.compute_zobrist(),
                    "after {}",
                    mv.to_uci()
                );
                walk(board, depth - 1);
                board.unmake_move(mv, undo);
                assert_eq!(
                    board.to_fen(),
                    fen_before,
                    "fen after unmaking {}",
                    mv.to_uci()
                );
                assert_eq!(
                    board.zobrist,
                    zobrist_before,
                    "zobrist after unmaking {}",
                    mv.to_uci()
                );
            }
        }
        // Kiwipete exercises captures, castling, en passant, and promotions.
        let mut board =
            Board::from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
                .unwrap();
        walk(&mut board, 3);
    }
}
