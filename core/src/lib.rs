//! brandobot_core — the native chess engine core.
//!
//! This crate owns all chess logic: bitboard board representation, move
//! generation, evaluation, move ordering, the transposition table, and search.
//! The Python wrappers (the UCI loop and the Flask API) hold a [`Searcher`] and
//! call into it; all chess logic lives here.

mod attacks;
mod board;
mod chess_move;
mod eval;
mod movegen;
mod movesort;
mod nnue;
mod search;
mod tt;
mod types;
mod zobrist;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use board::Board;
use chess_move::parse_uci;
use movegen::generate_legal;
use tt::{Flag, VecTt};

/// The UCI null move, returned when no legal move exists.
const NULL_MOVE: &str = "0000";

/// A captured decision tree: the searched position's FEN and the root nodes.
/// Populated only when `next_move` is asked to capture one.
type DecisionTree = (String, Vec<CapturedNode>);

/// One captured tree node, ready to serialize to the HTTP client.
struct CapturedNode {
    uci: String,
    value: i32,
    children: Vec<CapturedNode>,
}

impl CapturedNode {
    fn from_tree(node: search::TreeNode) -> CapturedNode {
        CapturedNode {
            uci: node.mv.to_uci(),
            value: node.value,
            children: node
                .children
                .into_iter()
                .map(CapturedNode::from_tree)
                .collect(),
        }
    }
}

/// Searcher — owns a Board and a transposition table and returns the best Move
/// for the current position. The Python wrappers hold one per game. `unsendable`
/// because the `VecTt` backend is `RefCell`-backed (`!Sync`): the engine object
/// is thread-affine to the Python thread that drives it.
#[pyclass(unsendable)]
struct Searcher {
    board: Board,
    transposition_table: VecTt,
    last_decision_tree: Option<DecisionTree>,
    /// The NNUE network, when one has been loaded; otherwise leaf positions use
    /// the hand-written evaluation. Engine configuration, not game state — it
    /// survives `new_game`.
    eval_net: Option<nnue::Network>,
}

#[pymethods]
impl Searcher {
    #[new]
    fn new() -> Self {
        Searcher {
            board: Board::startpos(),
            transposition_table: VecTt::new(),
            last_decision_tree: None,
            eval_net: None,
        }
    }

    /// Reset to the starting position, clear the transposition table, and drop
    /// any captured decision tree. The loaded NNUE network, if any, is kept.
    fn new_game(&mut self) {
        self.board = Board::startpos();
        self.transposition_table = VecTt::new();
        self.last_decision_tree = None;
    }

    /// Load an NNUE network from a file; leaf positions then evaluate through it
    /// instead of the hand-written evaluation. Rejects a file that does not match
    /// the compiled architecture.
    fn load_nnue(&mut self, path: &str) -> PyResult<()> {
        let bytes = std::fs::read(path)
            .map_err(|err| PyValueError::new_err(format!("cannot read '{path}': {err}")))?;
        let network = nnue::Network::from_bytes(&bytes).map_err(PyValueError::new_err)?;
        self.eval_net = Some(network);
        Ok(())
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
    /// or the null move when no legal move exists. When `capture_tree` is set,
    /// also record a decision tree `tree_depth` plies deep (clamped to the search
    /// depth) for `decision_tree`.
    #[pyo3(signature = (depth, capture_tree=false, tree_depth=1))]
    fn next_move(&mut self, depth: u32, capture_tree: bool, tree_depth: u32) -> String {
        if capture_tree {
            let plies = tree_depth.clamp(1, depth.max(1));
            let nodes = {
                let mut scout = search::Searcher::new(&self.transposition_table)
                    .with_eval_net(self.eval_net.as_ref());
                scout.capture_tree(&mut self.board, depth as i32, plies, 0)
            };
            let captured = nodes.into_iter().map(CapturedNode::from_tree).collect();
            self.last_decision_tree = Some((self.board.to_fen(), captured));
        }
        let mut searcher =
            search::Searcher::new(&self.transposition_table).with_eval_net(self.eval_net.as_ref());
        match searcher.best_move(&mut self.board, depth as i32) {
            Some(mv) => mv.to_uci(),
            None => NULL_MOVE.to_string(),
        }
    }

    /// Iteratively deepen within the given limits and return the result. All
    /// times are milliseconds. `score_centipawns` is None when a mate is found;
    /// `mate_in_moves` is the signed moves to mate otherwise.
    #[pyo3(signature = (max_depth=64, move_time_ms=None, white_time_ms=None,
                        black_time_ms=None, white_increment_ms=0,
                        black_increment_ms=0, moves_to_go=None, node_limit=None))]
    #[allow(clippy::too_many_arguments)]
    fn search<'py>(
        &mut self,
        py: Python<'py>,
        max_depth: u32,
        move_time_ms: Option<u64>,
        white_time_ms: Option<u64>,
        black_time_ms: Option<u64>,
        white_increment_ms: u64,
        black_increment_ms: u64,
        moves_to_go: Option<u32>,
        node_limit: Option<u64>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let limits = search::SearchLimits {
            max_depth,
            move_time_ms,
            white_time_ms,
            black_time_ms,
            white_increment_ms,
            black_increment_ms,
            moves_to_go,
            node_limit,
        };
        let result = {
            let mut searcher = search::Searcher::new(&self.transposition_table)
                .with_eval_net(self.eval_net.as_ref());
            searcher.search(&mut self.board, &limits, std::time::Instant::now())
        };

        let (score_centipawns, mate_in_moves) = match search::mate_in_moves(result.score) {
            Some(moves) => (None, Some(moves)),
            None => (Some(result.score), None),
        };
        let principal_variation: Vec<String> = result
            .principal_variation
            .iter()
            .map(|mv| mv.to_uci())
            .collect();

        let dict = PyDict::new(py);
        dict.set_item(
            "best_move",
            result
                .best_move
                .map(|mv| mv.to_uci())
                .unwrap_or_else(|| NULL_MOVE.to_string()),
        )?;
        dict.set_item("score_centipawns", score_centipawns)?;
        dict.set_item("mate_in_moves", mate_in_moves)?;
        dict.set_item("depth", result.depth)?;
        dict.set_item("nodes", result.nodes)?;
        dict.set_item("elapsed_ms", result.elapsed_ms)?;
        dict.set_item("principal_variation", principal_variation)?;
        Ok(dict)
    }

    /// The decision tree captured by the last `next_move(capture_tree=True)`, or
    /// None when no search has captured one. Each move carries its value and the
    /// reply tree beneath it.
    fn decision_tree<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let Some((fen, nodes)) = &self.last_decision_tree else {
            return Ok(None);
        };
        let root = PyDict::new(py);
        root.set_item("fen", fen)?;
        root.set_item("moves", build_tree(py, nodes)?)?;
        Ok(Some(root))
    }
}

/// Build a nested move list from captured tree nodes.
fn build_tree<'py>(py: Python<'py>, nodes: &[CapturedNode]) -> PyResult<Bound<'py, PyList>> {
    let list = PyList::empty(py);
    for node in nodes {
        let dict = PyDict::new(py);
        dict.set_item("move", &node.uci)?;
        dict.set_item("value", node.value)?;
        dict.set_item("children", build_tree(py, &node.children)?)?;
        list.append(dict)?;
    }
    Ok(list)
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

/// The absolute (white-positive) static evaluation of `fen`.
#[pyfunction]
fn evaluate(fen: &str) -> PyResult<i64> {
    let board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    Ok(eval::evaluate(&board) as i64)
}

/// The white-positive NNUE evaluation of `fen` under the network at `net_path`.
/// Lets the trainer verify its exported `.nnue` against the engine's own math.
#[pyfunction]
fn nnue_evaluate(fen: &str, net_path: &str) -> PyResult<i64> {
    let board = Board::from_fen(fen).map_err(PyValueError::new_err)?;
    let bytes = std::fs::read(net_path)
        .map_err(|err| PyValueError::new_err(format!("cannot read '{net_path}': {err}")))?;
    let network = nnue::Network::from_bytes(&bytes).map_err(PyValueError::new_err)?;
    Ok(network.evaluate(&board) as i64)
}

/// Whether `fen` parses as a legal position — for boundary validation.
#[pyfunction]
fn is_valid_fen(fen: &str) -> bool {
    Board::from_fen(fen).is_ok()
}

/// The `brandobot_core` Python module.
#[pymodule]
fn brandobot_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Searcher>()?;
    module.add_function(wrap_pyfunction!(perft, module)?)?;
    module.add_function(wrap_pyfunction!(legal_moves, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate, module)?)?;
    module.add_function(wrap_pyfunction!(nnue_evaluate, module)?)?;
    module.add_function(wrap_pyfunction!(is_valid_fen, module)?)?;
    Ok(())
}
