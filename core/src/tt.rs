//! TranspositionTable — a Zobrist-keyed cache of evaluated positions, a port of
//! `src/transposition_table.py` with the same replace-by-depth-and-age policy.

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

pub struct TranspositionTable {
    table: Vec<Option<HashEntry>>,
}

impl Default for TranspositionTable {
    fn default() -> Self {
        TranspositionTable::new()
    }
}

impl TranspositionTable {
    pub fn new() -> TranspositionTable {
        TranspositionTable {
            table: vec![None; TABLE_SIZE],
        }
    }

    /// Store `entry` if the slot is empty, the new entry is newer (greater age),
    /// or it was searched deeper.
    pub fn replace(&mut self, entry: HashEntry) {
        let index = (entry.zobrist % TABLE_SIZE as u64) as usize;
        let should_replace = match self.table[index] {
            None => true,
            Some(stored) => entry.age > stored.age || entry.depth > stored.depth,
        };
        if should_replace {
            self.table[index] = Some(entry);
        }
    }

    /// The stored entry, if its key matches and it was searched at least as deep.
    pub fn get(&self, zobrist: u64, depth: i32) -> Option<HashEntry> {
        let index = (zobrist % TABLE_SIZE as u64) as usize;
        match self.table[index] {
            Some(stored) if stored.zobrist == zobrist && stored.depth >= depth => Some(stored),
            _ => None,
        }
    }

    pub fn entries(&self) -> impl Iterator<Item = &HashEntry> {
        self.table.iter().filter_map(|slot| slot.as_ref())
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
        let mut table = TranspositionTable::new();
        let stored = entry(5, 0);
        table.replace(stored);
        assert_eq!(table.get(0xABCD, 5), Some(stored));
    }

    #[test]
    fn replaces_when_age_is_greater() {
        let mut table = TranspositionTable::new();
        table.replace(entry(5, 0));
        let newer = entry(5, 2);
        table.replace(newer);
        assert_eq!(table.get(0xABCD, 5), Some(newer));
    }

    #[test]
    fn replaces_when_depth_is_greater_and_age_equal() {
        let mut table = TranspositionTable::new();
        table.replace(entry(4, 0));
        let deeper = entry(5, 0);
        table.replace(deeper);
        assert_eq!(table.get(0xABCD, 5), Some(deeper));
    }

    #[test]
    fn keeps_entry_when_depth_is_lesser_and_age_equal() {
        let mut table = TranspositionTable::new();
        let deeper = entry(5, 0);
        table.replace(deeper);
        table.replace(entry(4, 0));
        assert_eq!(table.get(0xABCD, 5), Some(deeper));
    }
}
