"""Fetch the Stockfish teacher for NNUE training-data labeling.

Downloads a pinned, official Stockfish release binary, installs it to `bin/`, and
verifies it answers the UCI handshake. Stockfish is the teacher: its evaluation
labels the self-play positions the NNUE network learns from (knowledge
distillation). The binary is large and reproducible, so it is not committed; run
this once before generating a training set.

The pinned version anchors the whole teacher pipeline — change `RELEASE` and
`VERSION` together to retrain against a different teacher, and record the new
identity with the dataset (per the nnue-eval spec, AC-2.3).

    Source:   https://github.com/official-stockfish/Stockfish/releases
    Release:  sf_17.1
    License:  GPL-3.0-or-later (the binary; only its eval labels are used)
"""

import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RELEASE = "sf_17.1"
VERSION = "Stockfish 17.1"
LICENSE = "GPL-3.0-or-later"
BASE_URL = "https://github.com/official-stockfish/Stockfish/releases/download"
DESTINATION = Path(__file__).resolve().parent.parent / "bin" / "stockfish"

# Official release asset per platform; keyed by (system, machine). Each release
# ships one tar per micro-architecture — the conservative, widely-compatible
# build is chosen for each.
ASSETS = {
    ("Darwin", "arm64"): "stockfish-macos-m1-apple-silicon.tar",
    ("Darwin", "x86_64"): "stockfish-macos-x86-64-avx2.tar",
    ("Linux", "x86_64"): "stockfish-ubuntu-x86-64-avx2.tar",
    ("Linux", "aarch64"): "stockfish-android-armv8.tar",
}


def asset_name(system=None, machine=None):
    """The release asset for this platform, or raise with a clear message."""
    system = system or platform.system()
    machine = machine or platform.machine()
    try:
        return ASSETS[(system, machine)]
    except KeyError:
        raise SystemExit(
            f"no pinned Stockfish asset for {system}/{machine}; add one to ASSETS "
            f"from the {RELEASE} release before provisioning"
        )


def verify_uci(binary):
    """Run the binary's UCI handshake; return its reported `id name`. Raises if it
    does not answer `uciok`."""
    result = subprocess.run(
        [str(binary)],
        input="uci\nquit\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if "uciok" not in result.stdout:
        raise SystemExit(f"{binary} did not answer the UCI handshake")
    for line in result.stdout.splitlines():
        if line.startswith("id name "):
            return line[len("id name ") :].strip()
    return "unknown"


def fetch(destination=DESTINATION, release=RELEASE):
    """Download, extract, install, and UCI-verify the teacher; return its path."""
    url = f"{BASE_URL}/{release}/{asset_name()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "stockfish.tar"
        with urllib.request.urlopen(url) as response:  # noqa: S310 (public, pinned URL)
            archive.write_bytes(response.read())
        with tarfile.open(archive) as tar:
            tar.extractall(work, filter="data")
        binary = next(
            path
            for path in Path(work).rglob("stockfish*")
            if path.is_file() and path.stat().st_mode & 0o111
        )
        destination.write_bytes(binary.read_bytes())
        destination.chmod(0o755)
    identity = verify_uci(destination)
    return destination, identity


def main():
    path, identity = fetch()
    print(f"wrote {path} ({identity}, {RELEASE}, {LICENSE})")
    if VERSION not in identity:
        print(
            f"warning: reported '{identity}' does not contain '{VERSION}'; the "
            "release may have moved -- verify the provenance before recording",
            file=sys.stderr,
        )


if __name__ == "__main__":
    sys.exit(main())
