//! TranspositionTable — a Zobrist-keyed cache of evaluated positions, a port of
//! `src/transposition_table.py` with the same replace-by-depth-and-age policy.
//! The cache is a trait with two backends: `ExclusiveTranspositionTable` for
//! single-threaded search (`Threads = 1`) and, later, a lockless atomic table
//! for parallel search.

use std::cell::RefCell;

use crate::chess_move::Move;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Flag {
    Exact,
    LowerBound,
    UpperBound,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct HashEntry {
    pub zobrist: u64,
    pub best_move: Option<Move>,
    pub depth: i32,
    pub value: i32,
    pub flag: Flag,
    /// The position's halfmove clock at store time, used for aging.
    pub age: u16,
}

/// 2^20 + 7 (prime), matching the original.
const TABLE_SIZE: usize = 1_048_583;

/// A Zobrist-keyed cache of evaluated positions. `probe` and `replace` take
/// `&self` so one table can back several searches at once; the backend supplies
/// the synchronization (`RefCell` for the single-threaded
/// `ExclusiveTranspositionTable`, atomics for the lockless parallel table). The
/// Searcher is generic over this trait, so the backend is chosen once at search
/// entry with no per-node virtual call.
pub trait TranspositionTable {
    /// The stored entry whose key matches, regardless of depth. The search
    /// decides whether the entry is deep enough to cut; even a shallow entry
    /// seeds move ordering with its best Move.
    fn probe(&self, zobrist: u64) -> Option<HashEntry>;

    /// Store `entry` if the slot is empty, the new entry is newer (greater age),
    /// or it was searched deeper.
    fn replace(&self, entry: HashEntry);
}

/// The single-threaded backend: today's `Vec` slot table behind `RefCell`
/// interior mutability. Used for `Threads = 1`; with one thread the borrow
/// always succeeds, so it is bit-identical to the original engine.
pub struct ExclusiveTranspositionTable {
    table: RefCell<Vec<Option<HashEntry>>>,
}

impl Default for ExclusiveTranspositionTable {
    fn default() -> Self {
        ExclusiveTranspositionTable::new()
    }
}

impl ExclusiveTranspositionTable {
    pub fn new() -> ExclusiveTranspositionTable {
        ExclusiveTranspositionTable {
            table: RefCell::new(vec![None; TABLE_SIZE]),
        }
    }

    /// A point-in-time snapshot of the live entries, for HTTP introspection.
    /// Returns owned entries because the slots sit behind a `RefCell` borrow.
    pub fn entries(&self) -> Vec<HashEntry> {
        self.table
            .borrow()
            .iter()
            .filter_map(|slot| *slot)
            .collect()
    }
}

impl TranspositionTable for ExclusiveTranspositionTable {
    fn probe(&self, zobrist: u64) -> Option<HashEntry> {
        let index = (zobrist % TABLE_SIZE as u64) as usize;
        match self.table.borrow()[index] {
            Some(stored) if stored.zobrist == zobrist => Some(stored),
            _ => None,
        }
    }

    fn replace(&self, entry: HashEntry) {
        let index = (entry.zobrist % TABLE_SIZE as u64) as usize;
        let mut table = self.table.borrow_mut();
        let should_replace = match table[index] {
            None => true,
            Some(stored) => entry.age > stored.age || entry.depth > stored.depth,
        };
        if should_replace {
            table[index] = Some(entry);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(depth: i32, age: u16) -> HashEntry {
        HashEntry {
            zobrist: 0xABCD,
            best_move: None,
            depth,
            value: 20,
            flag: Flag::Exact,
            age,
        }
    }

    #[test]
    fn stores_into_an_empty_slot() {
        let table = ExclusiveTranspositionTable::new();
        let stored = entry(5, 0);
        table.replace(stored);
        assert_eq!(table.probe(0xABCD), Some(stored));
    }

    #[test]
    fn replaces_when_age_is_greater() {
        let table = ExclusiveTranspositionTable::new();
        table.replace(entry(5, 0));
        let newer = entry(5, 2);
        table.replace(newer);
        assert_eq!(table.probe(0xABCD), Some(newer));
    }

    #[test]
    fn replaces_when_depth_is_greater_and_age_equal() {
        let table = ExclusiveTranspositionTable::new();
        table.replace(entry(4, 0));
        let deeper = entry(5, 0);
        table.replace(deeper);
        assert_eq!(table.probe(0xABCD), Some(deeper));
    }

    #[test]
    fn keeps_entry_when_depth_is_lesser_and_age_equal() {
        let table = ExclusiveTranspositionTable::new();
        let deeper = entry(5, 0);
        table.replace(deeper);
        table.replace(entry(4, 0));
        assert_eq!(table.probe(0xABCD), Some(deeper));
    }
}
