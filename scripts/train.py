"""Train the NNUE network on teacher-labeled data and export it to .nnue (BNN1).

Reads gen_data.py's ``<fen> | <cp> | <wdl>`` records, trains a 768->256->1
perspective network on the Mac's GPU (PyTorch MPS), quantizes it to the engine's
integer format (QA/QB/SCALE), and writes the BNN1 file nnue.rs loads. The training
target blends the teacher's eval (mapped to a win probability) with the game
result by a lambda.

The architecture, quantization scales, and feature indexing mirror
``core/src/nnue.rs`` exactly, so the exported net evaluates identically in the
engine — verified after export via the `nnue_evaluate` entrypoint. See the
nnue-eval spec, Wave 2.

    .venv/bin/python scripts/train.py --data data/train.txt --out nets/net.nnue
"""

import argparse
import math
import struct
import sys
from pathlib import Path

import chess
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

# Architecture + quantization — must match core/src/nnue.rs exactly.
INPUT = 768
HIDDEN = 256
QA = 255
QB = 64
SCALE = 400
MAGIC = b"BNN1"

ROOT = Path(__file__).resolve().parent.parent


def feature_indices(board):
    """Active (white-perspective, black-perspective) feature indices, matching
    nnue.rs `feature_index`: block 0 for the perspective's own pieces, square
    vertically mirrored (`^ 56`) for Black's perspective."""
    white, black = [], []
    for square, piece in board.piece_map().items():
        piece_type = piece.piece_type - 1  # python-chess PAWN=1..KING=6 -> 0..5
        white.append((0 if piece.color == chess.WHITE else 1) * 384 + piece_type * 64 + square)
        black.append(
            (0 if piece.color == chess.BLACK else 1) * 384 + piece_type * 64 + (square ^ 56)
        )
    return white, black


def load_dataset(path, blend):
    """Parse records into per-position features, the side-to-move flag, and the
    side-to-move-relative target win probability."""
    rows = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        fen, cp_str, wdl_str = (part.strip() for part in line.split("|"))
        board = chess.Board(fen)
        stm_white = board.turn == chess.WHITE
        cp = int(cp_str) if stm_white else -int(cp_str)
        wdl = float(wdl_str) if stm_white else 1.0 - float(wdl_str)
        target = blend * (1.0 / (1.0 + math.exp(-cp / SCALE))) + (1.0 - blend) * wdl
        white, black = feature_indices(board)
        rows.append((white, black, 1.0 if stm_white else 0.0, target))
    return rows


def collate(batch):
    """Scatter the active feature indices into dense [B, 768] perspective inputs."""
    size = len(batch)
    white = torch.zeros(size, INPUT)
    black = torch.zeros(size, INPUT)
    for i, (w, b, _, _) in enumerate(batch):
        white[i, w] = 1.0
        black[i, b] = 1.0
    stm = torch.tensor([[row[2]] for row in batch])
    target = torch.tensor([[row[3]] for row in batch])
    return white, black, stm, target


def screlu(x):
    return torch.clamp(x, 0.0, 1.0) ** 2


class PerspectiveNet(nn.Module):
    """`(768 -> 256)x2 -> 1`: one shared feature transformer, side-to-move and
    opponent accumulators concatenated, a single output. Output is a logit;
    `sigmoid` gives the win probability, `* SCALE` gives centipawns."""

    def __init__(self):
        super().__init__()
        self.ft = nn.Linear(INPUT, HIDDEN)
        self.out = nn.Linear(2 * HIDDEN, 1)

    def forward(self, white, black, stm):
        w = self.ft(white)
        b = self.ft(black)
        accumulator_stm = stm * w + (1.0 - stm) * b
        accumulator_nstm = stm * b + (1.0 - stm) * w
        return self.out(torch.cat([screlu(accumulator_stm), screlu(accumulator_nstm)], dim=1))


def quantize(array, scale):
    return np.clip(np.round(array * scale), -32768, 32767).astype("<i2")


def export(model, path):
    """Quantize and write the BNN1 file nnue.rs `from_bytes` reads."""
    model = model.cpu()
    feature_weights = model.ft.weight.detach().numpy()  # [HIDDEN, INPUT]
    feature_bias = model.ft.bias.detach().numpy()  # [HIDDEN]
    output_weights = model.out.weight.detach().numpy()[0]  # [2*HIDDEN]
    output_bias = float(model.out.bias.detach().numpy()[0])

    blob = bytearray(MAGIC)
    blob += struct.pack("<5i", INPUT, HIDDEN, QA, QB, SCALE)
    blob += quantize(feature_weights.T.reshape(-1), QA).tobytes()  # feature-major [f*HIDDEN+h]
    blob += quantize(feature_bias, QA).tobytes()
    blob += quantize(output_weights, QB).tobytes()
    blob += struct.pack("<i", int(np.clip(round(output_bias * QA * QB), -(2**31), 2**31 - 1)))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def verify(model, path, fens):
    """Compare the float model's white-positive eval to the engine's integer eval
    of the exported net — they must agree within quantization error."""
    import brandobot_core

    model = model.cpu().eval()
    worst = 0
    for fen in fens:
        board = chess.Board(fen)
        white, black = feature_indices(board)
        wd = torch.zeros(1, INPUT)
        wd[0, white] = 1.0
        bd = torch.zeros(1, INPUT)
        bd[0, black] = 1.0
        stm = torch.tensor([[1.0 if board.turn == chess.WHITE else 0.0]])
        with torch.no_grad():
            logit = model(wd, bd, stm).item()
        model_cp = SCALE * logit
        model_white = model_cp if board.turn == chess.WHITE else -model_cp
        engine_white = brandobot_core.nnue_evaluate(fen, str(path))
        worst = max(worst, abs(engine_white - model_white))
        print(f"  {fen[:34]:34} model={model_white:+8.1f}  engine={engine_white:+6d}")
    print(f"verify: worst |engine - model| = {worst:.1f} cp (quantization error)")


def main():
    parser = argparse.ArgumentParser(description="Train and export the NNUE net.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "train.txt")
    parser.add_argument("--out", type=Path, default=ROOT / "nets" / "net.nnue")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--blend", type=float, default=0.7, help="teacher-vs-result target weight (lambda)"
    )
    args = parser.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    rows = load_dataset(args.data, args.blend)
    if not rows:
        raise SystemExit(f"no records in {args.data}; run scripts/gen_data.py first")
    print(f"{len(rows)} positions, device={device}, blend={args.blend}")

    loader = DataLoader(rows, batch_size=args.batch, shuffle=True, collate_fn=collate)
    model = PerspectiveNet().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    for epoch in range(args.epochs):
        total = 0.0
        for white, black, stm, target in loader:
            white, black, stm, target = (
                white.to(device),
                black.to(device),
                stm.to(device),
                target.to(device),
            )
            optimizer.zero_grad()
            loss = ((torch.sigmoid(model(white, black, stm)) - target) ** 2).mean()
            loss.backward()
            optimizer.step()
            total += loss.item() * white.shape[0]
        print(f"epoch {epoch + 1}/{args.epochs}: loss {total / len(rows):.5f}", file=sys.stderr)

    path = export(model, args.out)
    print(f"wrote {path}")
    verify(model, path, [row_fen for row_fen in sample_fens(args.data)])


def sample_fens(path, count=5):
    fens = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            fens.append(line.split("|")[0].strip())
        if len(fens) >= count:
            break
    return fens


if __name__ == "__main__":
    sys.exit(main())
