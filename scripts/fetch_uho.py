"""Fetch the UHO opening book for fair-match SPRT runs.

Downloads UHO_4060_v4 (unbalanced human openings) from the public, CC0-licensed
`official-stockfish/books` repository, extracts it to `bench/`, and verifies the
position count against the source. The book is large and reproducible, so it is
not committed; run this once before a full SPRT.

    Source:    https://github.com/official-stockfish/books
    Archive:   UHO_4060_v4.epd.zip
    License:   CC0 1.0 Universal
    Positions: 241670 (verified after extraction)
"""

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/official-stockfish/books/master/"
    "UHO_4060_v4.epd.zip"
)
LICENSE = "CC0 1.0 Universal"
ARCHIVE_MEMBER = "UHO_4060_v4.epd"
EXPECTED_POSITIONS = 241_670
DESTINATION = Path(__file__).resolve().parent.parent / "bench" / "uho_4060_v4.epd"


def fetch(url=SOURCE_URL, destination=DESTINATION, expected=EXPECTED_POSITIONS):
    """Download, extract, verify the position count, and write the book; return
    its path. Raises if the count differs from the recorded source figure."""
    with urllib.request.urlopen(url) as response:  # noqa: S310 (public, pinned URL)
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    text = archive.read(ARCHIVE_MEMBER).decode("utf-8")
    positions = [line.strip() for line in text.splitlines() if line.strip()]
    if len(positions) != expected:
        raise SystemExit(
            f"position count {len(positions)} != recorded {expected}; the source "
            "book changed -- verify and update the provenance before recording"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# UHO_4060_v4 unbalanced-human-openings book\n"
        f"# Source: {SOURCE_URL}\n"
        f"# License: {LICENSE}\n"
        f"# Positions: {len(positions)} (verified)\n"
    )
    destination.write_text(header + "\n".join(positions) + "\n")
    return destination


def main():
    path = fetch()
    print(f"wrote {path} ({EXPECTED_POSITIONS} positions, {LICENSE})")


if __name__ == "__main__":
    sys.exit(main())
