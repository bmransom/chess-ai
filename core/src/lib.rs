//! brandobot_core — the native chess engine core.
//!
//! This crate owns all chess logic: bitboard board representation, move
//! generation, evaluation, move ordering, the transposition table, and search.
//! Python reaches it through the [`Searcher`] class and the module functions
//! [`perft`] and [`legal_moves`].
//!
//! Search itself lands in Wave 6; until then [`Searcher::next_move`] returns the
//! first legal move so the seam is exercisable end to end.

mod attacks;
mod board;
mod chess_move;
mod eval;
mod movegen;
mod movesort;
mod search;
mod tt;
mod types;
mod zobrist;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use board::Board;
use chess_move::parse_uci;
use movegen::generate_legal;
use tt::{Flag, TranspositionTable};

/// The UCI null move, returned when no legal move exists.
const NULL_MOVE: &str = "0000";

/// Searcher — owns a Board (and, from Wave 5, a TranspositionTable) and returns
/// the best Move for the current position. The Python wrappers hold one per game.
#[pyclass]
struct Searcher {
    board: Board,
    transposition_table: TranspositionTable,
}

#[pymethods]
impl Searcher {
    #[new]
    fn new() -> Self {
        Searcher {
            board: Board::startpos(),
            transposition_table: TranspositionTable::new(),
        }
    }

    /// Reset to the starting position and clear the transposition table.
    fn new_game(&mut self) {
        self.board = Board::startpos();
        self.transposition_table = TranspositionTable::new();
    }

    /// Set the position: `fen` (or the start position when omitted), then apply
    /// `moves` in UCI notation.
    #[pyo3(signature = (fen=None, moves=None))]
    fn set_position(&mut self, fen: Option<String>, moves: Option<Vec<String>>) -> PyResult<()> {
        let mut board = match fen {
            Some(text) => Board::from_fen(&text).map_err(PyValueError::new_err)?,
            None => Board::startpos(),
        };
        if let Some(moves) = moves {
            for uci in moves {
                if !apply_uci_move(&mut board, &uci) {
                    return Err(PyValueError::new_err(format!(
                        "illegal or malformed move '{uci}'"
                    )));
                }
            }
        }
        self.board = board;
        Ok(())
    }

    /// Set the position directly from a FEN.
    fn set_fen(&mut self, fen: &str) -> PyResult<()> {
        self.board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
        Ok(())
    }

    /// The current position as a FEN.
    fn fen(&self) -> String {
        self.board.to_fen()
    }

    /// The transposition-table entries, one dict each, for the HTTP
    /// introspection endpoint.
    fn transposition_table<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyDict>>> {
        let mut entries = Vec::new();
        for entry in self.transposition_table.entries() {
            let dict = PyDict::new(py);
            dict.set_item("zobrist", entry.zobrist)?;
            dict.set_item(
                "best_move",
                entry
                    .best_move
                    .map(|mv| mv.to_uci())
                    .unwrap_or_else(|| "None".to_string()),
            )?;
            dict.set_item("depth", entry.depth)?;
            dict.set_item("value", entry.value)?;
            dict.set_item("flag", flag_name(entry.flag))?;
            dict.set_item("age", entry.age)?;
            entries.push(dict);
        }
        Ok(entries)
    }

    /// The best Move for the side to move, searched to `depth`, in UCI notation,
    /// or the null move when no legal move exists.
    #[pyo3(signature = (depth, capture_tree=false))]
    fn next_move(&mut self, depth: u32, capture_tree: bool) -> String {
        let _ = capture_tree;
        let is_endgame = eval::is_endgame(&self.board);
        let mut searcher = search::Searcher::new(&mut self.transposition_table, is_endgame);
        match searcher.best_move(&mut self.board, depth as i32) {
            Some(mv) => mv.to_uci(),
            None => NULL_MOVE.to_string(),
        }
    }
}

/// The transposition-table flag name, matching the original's `Flag.name`.
fn flag_name(flag: Flag) -> &'static str {
    match flag {
        Flag::Exact => "EXACT",
        Flag::LowerBound => "LOWER_BOUND",
        Flag::UpperBound => "UPPER_BOUND",
    }
}

/// Find the legal move matching a UCI string and play it; return whether it was
/// found and applied.
fn apply_uci_move(board: &mut Board, uci: &str) -> bool {
    let Some((from, to, promotion)) = parse_uci(uci) else {
        return false;
    };
    for mv in generate_legal(board) {
        if mv.from() == from && mv.to() == to && mv.promotion() == promotion {
            board.make_move(mv);
            return true;
        }
    }
    false
}

/// Count leaf nodes to `depth` from `fen` — the move-generation gate.
#[pyfunction]
fn perft(fen: &str, depth: u32) -> PyResult<u64> {
    let mut board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    Ok(movegen::perft(&mut board, depth))
}

/// Every legal move for `fen`, in UCI notation. Used by the differential test
/// that cross-checks move generation against python-chess.
#[pyfunction]
fn legal_moves(fen: &str) -> PyResult<Vec<String>> {
    let mut board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    Ok(generate_legal(&mut board)
        .iter()
        .map(|mv| mv.to_uci())
        .collect())
}

/// The absolute (white-positive) static evaluation of `fen`, matching
/// `Board.value()`. Used by the eval-parity test.
#[pyfunction]
fn evaluate(fen: &str) -> PyResult<i64> {
    let board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    let endgame = eval::is_endgame(&board);
    Ok(eval::value(&board, endgame) as i64)
}

/// Whether `fen` is an endgame, matching `Board.is_endgame`.
#[pyfunction]
fn is_endgame(fen: &str) -> PyResult<bool> {
    let board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    Ok(eval::is_endgame(&board))
}

/// The `brandobot_core` Python module.
#[pymodule]
fn brandobot_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Searcher>()?;
    module.add_function(wrap_pyfunction!(perft, module)?)?;
    module.add_function(wrap_pyfunction!(legal_moves, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate, module)?)?;
    module.add_function(wrap_pyfunction!(is_endgame, module)?)?;
    Ok(())
}
