"""Train the NNUE network on teacher-labeled data and export it to .nnue (BNN1).

Reads a compact numpy dataset built by `build_dataset.py` (per position: the active
768-feature indices for both perspectives, the White-positive centipawn score, and
the side to move), or a `<fen> | <cp> | <wdl>` text file. Trains a 768->256->1
perspective network on the Mac's GPU (PyTorch MPS) with an LR-decay schedule,
quantizes to the engine's integer format (QA/QB/SCALE), and writes the BNN1 file
nnue.rs loads. Batches are built on the GPU by scatter, so tens of millions of
positions train without a Python hot loop.

The architecture, quantization, and feature indexing mirror `core/src/nnue.rs`
exactly — verified after export via the `nnue_evaluate` entrypoint. See the
nnue-eval spec, Wave 2.

    .venv/bin/python scripts/train.py --data data/dataset --epochs 20 --out nets/net.nnue
"""

import argparse
import struct
import sys
from pathlib import Path

import chess
import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dataset import MAX_PIECES, features  # noqa: E402

# Architecture + quantization — must match core/src/nnue.rs exactly.
INPUT = 768
HIDDEN = 256
QA = 255
QB = 64
SCALE = 400
MAGIC = b"BNN1"
MAGIC2 = b"BNN2"  # adds a per-bucket output layer (mixture of experts)

ROOT = Path(__file__).resolve().parent.parent


def feature_indices(board):
    """Active (white-perspective, black-perspective) feature indices via
    python-chess — the reference used to verify the export."""
    white, black = [], []
    for square, piece in board.piece_map().items():
        piece_type = piece.piece_type - 1
        white.append((0 if piece.color == chess.WHITE else 1) * 384 + piece_type * 64 + square)
        black.append(
            (0 if piece.color == chess.BLACK else 1) * 384 + piece_type * 64 + (square ^ 56)
        )
    return white, black


def load_data(path):
    """Return (feats, score, stm) numpy arrays from a `build_dataset` directory or
    a `<fen> | <cp> | <wdl>` text file."""
    path = Path(path)
    if path.is_dir():
        return (
            np.load(path / "feats.npy", mmap_mode="r"),
            np.load(path / "score.npy"),
            np.load(path / "stm.npy"),
        )
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    feats = np.full((len(lines), 2 * MAX_PIECES), -1, dtype=np.int16)
    score = np.empty(len(lines), dtype=np.int16)
    stm = np.empty(len(lines), dtype=np.int8)
    kept = 0
    for line in lines:
        fen = line.split("|")[0].strip()
        white, black = features(fen.split(" ")[0])
        if len(white) > MAX_PIECES:
            continue
        feats[kept, : len(white)] = white
        feats[kept, MAX_PIECES : MAX_PIECES + len(black)] = black
        score[kept] = int(line.split("|")[1])
        stm[kept] = 1 if fen.split(" ")[1] == "w" else 0
        kept += 1
    return feats[:kept], score[:kept], stm[:kept]


def targets(score, stm, blend):
    """Side-to-move-relative target win probability:
    `blend·sigmoid(cp/SCALE) + (1−blend)·0.5`. The dump has no game result, so the
    `0.5` term is a neutral prior; train with `blend=1.0` for pure distillation."""
    sign = np.where(stm == 1, 1.0, -1.0).astype(np.float32)
    relative = score.astype(np.float32) * sign
    return (blend / (1.0 + np.exp(-relative / SCALE)) + (1.0 - blend) * 0.5).astype(np.float32)


def screlu(x):
    return torch.clamp(x, 0.0, 1.0) ** 2


class PerspectiveNet(nn.Module):
    """`(768 -> 256)x2 -> buckets`: one shared feature transformer, side-to-move and
    opponent accumulators concatenated, then `buckets` output heads. The position's
    material-indexed bucket selects which head's logit is used — a hard-gated mixture
    of experts (`buckets=1` is the plain dense net). `sigmoid` gives the win
    probability, `* SCALE` gives centipawns."""

    def __init__(self, buckets=1):
        super().__init__()
        self.ft = nn.Linear(INPUT, HIDDEN)
        self.out = nn.Linear(2 * HIDDEN, buckets)

    def forward(self, white, black, stm, bucket):
        w = self.ft(white)
        b = self.ft(black)
        accumulator_stm = stm * w + (1.0 - stm) * b
        accumulator_nstm = stm * b + (1.0 - stm) * w
        heads = self.out(torch.cat([screlu(accumulator_stm), screlu(accumulator_nstm)], dim=1))
        return heads.gather(1, bucket)


def make_batch(feats, target, stm, bucket, index):
    """Dense [B, 768] perspective inputs, built on-device by scatter from the
    padded feature-index rows (−1 padding contributes nothing). `feats`, `target`,
    `stm`, and `bucket` are already on the device, so batching never leaves the GPU."""
    rows = feats[index].long()
    white_idx, black_idx = rows[:, :MAX_PIECES], rows[:, MAX_PIECES:]
    size = rows.shape[0]
    white = torch.zeros(size, INPUT, device=rows.device)
    black = torch.zeros(size, INPUT, device=rows.device)
    white.scatter_add_(1, white_idx.clamp(min=0), (white_idx >= 0).float())
    black.scatter_add_(1, black_idx.clamp(min=0), (black_idx >= 0).float())
    return white, black, stm[index].unsqueeze(1), target[index].unsqueeze(1), bucket[index].unsqueeze(1)


def output_buckets(feats_t, buckets):
    """The material-indexed bucket for each position, mirroring `nnue.rs`
    `output_bucket`: piece count → `(count-1)/(32/buckets)`, clamped. Computed from
    the on-device feature rows (a perspective lists all pieces, so the active count
    in the first half is the piece count)."""
    divisor = max(32 // buckets, 1)
    piece_count = (feats_t[:, :MAX_PIECES] >= 0).sum(dim=1)
    return ((piece_count - 1) // divisor).clamp(0, buckets - 1).long()


def to_device_int16(array, device, chunk=10_000_000):
    """Copy a possibly-memmapped int16 array to `device` in chunks, so the full
    array is never held in (unified) RAM alongside the device copy — needed for the
    100M+ datasets on a 64 GB machine, where numpy and the MPS tensor share memory."""
    tensor = torch.empty(tuple(array.shape), dtype=torch.int16, device=device)
    for start in range(0, len(array), chunk):
        block = np.ascontiguousarray(array[start : start + chunk])
        tensor[start : start + len(block)] = torch.from_numpy(block).to(device)
    return tensor


def quantize(array, scale):
    return np.clip(np.round(array * scale), -32768, 32767).astype("<i2")


def export(model, path):
    """Quantize and write the file nnue.rs `from_bytes` reads — BNN1 for a dense net
    (1 bucket), BNN2 (a per-bucket output layer) for a mixture of experts."""
    model = model.cpu()
    feature_weights = model.ft.weight.detach().numpy()
    feature_bias = model.ft.bias.detach().numpy()
    output_weights = model.out.weight.detach().numpy()  # [buckets, 2*HIDDEN]
    output_bias = model.out.bias.detach().numpy()  # [buckets]
    buckets = output_weights.shape[0]

    if buckets == 1:
        blob = bytearray(MAGIC)
        blob += struct.pack("<5i", INPUT, HIDDEN, QA, QB, SCALE)
    else:
        blob = bytearray(MAGIC2)
        blob += struct.pack("<6i", INPUT, HIDDEN, buckets, QA, QB, SCALE)
    blob += quantize(feature_weights.T.reshape(-1), QA).tobytes()
    blob += quantize(feature_bias, QA).tobytes()
    for b in range(buckets):  # output weights, bucket-major
        blob += quantize(output_weights[b], QB).tobytes()
    for b in range(buckets):  # output bias, one per bucket
        blob += struct.pack("<i", int(np.clip(round(float(output_bias[b]) * QA * QB), -(2**31), 2**31 - 1)))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def verify(model, path, fens):
    """Compare the float model's White-positive eval to the engine's integer eval
    of the exported net — they must agree within quantization error."""
    import brandobot_core

    model = model.cpu().eval()
    buckets = model.out.weight.shape[0]
    divisor = max(32 // buckets, 1)
    worst = 0
    for fen in fens:
        board = chess.Board(fen)
        white, black = feature_indices(board)
        wd = torch.zeros(1, INPUT)
        wd[0, white] = 1.0
        bd = torch.zeros(1, INPUT)
        bd[0, black] = 1.0
        stm = torch.tensor([[1.0 if board.turn == chess.WHITE else 0.0]])
        bucket = min((len(board.piece_map()) - 1) // divisor, buckets - 1)
        with torch.no_grad():
            logit = model(wd, bd, stm, torch.tensor([[bucket]])).item()
        model_white = (SCALE * logit) if board.turn == chess.WHITE else -(SCALE * logit)
        engine_white = brandobot_core.nnue_evaluate(fen, str(path))
        worst = max(worst, abs(engine_white - model_white))
    print(f"verify: worst |engine - model| = {worst:.1f} cp")


def main():
    parser = argparse.ArgumentParser(description="Train and export the NNUE net.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "dataset")
    parser.add_argument("--out", type=Path, default=ROOT / "nets" / "net.nnue")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=16384)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--blend", type=float, default=1.0, help="teacher-vs-result weight (lambda)")
    parser.add_argument("--limit", type=int, default=None, help="train on a random N-position subset")
    parser.add_argument("--buckets", type=int, default=1, help="material-indexed output buckets (MoE)")
    args = parser.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    feats, score, stm = load_data(args.data)
    if args.limit and args.limit < len(feats):
        # a random subset is a representative sample of the (diverse) full set, so a
        # data-size sweep stays controlled — same pipeline, only the count varies.
        index = np.random.default_rng(0).permutation(len(feats))[: args.limit]
        feats, score, stm = feats[index], score[index], stm[index]
    count = len(feats)
    print(f"{count} positions, device={device}, blend={args.blend}, buckets={args.buckets}", file=sys.stderr)

    # Hold the whole dataset on the device (the M5 Pro's unified memory), so each
    # batch is a pure on-device gather + scatter — no per-step CPU↔GPU transfer.
    feats_t = to_device_int16(feats, device)
    del feats
    target_t = torch.from_numpy(targets(score, stm, args.blend)).to(device)
    stm_t = torch.from_numpy(stm.astype(np.float32)).to(device)
    bucket_t = output_buckets(feats_t, args.buckets)

    model = PerspectiveNet(args.buckets).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=args.lr * 0.02
    )

    for epoch in range(args.epochs):
        order = torch.randperm(count, device=device)
        total = 0.0
        for start in range(0, count, args.batch):
            index = order[start : start + args.batch]
            white, black, stm_b, target_b, bucket_b = make_batch(feats_t, target_t, stm_t, bucket_t, index)
            optimizer.zero_grad()
            loss = ((torch.sigmoid(model(white, black, stm_b, bucket_b)) - target_b) ** 2).mean()
            loss.backward()
            optimizer.step()
            total += loss.item() * index.numel()
        scheduler.step()
        print(
            f"epoch {epoch + 1}/{args.epochs}: loss {total / count:.5f} "
            f"lr {scheduler.get_last_lr()[0]:.2e}",
            file=sys.stderr,
        )

    path = export(model, args.out)
    print(f"wrote {path}")
    sample = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r1bq1rk1/2p2ppp/p1n1p3/1p2Pn2/3P4/2PB1N2/PP3PPP/RNBQ1RK1 b - - 0 1",
        "8/5K1p/8/8/8/7k/8/4q3 w - - 0 1",
    ]
    verify(model, path, sample)


if __name__ == "__main__":
    sys.exit(main())
