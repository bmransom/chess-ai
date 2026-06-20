"""Render charts from a fair-match SPRT measurement log.

Parses the `progress` snapshots and the final `SPRT ...` summary that
`scripts/sprt.py --progress-every N` writes, and emits PNG charts for the
measurement report:

    pentanomial.png        outcome distribution over the five pair categories
    census-trajectory.png  census Elo and its confidence interval vs pairs
    llr-trajectory.png     the SPRT log-likelihood ratio vs pairs, with bounds

    python scripts/plot_measurement.py <log> <out-dir> [--old-elo 44 --old-margin 84]
"""

import argparse
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CATEGORIES = ["LL", "LD+DL", "LW+DD+WL", "DW+WD", "WW"]
CATEGORY_COLORS = ["#c0392b", "#e08e0b", "#7f8c8d", "#27ae60", "#1e8449"]

_PROGRESS = re.compile(
    r"progress pairs=(\d+) llr=([+-][\d.]+) counts=\[([\d, ]+)\] "
    r"elo=([+-][\d.]+) ci=\[([+-][\d.]+),([+-][\d.]+)\]"
)
_FINAL = re.compile(
    r"SPRT \[(-?\d+), (-?\d+)\] a=([\d.]+) b=([\d.]+): (\S+) after (\d+) pairs; "
    r"LLR ([+-][\d.]+); counts \[([\d, ]+)\]; "
    r"Elo ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\]"
)


def parse_log(path):
    """Return (config, progress, final) parsed from an SPRT log."""
    text = Path(path).read_text()
    progress = []
    for match in _PROGRESS.finditer(text):
        progress.append(
            {
                "pairs": int(match.group(1)),
                "llr": float(match.group(2)),
                "counts": [int(value) for value in match.group(3).split(",")],
                "elo": float(match.group(4)),
                "ci_low": float(match.group(5)),
                "ci_high": float(match.group(6)),
            }
        )
    final_match = _FINAL.search(text)
    if final_match is None:
        raise SystemExit("no final SPRT summary found in the log")
    final = {
        "elo0": int(final_match.group(1)),
        "elo1": int(final_match.group(2)),
        "alpha": float(final_match.group(3)),
        "beta": float(final_match.group(4)),
        "verdict": final_match.group(5),
        "pairs": int(final_match.group(6)),
        "llr": float(final_match.group(7)),
        "counts": [int(value) for value in final_match.group(8).split(",")],
        "elo": float(final_match.group(9)),
        "ci_low": float(final_match.group(10)),
        "ci_high": float(final_match.group(11)),
    }
    return final, progress


def plot_pentanomial(final, out):
    counts = final["counts"]
    fig, axis = plt.subplots(figsize=(6.4, 3.6))
    axis.bar(CATEGORIES, counts, color=CATEGORY_COLORS)
    for index, value in enumerate(counts):
        axis.text(index, value, str(value), ha="center", va="bottom", fontsize=9)
    decisive = counts[0] + counts[1] + counts[3] + counts[4]
    axis.set_title(
        f"Pentanomial outcomes over {final['pairs']} pairs "
        f"({decisive} decisive, {counts[2]} drawn)"
    )
    axis.set_ylabel("pair count")
    axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "pentanomial.png", dpi=140)
    plt.close(fig)


def plot_census_trajectory(final, progress, out):
    fig, axis = plt.subplots(figsize=(6.4, 3.6))
    pairs = [point["pairs"] for point in progress] or [final["pairs"]]
    elo = [point["elo"] for point in progress] or [final["elo"]]
    low = [point["ci_low"] for point in progress] or [final["ci_low"]]
    high = [point["ci_high"] for point in progress] or [final["ci_high"]]
    axis.axhspan(
        final["elo0"],
        final["elo1"],
        color="#bdc3c7",
        alpha=0.35,
        label=f"indifference region [{final['elo0']}, {final['elo1']}]",
    )
    axis.axhline(0, color="#7f8c8d", lw=0.8)
    axis.fill_between(pairs, low, high, color="#2980b9", alpha=0.2, label="95% CI")
    axis.plot(pairs, elo, color="#2980b9", lw=2, label="census Elo")
    axis.set_title("Census Elo estimate (candidate − baseline)")
    axis.set_xlabel("pairs")
    axis.set_ylabel("Elo")
    axis.legend(fontsize=8, loc="best")
    axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "census-trajectory.png", dpi=140)
    plt.close(fig)


def plot_llr_trajectory(final, progress, out):
    upper = math.log((1 - final["beta"]) / final["alpha"])
    lower = math.log(final["beta"] / (1 - final["alpha"]))
    fig, axis = plt.subplots(figsize=(6.4, 3.6))
    pairs = [point["pairs"] for point in progress] or [final["pairs"]]
    llr = [point["llr"] for point in progress] or [final["llr"]]
    axis.axhline(
        upper, color="#27ae60", ls="--", lw=1, label=f"accept H1 (+{upper:.2f})"
    )
    axis.axhline(
        lower, color="#c0392b", ls="--", lw=1, label=f"accept H0 ({lower:.2f})"
    )
    axis.axhline(0, color="#7f8c8d", lw=0.8)
    axis.plot(pairs, llr, color="#8e44ad", lw=2, label="LLR")
    axis.set_title("SPRT log-likelihood ratio")
    axis.set_xlabel("pairs")
    axis.set_ylabel("LLR")
    axis.legend(fontsize=8, loc="best")
    axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "llr-trajectory.png", dpi=140)
    plt.close(fig)


def plot_comparison(final, old_elo, old_margin, out):
    fig, axis = plt.subplots(figsize=(6.4, 2.6))
    rows = [
        (
            "old: 16 games, depth 4",
            old_elo,
            old_elo - old_margin,
            old_elo + old_margin,
            "#c0392b",
        ),
        (
            f"new: SPRT, {final['pairs']} pairs",
            final["elo"],
            final["ci_low"],
            final["ci_high"],
            "#2980b9",
        ),
    ]
    for index, (label, value, low, high, color) in enumerate(rows):
        axis.plot(
            [low, high], [index, index], color=color, lw=6, solid_capstyle="round"
        )
        axis.plot(value, index, "o", color="white", markeredgecolor=color, markersize=8)
        axis.text(
            value,
            index + 0.18,
            f"{value:+.0f} [{low:+.0f}, {high:+.0f}]",
            ha="center",
            fontsize=8,
        )
    axis.axvline(0, color="#7f8c8d", lw=0.8)
    axis.set_yticks([0, 1])
    axis.set_yticklabels([row[0] for row in rows])
    axis.set_ylim(-0.6, 1.6)
    axis.set_xlabel("Elo estimate (candidate − baseline)")
    axis.set_title("Measurement method: old vs new")
    axis.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "method-comparison.png", dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Chart a fair-match SPRT log.")
    parser.add_argument("log", help="SPRT measurement log (with progress snapshots)")
    parser.add_argument("out", help="output directory for the PNG charts")
    parser.add_argument("--old-elo", type=float, default=44.0, help="old-method Elo")
    parser.add_argument(
        "--old-margin", type=float, default=84.0, help="old-method ± margin"
    )
    args = parser.parse_args()

    final, progress = parse_log(args.log)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plot_pentanomial(final, out)
    plot_census_trajectory(final, progress, out)
    plot_llr_trajectory(final, progress, out)
    plot_comparison(final, args.old_elo, args.old_margin, out)
    print(
        f"wrote 4 charts to {out} (verdict: {final['verdict']}, {final['pairs']} pairs)"
    )


if __name__ == "__main__":
    main()
