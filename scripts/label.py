"""Label positions with the Stockfish teacher for NNUE training (distillation).

Drives the provisioned teacher (`bin/stockfish`, see `fetch_stockfish.py`) over
UCI to score positions. The teacher's evaluation is the training target the NNUE
network learns to predict. Only quiet positions are kept, so the static-evaluation
target is meaningful (the network reads no search).

Scores are white-positive centipawns, matching the engine's own evaluation and the
NNUE module, with mate scores capped to a finite bound (the NNUE `EVAL_LIMIT`).
This module is the labeling primitive; the self-play generation (`gen_data.py`)
builds on it to write plain `<fen> | <cp> | <wdl>` records (nnue-eval spec, task 2.2).
"""

import sys
from pathlib import Path

import chess
import chess.engine

TEACHER = Path(__file__).resolve().parent.parent / "bin" / "stockfish"
DEFAULT_DEPTH = 8
# Mate scores cap to this finite bound, matching the NNUE eval clamp so the target
# range and the network's output range agree.
MATE_CP = 30_000


def is_quiet(board):
    """True when the side to move is not in check and has no capture available, so
    a static evaluation matches a searched one."""
    if board.is_check():
        return False
    return not any(board.is_capture(move) for move in board.legal_moves)


def teacher_eval(board, engine, depth=DEFAULT_DEPTH):
    """The teacher's white-positive centipawn score for `board`, mate-capped."""
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    return info["score"].white().score(mate_score=MATE_CP)


def open_teacher(path=TEACHER):
    """Open the teacher engine, or raise pointing at the provisioning script."""
    if not path.exists():
        raise SystemExit(
            f"teacher not found at {path}; run scripts/fetch_stockfish.py first"
        )
    return chess.engine.SimpleEngine.popen_uci(str(path))


def main():
    """Demonstrate labeling: score a few opening positions through the teacher."""
    lines = ["", "e2e4", "e2e4 e7e5", "e2e4 e7e5 g1f3", "e2e4 d7d5"]
    with open_teacher() as engine:
        for line in lines:
            board = chess.Board()
            for uci in line.split():
                board.push_uci(uci)
            label = "startpos" if not line else line
            print(
                f"{label:<22} quiet={is_quiet(board)!s:<5} "
                f"teacher_cp={teacher_eval(board, engine):+d}"
            )


if __name__ == "__main__":
    sys.exit(main())
