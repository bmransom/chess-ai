//! brandobot_core — the native chess engine core.
//!
//! This crate owns all chess logic: bitboard board representation, move
//! generation, evaluation, move ordering, the transposition table, and search.
//! Python reaches it through the [`Searcher`] class and the [`perft`] function.
//!
//! Wave 0 is a walking skeleton — the seam compiles, imports, and answers. The
//! real Board, move generation, evaluation, and search land in later waves; the
//! method bodies below are deliberate placeholders, marked as such.

use pyo3::prelude::*;

/// Starting position in Forsyth–Edwards Notation.
const STARTPOS_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/// The UCI null move — returned when no legal move exists.
const NULL_MOVE: &str = "0000";

/// Searcher — owns a Board and a TranspositionTable and returns the best Move
/// for the current position. The Python wrappers hold one Searcher per game.
///
/// Walking skeleton: it tracks only the current FEN; the Board, move
/// generation, and search arrive in later waves.
#[pyclass]
struct Searcher {
    fen: String,
}

#[pymethods]
impl Searcher {
    #[new]
    fn new() -> Self {
        Searcher {
            fen: STARTPOS_FEN.to_string(),
        }
    }

    /// Reset to the starting position and clear the transposition table.
    fn new_game(&mut self) {
        self.fen = STARTPOS_FEN.to_string();
    }

    /// Set the position: `fen` (or the start position when omitted), then apply
    /// `moves` in UCI notation. Move application lands with make/unmake (Wave 1).
    #[pyo3(signature = (fen=None, moves=None))]
    fn set_position(&mut self, fen: Option<String>, moves: Option<Vec<String>>) {
        self.fen = fen.unwrap_or_else(|| STARTPOS_FEN.to_string());
        let _ = moves;
    }

    /// Set the position directly from a FEN.
    fn set_fen(&mut self, fen: String) {
        self.fen = fen;
    }

    /// The current position as a FEN.
    fn fen(&self) -> String {
        self.fen.clone()
    }

    /// The best Move for the side to move, searched to `depth`, in UCI
    /// notation. Walking skeleton: returns the null move until search exists
    /// (Wave 6).
    #[pyo3(signature = (depth, capture_tree=false))]
    fn next_move(&mut self, depth: u32, capture_tree: bool) -> String {
        let _ = (depth, capture_tree);
        NULL_MOVE.to_string()
    }
}

/// Count leaf nodes to `depth` from `fen` — the move-generation gate. Walking
/// skeleton: returns 0 until move generation exists (Wave 2).
#[pyfunction]
#[pyo3(signature = (fen, depth))]
fn perft(fen: &str, depth: u32) -> u64 {
    let _ = (fen, depth);
    0
}

/// The `brandobot_core` Python module.
#[pymodule]
fn brandobot_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Searcher>()?;
    module.add_function(wrap_pyfunction!(perft, module)?)?;
    Ok(())
}
