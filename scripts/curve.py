"""Elo-vs-data-size curve: train NNUE nets on increasing random subsets of one
built dataset and SPRT each vs PeSTO, with everything else fixed (same pipeline,
epochs, LR schedule). Resumable — skips sizes already in the results file — and
re-plots after each point.

    .venv/bin/python scripts/curve.py --data data/dataset --sizes 5 20 50 100
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
ELO = re.compile(r"Elo ([+-]?\d+(?:\.\d+)?) \[([+-]?\d+(?:\.\d+)?), ([+-]?\d+(?:\.\d+)?)\]")


def train(data, size, epochs, out):
    subprocess.run(
        [PY, str(ROOT / "scripts/train.py"), "--data", str(data), "--limit", str(size),
         "--epochs", str(epochs), "--blend", "1.0", "--out", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def sprt(net, nodes, pairs):
    """Run sprt.py and return (elo, lo, hi) from its census estimate."""
    proc = subprocess.run(
        [PY, str(ROOT / "scripts/sprt.py"),
         "--engine1", f"{PY} {ROOT / 'src/main.py'} --net {net}",
         "--engine2", f"{PY} {ROOT / 'src/main.py'}",
         "--nodes", str(nodes), "--max-pairs", str(pairs), "--max-moves", "130"],
        capture_output=True, text=True,
    )
    match = ELO.search(proc.stdout + proc.stderr)
    if not match:
        raise RuntimeError("could not parse SPRT Elo:\n" + (proc.stdout + proc.stderr)[-800:])
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def plot(results, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    results = sorted(results, key=lambda r: r["size"])
    x = [r["size"] for r in results]
    y = [r["elo"] for r in results]
    yerr = [[r["elo"] - r["lo"] for r in results], [r["hi"] - r["elo"] for r in results]]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axhline(0, color="#888", ls="--", lw=1.2)
    ax.text(x[0], 6, "PeSTO baseline", color="#666", fontsize=9)
    ax.errorbar(x, y, yerr=yerr, fmt="o-", capsize=5, color="#2ca02c", lw=2, ms=8)
    ax.set_xscale("log")
    ax.set_xlabel("training positions (log scale)")
    ax.set_ylabel("Elo vs PeSTO  (16k nodes/move)")
    ax.set_title("NNUE Elo vs training-data size (controlled — same pipeline)")
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Elo-vs-data-size curve.")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "dataset")
    parser.add_argument("--sizes", type=int, nargs="+", default=[5, 20, 50, 100], help="millions")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--nodes", type=int, default=16000)
    parser.add_argument("--pairs", type=int, default=60)
    parser.add_argument("--results", type=Path, default=ROOT / "data" / "curve_results.json")
    parser.add_argument(
        "--chart", type=Path, default=ROOT / "roadmap/specs/nnue-eval/assets/elo-vs-data-controlled.png"
    )
    args = parser.parse_args()

    results = json.loads(args.results.read_text()) if args.results.exists() else []
    done = {r["size"] for r in results}
    for millions in args.sizes:
        size = millions * 1_000_000
        if size in done:
            continue
        net = ROOT / "nets" / f"curve_{millions}M.nnue"
        print(f"--- {millions}M: training ---", file=sys.stderr)
        train(args.data, size, args.epochs, net)
        elo, lo, hi = sprt(net, args.nodes, args.pairs)
        results.append({"size": size, "millions": millions, "elo": elo, "lo": lo, "hi": hi})
        args.results.write_text(json.dumps(results, indent=2))
        plot(results, args.chart)
        print(f"{millions}M: Elo {elo:+.0f} [{lo:+.0f}, {hi:+.0f}]", file=sys.stderr)
    print(f"curve complete: {len(results)} points -> {args.chart}")


if __name__ == "__main__":
    sys.exit(main())
