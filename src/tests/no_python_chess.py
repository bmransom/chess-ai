"""AC-7.1: the engine and its wrappers must not import python-chess. The Rust
core (brandobot_core) is the only source of chess logic."""

import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
ENGINE_MODULES = ["main.py", "communication.py", "api.py", "perft.py"]


class NoPythonChessTest(unittest.TestCase):
    def test_engine_modules_do_not_import_python_chess(self):
        for name in ENGINE_MODULES:
            source = (SRC / name).read_text()
            self.assertNotIn("import chess", source, name)
