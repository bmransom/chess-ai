"""Fetch teacher-labeled positions from the Lichess evaluations database.

Reads the HuggingFace mirror of the Lichess eval dump — hundreds of millions of
positions already scored by Stockfish — and converts a sample to the trainer's
``<fen> | <cp> | <wdl>`` format. This is a far larger, higher-quality, near-free
alternative to brandobot self-play.

The mirror serves ~20 parquet shards over a fast CDN (the lichess.org `.zst` is
throttled to ~0.7 MB/s). Each shard is FEN-sorted and spans the full position
range, so one shard is already a diverse sample. The data is denormalized (one row
per position and depth), so we keep the *deepest* eval per position. Lichess `cp`
is White-positive (matching our convention); mates cap to ±`MATE_CP`. The dump
carries no game result, so `wdl` is a placeholder — train with ``--blend 1.0``
(pure distillation from the eval). FENs omit move clocks; we pad them.

    Source:  https://huggingface.co/datasets/Lichess/chess-position-evaluations
    License: CC0 1.0 Universal

    .venv/bin/python scripts/fetch_lichess_evals.py --count 5000000 --out data/lichess.txt
"""

import argparse
import random
import sys
import urllib.request
from pathlib import Path

import chess
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from label import MATE_CP  # noqa: E402

SHARD_URL = (
    "https://huggingface.co/api/datasets/Lichess/chess-position-evaluations"
    "/parquet/default/train/{index}.parquet"
)
ROOT = Path(__file__).resolve().parent.parent
SHARD_DIR = ROOT / "data" / "hf"


def shard_path(index):
    """Download parquet shard `index` to `data/hf/` if absent; return its path."""
    path = SHARD_DIR / f"{index}.parquet"
    if path.exists():
        return path
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading shard {index} ...", file=sys.stderr)
    request = urllib.request.Request(
        SHARD_URL.format(index=index), headers={"User-Agent": "brandobot/1.0"}
    )
    with urllib.request.urlopen(request) as response, path.open("wb") as handle:  # noqa: S310
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    return path


def deepest_per_position(path, min_depth):
    """One White-positive centipawn score per position — the deepest eval, with
    mates capped to ±MATE_CP. Returns a list of (fen, score)."""
    frame = pd.read_parquet(path, columns=["fen", "depth", "cp", "mate"])
    frame = frame[(frame["depth"] >= min_depth) & (frame["cp"].notna() | frame["mate"].notna())]
    score = np.where(
        frame["cp"].notna(), frame["cp"], np.where(frame["mate"] > 0, MATE_CP, -MATE_CP)
    )
    frame = frame.assign(score=score)
    # The shard is FEN-sorted; sorting by depth then keeping the last row per FEN
    # leaves the deepest eval for each position.
    frame = frame.sort_values("depth").drop_duplicates("fen", keep="last")
    frame["score"] = frame["score"].clip(-MATE_CP, MATE_CP).astype("int64")
    return list(zip(frame["fen"].tolist(), frame["score"].tolist()))


def main():
    parser = argparse.ArgumentParser(description="Fetch Lichess eval positions for training.")
    parser.add_argument("--count", type=int, default=5_000_000, help="quiet positions to write")
    parser.add_argument("--shards", type=int, default=1, help="parquet shards to draw from")
    parser.add_argument("--min-depth", type=int, default=12, help="skip evals shallower than this")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "lichess.txt")
    args = parser.parse_args()

    positions = []
    for index in range(args.shards):
        positions += deepest_per_position(shard_path(index), args.min_depth)
    print(f"{len(positions)} unique positions; filtering to quiet", file=sys.stderr)
    random.Random(args.seed).shuffle(positions)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.out.open("w") as handle:
        for fen, score in positions:
            full = fen + " 0 1" if fen.count(" ") == 3 else fen
            try:
                board = chess.Board(full)
            except ValueError:
                continue
            # The deep Lichess eval already resolves tactics, so we only drop
            # in-check positions. Rejecting every position with a capture available
            # (as for self-play data) would over-select sparse endgames.
            if board.is_check():
                continue
            handle.write(f"{board.fen()} | {score} | 0.5\n")
            written += 1
            if written % 100_000 == 0:
                print(f"{written} quiet positions", file=sys.stderr)
            if written >= args.count:
                break
    print(f"wrote {written} positions to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
