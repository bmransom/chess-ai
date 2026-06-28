"""Build a compact training dataset from Lichess eval parquet shards.

Converts the HuggingFace parquet shards in `data/hf/` into compact numpy arrays the
trainer holds in RAM: per position, the active 768-feature indices for both
perspectives (padded to 32 each with −1), the White-positive centipawn score, and
the side to move. At ~130 bytes/position this fits ~100M positions in ~13 GB — far
more than the text format — so we can train near the data regime real engines use
(Leorik: the same 768→256 net on 622M positions). The deepest eval per position is
kept; mates cap to ±`MATE_CP`. Feature indexing mirrors `nnue.rs` exactly.

    .venv/bin/python scripts/build_dataset.py --shards 8 --count 100000000 --out data/dataset
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label import MATE_CP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHARD_DIR = ROOT / "data" / "hf"
MAX_PIECES = 32  # a legal position has at most 32 pieces, i.e. 32 active features
PIECE = {"p": 0, "n": 1, "b": 2, "r": 3, "q": 4, "k": 5}


def features(board_field):
    """White- and black-perspective feature indices for a FEN board field,
    matching nnue.rs `feature_index`. Ranks run 8→1 in the FEN, so the first rank
    is squares 56–63; a1 = 0."""
    white, black = [], []
    rank, file = 7, 0
    for char in board_field:
        if char == "/":
            rank, file = rank - 1, 0
        elif char.isdigit():
            file += ord(char) - 48
        else:
            square = rank * 8 + file
            upper = char.isupper()
            piece = PIECE[char.lower()]
            white.append((0 if upper else 1) * 384 + piece * 64 + square)
            black.append((0 if not upper else 1) * 384 + piece * 64 + (square ^ 56))
            file += 1
    return white, black


def deepest(path, min_depth):
    """Deepest White-positive eval per position in a shard: a DataFrame of
    (fen, score)."""
    frame = pd.read_parquet(path, columns=["fen", "depth", "cp", "mate"])
    frame = frame[(frame["depth"] >= min_depth) & (frame["cp"].notna() | frame["mate"].notna())]
    score = np.where(frame["cp"].notna(), frame["cp"], np.where(frame["mate"] > 0, MATE_CP, -MATE_CP))
    frame = frame.assign(score=np.clip(score, -MATE_CP, MATE_CP))
    return frame.sort_values("depth").drop_duplicates("fen", keep="last")


def build(shards, count, min_depth, out):
    feats = np.full((count, 2 * MAX_PIECES), -1, dtype=np.int16)
    scores = np.empty(count, dtype=np.int16)
    stms = np.empty(count, dtype=np.int8)
    written = 0
    for shard in range(shards):
        frame = deepest(SHARD_DIR / f"{shard}.parquet", min_depth)
        for fen, score in zip(frame["fen"].to_numpy(), frame["score"].to_numpy()):
            board_field, side = fen.split(" ")[0], fen.split(" ")[1]
            white, black = features(board_field)
            if len(white) > MAX_PIECES:
                continue  # illegal position (>32 pieces) from a custom analysis board
            feats[written, : len(white)] = white
            feats[written, MAX_PIECES : MAX_PIECES + len(black)] = black
            scores[written] = score
            stms[written] = 1 if side == "w" else 0
            written += 1
            if written >= count:
                break
        print(f"shard {shard}: {written} positions", file=sys.stderr)
        if written >= count:
            break

    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "feats.npy", feats[:written])
    np.save(out / "score.npy", scores[:written])
    np.save(out / "stm.npy", stms[:written])
    return written


def main():
    parser = argparse.ArgumentParser(description="Build a compact NNUE training dataset.")
    parser.add_argument("--shards", type=int, default=8)
    parser.add_argument("--count", type=int, default=100_000_000)
    parser.add_argument("--min-depth", type=int, default=12)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "dataset")
    args = parser.parse_args()

    written = build(args.shards, args.count, args.min_depth, args.out)
    print(f"wrote {written} positions to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
