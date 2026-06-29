//! TranspositionTable — a Zobrist-keyed cache of evaluated positions, a port of
//! `src/transposition_table.py` with the same replace-by-depth-and-age policy.
//! The cache is a trait with two backends: `ExclusiveTranspositionTable` for
//! single-threaded search (`Threads = 1`) and `LocklessTranspositionTable`, a
//! lockless atomic table, for parallel search (`Threads > 1`).

use std::cell::RefCell;
use std::sync::atomic::{AtomicU64, Ordering};

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

/// The lockless parallel backend (`Threads > 1`): a slot table of atomic word
/// pairs using Robert Hyatt's key-XOR-data trick. Each `HashEntry` packs into one
/// 60-bit `data` word and the slot stores `key = zobrist ^ data`, so `probe`
/// trusts a slot only when `key ^ data` reproduces the probed zobrist. A torn read
/// — `key` from one store, `data` from another — fails that checksum and reads as
/// a miss, never a wrong-position hit. No locks on the hot path, no `unsafe`.
#[allow(dead_code)] // the parallel coordinator constructs this in Wave 3
pub struct LocklessTranspositionTable {
    table: Vec<AtomicSlot>,
}

/// One slot: the `key` checksum and the packed-entry `data`. All-zero is empty.
#[allow(dead_code)]
struct AtomicSlot {
    key: AtomicU64,
    data: AtomicU64,
}

#[allow(dead_code)]
impl AtomicSlot {
    fn empty() -> AtomicSlot {
        AtomicSlot {
            key: AtomicU64::new(0),
            data: AtomicU64::new(0),
        }
    }
}

#[allow(dead_code)] // reachable once the coordinator constructs the table (Wave 3)
impl LocklessTranspositionTable {
    // `data` bit layout, 60 of 64 bits used: best_move 16 | depth 8 | value 18 |
    // flag 2 | age 16. `best_move` occupies the low bits; 0 is the `None` sentinel
    // (`a1a1`, never legal).
    const DEPTH_SHIFT: u32 = 16;
    const VALUE_SHIFT: u32 = 24;
    const FLAG_SHIFT: u32 = 42;
    const AGE_SHIFT: u32 = 44;
    const MOVE_MASK: u64 = 0xFFFF;
    const DEPTH_MASK: u64 = 0xFF;
    const VALUE_MASK: u64 = 0x3_FFFF;
    const FLAG_MASK: u64 = 0x3;
    const AGE_MASK: u64 = 0xFFFF;
    /// Bits the signed `value` field occupies, for sign extension on unpack.
    const VALUE_BITS: u32 = 18;

    pub fn new() -> LocklessTranspositionTable {
        LocklessTranspositionTable {
            table: (0..TABLE_SIZE).map(|_| AtomicSlot::empty()).collect(),
        }
    }

    /// Pack a `HashEntry`'s fields (everything but the zobrist) into one 60-bit word.
    fn pack(entry: HashEntry) -> u64 {
        let best_move = entry.best_move.map_or(0, |mv| mv.0 as u64);
        let depth = (entry.depth as i8 as u8) as u64;
        let value = (entry.value as i64 as u64) & Self::VALUE_MASK;
        let flag = match entry.flag {
            Flag::Exact => 0,
            Flag::LowerBound => 1,
            Flag::UpperBound => 2,
        };
        let age = entry.age as u64;
        best_move
            | (depth << Self::DEPTH_SHIFT)
            | (value << Self::VALUE_SHIFT)
            | (flag << Self::FLAG_SHIFT)
            | (age << Self::AGE_SHIFT)
    }

    /// Decode a packed word; the zobrist is supplied by the caller (not stored).
    fn unpack(data: u64, zobrist: u64) -> HashEntry {
        let move_bits = (data & Self::MOVE_MASK) as u16;
        let best_move = (move_bits != 0).then_some(Move(move_bits));
        let depth = ((data >> Self::DEPTH_SHIFT) & Self::DEPTH_MASK) as u8 as i8 as i32;
        // Sign-extend the value: lift its high bit to bit 63, then arithmetic-shift back.
        let raw = (data >> Self::VALUE_SHIFT) & Self::VALUE_MASK;
        let value = ((raw << (64 - Self::VALUE_BITS)) as i64 >> (64 - Self::VALUE_BITS)) as i32;
        let flag = match (data >> Self::FLAG_SHIFT) & Self::FLAG_MASK {
            0 => Flag::Exact,
            1 => Flag::LowerBound,
            _ => Flag::UpperBound,
        };
        let age = ((data >> Self::AGE_SHIFT) & Self::AGE_MASK) as u16;
        HashEntry {
            zobrist,
            best_move,
            depth,
            value,
            flag,
            age,
        }
    }
}

impl Default for LocklessTranspositionTable {
    fn default() -> Self {
        LocklessTranspositionTable::new()
    }
}

impl TranspositionTable for LocklessTranspositionTable {
    fn probe(&self, zobrist: u64) -> Option<HashEntry> {
        let slot = &self.table[(zobrist % TABLE_SIZE as u64) as usize];
        let data = slot.data.load(Ordering::Relaxed);
        let key = slot.key.load(Ordering::Relaxed);
        // The checksum holds only when both words come from the same store.
        (key ^ data == zobrist).then(|| Self::unpack(data, zobrist))
    }

    fn replace(&self, entry: HashEntry) {
        let slot = &self.table[(entry.zobrist % TABLE_SIZE as u64) as usize];
        let stored = slot.data.load(Ordering::Relaxed);
        let stored_depth = ((stored >> Self::DEPTH_SHIFT) & Self::DEPTH_MASK) as u8 as i8 as i32;
        let stored_age = ((stored >> Self::AGE_SHIFT) & Self::AGE_MASK) as u16;
        // Best-effort replace-by-age-or-depth; an empty (all-zero) slot decodes to
        // age 0 / depth 0, so any real entry overwrites it. The race is speed-only:
        // a lost replacement costs nodes, never legality.
        if entry.age > stored_age || entry.depth > stored_depth {
            let data = Self::pack(entry);
            slot.key.store(entry.zobrist ^ data, Ordering::Relaxed);
            slot.data.store(data, Ordering::Relaxed);
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

    // --- Wave 2: the lockless parallel backend ---

    fn full_entry(
        zobrist: u64,
        best_move: Option<Move>,
        depth: i32,
        value: i32,
        flag: Flag,
        age: u16,
    ) -> HashEntry {
        HashEntry {
            zobrist,
            best_move,
            depth,
            value,
            flag,
            age,
        }
    }

    #[test]
    fn lockless_entry_round_trips_through_packing() {
        // Every field survives the 60-bit codec, including a None move, the depth
        // and value extremes (negative quiescence depth, ±mate), all three flags,
        // and the full 16-bit age range.
        let cases = [
            full_entry(0x1, None, 0, 0, Flag::Exact, 0),
            full_entry(
                0x2,
                Some(Move(0xFFFF)),
                64,
                99_999,
                Flag::LowerBound,
                65_535,
            ),
            full_entry(0x3, Some(Move(1)), -5, -99_999, Flag::UpperBound, 100),
            full_entry(0x4, Some(Move(0x0ABC)), 12, -54_321, Flag::Exact, 7),
        ];
        for entry in cases {
            let data = LocklessTranspositionTable::pack(entry);
            assert_eq!(
                LocklessTranspositionTable::unpack(data, entry.zobrist),
                entry
            );
        }
    }

    #[test]
    fn lockless_stores_and_probes() {
        let table = LocklessTranspositionTable::new();
        let stored = full_entry(0xDEAD_BEEF, Some(Move(0x1234)), 7, 42, Flag::Exact, 3);
        table.replace(stored);
        assert_eq!(table.probe(0xDEAD_BEEF), Some(stored));
        assert_eq!(table.probe(0xFEED_FACE), None);
    }

    #[test]
    fn lockless_rejects_a_torn_read() {
        // AC-3.2: a torn read — `key` from one store, `data` from another — fails
        // the key-XOR-data checksum and reads as a miss, never a wrong-position hit.
        let table = LocklessTranspositionTable::new();
        let zobrist = 0xDEAD_BEEF;
        let stored = full_entry(zobrist, Some(Move(0x1234)), 7, 42, Flag::Exact, 3);
        let intruder = full_entry(zobrist, Some(Move(0x5678)), 9, -88, Flag::LowerBound, 4);
        table.replace(stored);
        assert_eq!(table.probe(zobrist), Some(stored));
        // Overwrite only the data word, leaving the old key: the checksum breaks.
        let index = (zobrist % TABLE_SIZE as u64) as usize;
        table.table[index].data.store(
            LocklessTranspositionTable::pack(intruder),
            std::sync::atomic::Ordering::Relaxed,
        );
        assert_eq!(table.probe(zobrist), None);
    }

    #[test]
    fn lockless_keeps_the_deeper_entry() {
        let table = LocklessTranspositionTable::new();
        let zobrist = 0x99;
        let deep = full_entry(zobrist, None, 8, 10, Flag::Exact, 0);
        table.replace(deep);
        table.replace(full_entry(zobrist, None, 3, 20, Flag::Exact, 0));
        assert_eq!(table.probe(zobrist), Some(deep));
    }
}
