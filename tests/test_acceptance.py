"""Acceptance tests: drive the real production entrypoint, never a mock.

Steps spawn the UCI engine (src/main.py) as a subprocess and speak the protocol
over its stdin/stdout, exactly as lichess-bot does.
"""

import re
import subprocess
import sys
from pathlib import Path

import chess
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / "src" / "main.py"

scenarios("../features")


def run_engine(commands):
    return subprocess.run(
        [sys.executable, str(ENGINE)],
        input=commands,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )


@pytest.fixture
def uci_session():
    return {}


@given("the chess engine is available")
def engine_available():
    assert ENGINE.exists(), f"engine entrypoint missing: {ENGINE}"


@when(parsers.parse('it receives the "{command}" command'))
def receive_command(uci_session, command):
    result = run_engine(f"{command}\nquit\n")
    uci_session["stdout"] = result.stdout
    uci_session["returncode"] = result.returncode


@when("it is asked for a move from the starting position")
def ask_for_move(uci_session):
    result = run_engine("position startpos\ngo\nquit\n")
    uci_session["stdout"] = result.stdout
    uci_session["returncode"] = result.returncode


@then(parsers.parse('it replies "{token}"'))
def replies_with(uci_session, token):
    assert uci_session["returncode"] == 0, uci_session
    assert token in uci_session["stdout"], uci_session["stdout"]


@then("it returns a legal move")
def returns_legal_move(uci_session):
    assert uci_session["returncode"] == 0, uci_session
    match = re.search(r"bestmove (\S+)", uci_session["stdout"])
    assert match, uci_session["stdout"]
    move = match.group(1)
    assert chess.Move.from_uci(move) in chess.Board().legal_moves
