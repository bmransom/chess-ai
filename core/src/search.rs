//! Searcher — iterative deepening with alpha-beta pruning, quiescence, the
//! transposition table, mate-distance scoring, and a triangular principal
//! variation. Deepens one ply at a time within a time budget.

use std::time::{Duration, Instant};

use crate::board::Board;
use crate::chess_move::Move;
use crate::eval;
use crate::movegen::generate_legal;
use crate::movesort::{get_moves_to_dequiet, in_check, prioritize_legal_moves};
use crate::tt::{Flag, HashEntry, TranspositionTable};
use crate::types::Color;

/// A checkmate scores `MATE - ply`; any score within `MAX_PLY` of `MATE` is a mate.
const MATE: i32 = 99999;
const MAX_PLY: i32 = 1000;
const MATE_THRESHOLD: i32 = MATE - MAX_PLY;
/// Quiescence stops descending captures below this depth.
const QUIESCENCE_FLOOR: i32 = -5;
/// Poll the clock every this many nodes.
const STOP_CHECK_INTERVAL: u64 = 2048;
/// Reserve this much wall-clock so the engine never flags.
const MOVE_OVERHEAD_MS: u64 = 50;
/// Sudden-death moves-to-go assumption.
const SUDDEN_DEATH_MOVES: u64 = 30;
/// Cap a move at this fraction of the remaining time (percent).
const MAX_BUDGET_PERCENT: u64 = 40;
/// PV table / ply array bound.
const MAX_SEARCH_PLY: usize = 128;

/// The limits for one search. All times are milliseconds.
#[derive(Clone, Copy, Default)]
pub struct SearchLimits {
    pub max_depth: u32,
    pub move_time_ms: Option<u64>,
    pub white_time_ms: Option<u64>,
    pub black_time_ms: Option<u64>,
    pub white_increment_ms: u64,
    pub black_increment_ms: u64,
    pub moves_to_go: Option<u32>,
}

/// The outcome of a search. `score` is internal (centipawns or a mate score);
/// the seam converts it to `score_centipawns` / `mate_in_moves`.
pub struct SearchResult {
    pub best_move: Option<Move>,
    pub score: i32,
    pub depth: i32,
    pub nodes: u64,
    pub elapsed_ms: u64,
    pub principal_variation: Vec<Move>,
}

/// A node in a captured decision tree (debug diagnostic).
pub struct TreeNode {
    pub mv: Move,
    pub value: i32,
    pub children: Vec<TreeNode>,
}

pub struct Searcher<'a> {
    transposition_table: &'a mut TranspositionTable,
    is_endgame: bool,
    /// Zobrist keys along the current line, for threefold-repetition detection.
    history: Vec<u64>,
    nodes: u64,
    deadline: Option<Instant>,
    stopped: bool,
    /// Triangular table: `pv_table[ply]` is the principal variation from `ply`.
    pv_table: Vec<Vec<Move>>,
}

impl<'a> Searcher<'a> {
    pub fn new(transposition_table: &'a mut TranspositionTable, is_endgame: bool) -> Searcher<'a> {
        Searcher {
            transposition_table,
            is_endgame,
            history: Vec::new(),
            nodes: 0,
            deadline: None,
            stopped: false,
            pv_table: vec![Vec::new(); MAX_SEARCH_PLY],
        }
    }

    /// Iteratively deepen within `limits` and return the best result. `now` is the
    /// search start; the clock is measured from it.
    pub fn search(
        &mut self,
        board: &mut Board,
        limits: &SearchLimits,
        now: Instant,
    ) -> SearchResult {
        self.deadline = compute_budget_ms(board.side_to_move(), limits)
            .map(|budget| now + Duration::from_millis(budget));
        let max_depth = limits.max_depth.max(1) as i32;

        // Fallback so we always return a legal move, even if depth 1 is cut off.
        let mut result = SearchResult {
            best_move: prioritize_legal_moves(board, self.is_endgame)
                .into_iter()
                .next(),
            score: 0,
            depth: 0,
            nodes: 0,
            elapsed_ms: 0,
            principal_variation: Vec::new(),
        };

        for depth in 1..=max_depth {
            let (best_move, score) = self.negamax(board, depth, -MATE, MATE, 0);
            if self.stopped {
                break; // discard this incomplete iteration
            }
            if best_move.is_some() {
                result.best_move = best_move;
            }
            result.score = score;
            result.depth = depth;
            result.principal_variation = self.pv_table[0].clone();
            if is_mate_score(score) {
                break; // a forced mate is found; deeper search cannot improve it
            }
        }

        result.nodes = self.nodes;
        result.elapsed_ms = now.elapsed().as_millis() as u64;
        result
    }

    /// The best move searched to a fixed `depth`, no time limit. Used by the HTTP
    /// path and the tactical tests.
    pub fn best_move(&mut self, board: &mut Board, depth: i32) -> Option<Move> {
        let (best, _score) = self.negamax(board, depth, -MATE, MATE, 0);
        best.or_else(|| {
            prioritize_legal_moves(board, self.is_endgame)
                .into_iter()
                .next()
        })
    }

    /// Capture a decision tree `tree_depth` plies deep — the debug diagnostic.
    pub fn capture_tree(
        &mut self,
        board: &mut Board,
        search_depth: i32,
        tree_depth: u32,
        ply: i32,
    ) -> Vec<TreeNode> {
        if tree_depth == 0 {
            return Vec::new();
        }
        let moves = prioritize_legal_moves(board, self.is_endgame);
        let mut nodes = Vec::with_capacity(moves.len());
        for mv in moves {
            let undo = board.make_move(mv);
            let (_, child_score) = self.negamax(board, search_depth - 1, -MATE, MATE, ply + 1);
            let children = self.capture_tree(board, search_depth - 1, tree_depth - 1, ply + 1);
            board.unmake_move(mv, undo);
            nodes.push(TreeNode {
                mv,
                value: -child_score,
                children,
            });
        }
        nodes
    }

    fn should_stop(&mut self) -> bool {
        if self.stopped {
            return true;
        }
        if self.nodes.is_multiple_of(STOP_CHECK_INTERVAL) {
            if let Some(deadline) = self.deadline {
                if Instant::now() >= deadline {
                    self.stopped = true;
                }
            }
        }
        self.stopped
    }

    fn negamax(
        &mut self,
        board: &mut Board,
        depth: i32,
        alpha: i32,
        beta: i32,
        ply: i32,
    ) -> (Option<Move>, i32) {
        let zobrist_key = board.zobrist();
        self.history.push(zobrist_key);
        let result = self.search_node(board, depth, alpha, beta, ply, zobrist_key);
        self.history.pop();
        result
    }

    fn search_node(
        &mut self,
        board: &mut Board,
        depth: i32,
        mut alpha: i32,
        mut beta: i32,
        ply: i32,
        zobrist_key: u64,
    ) -> (Option<Move>, i32) {
        self.nodes += 1;
        if self.should_stop() {
            return (None, 0);
        }
        if (ply as usize) < MAX_SEARCH_PLY {
            self.pv_table[ply as usize].clear();
        }

        let is_in_check = in_check(board);
        let has_legal_move = !generate_legal(board).is_empty();

        if !has_legal_move && is_in_check {
            return (None, -(MATE - ply));
        }
        if depth > 0 && ((!has_legal_move && !is_in_check) || self.is_draw(board, zobrist_key)) {
            return (None, 0);
        }

        let original_alpha = alpha;

        let stored_entry = self.transposition_table.probe(zobrist_key);
        if let Some(stored) = stored_entry {
            if stored.depth >= depth {
                let value = value_from_tt(stored.value, ply);
                match stored.flag {
                    Flag::Exact => return (stored.best_move, value),
                    Flag::LowerBound => alpha = alpha.max(value),
                    Flag::UpperBound => beta = beta.min(value),
                }
                if alpha >= beta {
                    return (stored.best_move, value);
                }
            }
        }
        let tt_move = stored_entry.and_then(|entry| entry.best_move);

        let moves = if depth <= 0 {
            let perspective = if board.side_to_move() == Color::White {
                1
            } else {
                -1
            };
            let stand_pat = eval::value(board, self.is_endgame) * perspective;
            if !is_in_check {
                if stand_pat >= beta {
                    return (None, beta);
                }
                alpha = alpha.max(stand_pat);
            }
            if depth < QUIESCENCE_FLOOR {
                return (None, stand_pat);
            }
            let captures_and_checks = get_moves_to_dequiet(board, self.is_endgame);
            if captures_and_checks.is_empty() {
                return (None, stand_pat);
            }
            order_tt_move_first(captures_and_checks, tt_move)
        } else {
            order_tt_move_first(prioritize_legal_moves(board, self.is_endgame), tt_move)
        };

        let mut best_score = -MATE;
        let mut best_move: Option<Move> = None;
        for mv in moves {
            let undo = board.make_move(mv);
            let (_, child_score) = self.negamax(board, depth - 1, -beta, -alpha, ply + 1);
            board.unmake_move(mv, undo);
            if self.stopped {
                return (None, 0);
            }
            let move_score = -child_score;

            if depth <= 0 && move_score >= beta {
                return (best_move, beta);
            }
            if move_score > best_score {
                best_score = move_score;
                best_move = Some(mv);
                if depth > 0 {
                    self.update_pv(ply, mv);
                }
            }
            alpha = alpha.max(best_score);
            if alpha >= beta {
                break;
            }
        }

        let flag = if best_score <= original_alpha {
            Flag::UpperBound
        } else if best_score >= beta {
            Flag::LowerBound
        } else {
            Flag::Exact
        };
        self.transposition_table.replace(HashEntry {
            zobrist: zobrist_key,
            best_move,
            depth,
            value: value_to_tt(best_score, ply),
            flag,
            age: board.halfmove_clock(),
        });

        (best_move, best_score)
    }

    fn update_pv(&mut self, ply: i32, mv: Move) {
        let ply = ply as usize;
        if ply + 1 >= MAX_SEARCH_PLY {
            return;
        }
        let mut line = Vec::with_capacity(self.pv_table[ply + 1].len() + 1);
        line.push(mv);
        let child_line = self.pv_table[ply + 1].clone();
        line.extend(child_line);
        self.pv_table[ply] = line;
    }

    fn is_draw(&self, board: &Board, zobrist_key: u64) -> bool {
        if board.halfmove_clock() >= 100 {
            return true;
        }
        self.history
            .iter()
            .filter(|&&seen| seen == zobrist_key)
            .count()
            >= 3
    }
}

pub fn is_mate_score(score: i32) -> bool {
    score.abs() >= MATE_THRESHOLD
}

/// The number of moves to mate, signed (positive when the side to move gives
/// mate), or None when `score` is not a mate score. UCI `score mate` is in moves.
pub fn mate_in_moves(score: i32) -> Option<i32> {
    if score >= MATE_THRESHOLD {
        Some((MATE - score + 1) / 2)
    } else if score <= -MATE_THRESHOLD {
        Some(-((MATE + score + 1) / 2))
    } else {
        None
    }
}

/// Store mate scores relative to the node (add the distance to root), so a
/// transposed entry stays correct.
fn value_to_tt(value: i32, ply: i32) -> i32 {
    if value >= MATE_THRESHOLD {
        value + ply
    } else if value <= -MATE_THRESHOLD {
        value - ply
    } else {
        value
    }
}

/// Re-relativize a stored mate score to this node's distance from the root.
fn value_from_tt(value: i32, ply: i32) -> i32 {
    if value >= MATE_THRESHOLD {
        value - ply
    } else if value <= -MATE_THRESHOLD {
        value + ply
    } else {
        value
    }
}

/// Promote the transposition-table move to the front, preserving the order of the
/// rest.
fn order_tt_move_first(mut moves: Vec<Move>, tt_move: Option<Move>) -> Vec<Move> {
    if let Some(tt_move) = tt_move {
        if let Some(index) = moves.iter().position(|&candidate| candidate == tt_move) {
            moves[..=index].rotate_right(1);
        }
    }
    moves
}

/// The per-move time budget in milliseconds, or None for a depth-only search.
fn compute_budget_ms(side: Color, limits: &SearchLimits) -> Option<u64> {
    if let Some(move_time) = limits.move_time_ms {
        return Some(move_time.saturating_sub(MOVE_OVERHEAD_MS));
    }
    let (remaining, increment) = match side {
        Color::White => (limits.white_time_ms, limits.white_increment_ms),
        Color::Black => (limits.black_time_ms, limits.black_increment_ms),
    };
    let remaining = remaining?;
    let divisor = limits
        .moves_to_go
        .map(|moves| moves as u64)
        .unwrap_or(SUDDEN_DEATH_MOVES)
        .max(1);
    let budget = remaining / divisor + increment * 7 / 10;
    let cap = remaining * MAX_BUDGET_PERCENT / 100;
    Some(budget.min(cap).saturating_sub(MOVE_OVERHEAD_MS))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn searcher_for(fen: &str) -> (Board, TranspositionTable) {
        let board = Board::from_fen(fen).unwrap();
        let table = TranspositionTable::new();
        (board, table)
    }

    fn best(fen: &str, depth: i32) -> String {
        let (mut board, mut table) = searcher_for(fen);
        let is_endgame = eval::is_endgame(&board);
        let mut searcher = Searcher::new(&mut table, is_endgame);
        searcher
            .best_move(&mut board, depth)
            .expect("a legal move exists")
            .to_uci()
    }

    fn run_search(fen: &str, limits: SearchLimits) -> SearchResult {
        let (mut board, mut table) = searcher_for(fen);
        let is_endgame = eval::is_endgame(&board);
        let mut searcher = Searcher::new(&mut table, is_endgame);
        searcher.search(&mut board, &limits, Instant::now())
    }

    const STARTPOS: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
    const MIDGAME: &str = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 1";
    const MATE_IN_ONE: &str = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1";

    // --- Wave 6: tactics preserved ---

    #[test]
    fn blocks_the_threatened_mate() {
        assert_eq!(
            best(
                "1r3rk1/p1p3pp/3bp3/1p1P1q2/P3pP2/2B1P2P/1P4Q1/4K1NR b K - 0 1",
                3
            ),
            "f8f7"
        );
    }

    #[test]
    fn moves_the_king_out_of_a_mating_net() {
        assert_eq!(
            best(
                "1r1qr3/pppbbQ1k/2n1p1p1/2PpP3/3P4/2P2N2/P1B2PP1/1RB1K3 b - - 0 1",
                3
            ),
            "h7h8"
        );
    }

    #[test]
    fn finds_the_mate_in_three() {
        assert_eq!(best("r5rk/5p1p/5R2/4B3/8/8/7P/7K w", 3), "f6a6");
    }

    #[test]
    fn declines_to_sacrifice_the_rook() {
        assert_ne!(
            best("2r3k1/6p1/5p1p/p2r4/3p4/6B1/PPP2PPP/R3R1K1 w - - 0 1", 3),
            "e1e8"
        );
    }

    // --- Wave 2: time budget ---

    #[test]
    fn budget_honors_movetime() {
        let limits = SearchLimits {
            move_time_ms: Some(1000),
            ..Default::default()
        };
        assert_eq!(compute_budget_ms(Color::White, &limits), Some(950));
    }

    #[test]
    fn budget_in_sudden_death_is_a_thirtieth_plus_increment() {
        let limits = SearchLimits {
            white_time_ms: Some(60_000),
            white_increment_ms: 1_000,
            ..Default::default()
        };
        // 60000/30 + 0.7*1000 - 50 = 2000 + 700 - 50.
        assert_eq!(compute_budget_ms(Color::White, &limits), Some(2_650));
    }

    #[test]
    fn budget_divides_by_moves_to_go() {
        let limits = SearchLimits {
            white_time_ms: Some(60_000),
            moves_to_go: Some(10),
            ..Default::default()
        };
        assert_eq!(compute_budget_ms(Color::White, &limits), Some(5_950));
    }

    #[test]
    fn budget_is_capped_at_forty_percent() {
        let limits = SearchLimits {
            white_time_ms: Some(1_000),
            moves_to_go: Some(1),
            ..Default::default()
        };
        // remaining/1 = 1000, capped to 400, minus 50.
        assert_eq!(compute_budget_ms(Color::White, &limits), Some(350));
    }

    #[test]
    fn budget_is_none_without_a_clock_or_movetime() {
        let limits = SearchLimits {
            max_depth: 4,
            ..Default::default()
        };
        assert_eq!(compute_budget_ms(Color::White, &limits), None);
    }

    // --- Wave 3: iterative deepening loop ---

    #[test]
    fn search_reaches_the_requested_depth() {
        let result = run_search(
            STARTPOS,
            SearchLimits {
                max_depth: 4,
                ..Default::default()
            },
        );
        assert_eq!(result.depth, 4);
        assert!(result.best_move.is_some());
    }

    #[test]
    fn a_tiny_budget_still_returns_a_move() {
        let result = run_search(
            MIDGAME,
            SearchLimits {
                max_depth: 64,
                move_time_ms: Some(1),
                ..Default::default()
            },
        );
        assert!(result.best_move.is_some());
    }

    #[test]
    fn a_movetime_search_stays_within_a_sane_bound() {
        let result = run_search(
            MIDGAME,
            SearchLimits {
                max_depth: 64,
                move_time_ms: Some(200),
                ..Default::default()
            },
        );
        assert!(result.best_move.is_some());
        assert!(result.elapsed_ms < 2_000, "elapsed {}", result.elapsed_ms);
    }

    // --- Wave 4: principal variation ---

    #[test]
    fn pv_first_move_is_the_best_move() {
        let result = run_search(
            STARTPOS,
            SearchLimits {
                max_depth: 4,
                ..Default::default()
            },
        );
        assert_eq!(
            result.principal_variation.first().copied(),
            result.best_move
        );
    }

    #[test]
    fn pv_is_a_legal_sequence() {
        let result = run_search(
            MIDGAME,
            SearchLimits {
                max_depth: 4,
                ..Default::default()
            },
        );
        let mut board = Board::from_fen(MIDGAME).unwrap();
        for mv in &result.principal_variation {
            let legal = generate_legal(&mut board);
            assert!(legal.contains(mv), "{} not legal", mv.to_uci());
            board.make_move(*mv);
        }
    }

    // --- Wave 1.2: mate-distance scoring ---

    #[test]
    fn mate_score_survives_a_tt_round_trip() {
        let root_relative = MATE - 5;
        let stored = value_to_tt(root_relative, 3);
        assert_eq!(value_from_tt(stored, 3), root_relative);
    }

    #[test]
    fn a_faster_mate_scores_higher() {
        let mate_in_one = run_search(
            MATE_IN_ONE,
            SearchLimits {
                max_depth: 4,
                ..Default::default()
            },
        );
        let mate_in_three = run_search(
            "r5rk/5p1p/5R2/4B3/8/8/7P/7K w",
            SearchLimits {
                max_depth: 4,
                ..Default::default()
            },
        );
        assert!(is_mate_score(mate_in_one.score));
        assert!(is_mate_score(mate_in_three.score));
        assert!(mate_in_one.score > mate_in_three.score);
        assert_eq!(mate_in_moves(mate_in_one.score), Some(1));
        assert_eq!(mate_in_moves(mate_in_three.score), Some(3));
    }

    // --- Wave 1.1: transposition-table reuse ---

    #[test]
    fn a_warm_table_reduces_nodes() {
        fn nodes(fen: &str, depth: i32, warm: bool) -> u64 {
            let (mut board, mut table) = searcher_for(fen);
            let is_endgame = eval::is_endgame(&board);
            if warm {
                let mut warmup = Searcher::new(&mut table, is_endgame);
                warmup.best_move(&mut board, depth - 1);
            }
            let mut searcher = Searcher::new(&mut table, is_endgame);
            searcher.best_move(&mut board, depth);
            searcher.nodes
        }
        let cold = nodes(MIDGAME, 5, false);
        let warm = nodes(MIDGAME, 5, true);
        assert!(warm < cold, "warm {warm} should be < cold {cold}");
    }
}
