import io
import pathlib
import sys
from contextlib import redirect_stdout

import brandobot_core

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import communication  # noqa: E402


def test_bare_go_uses_the_default_depth_without_endgame_boost():
    searcher = brandobot_core.Searcher()
    searcher.set_fen("8/8/8/4k3/8/8/4K3/8 w - - 0 1")

    out = io.StringIO()
    with redirect_stdout(out):
        communication.go(searcher, 1, "go")

    assert out.getvalue().splitlines()[0].startswith("info depth 1 ")
