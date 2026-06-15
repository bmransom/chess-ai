"""Acceptance tests: drive the real production entrypoint, never a mock.

Steps spawn the UCI engine (src/main.py) as a subprocess and speak the protocol
over its stdin/stdout, exactly as lichess-bot does.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / "src" / "main.py"

scenarios("../features")


@pytest.fixture
def uci_session():
    return {}


@given("the chess engine is available")
def engine_available():
    assert ENGINE.exists(), f"engine entrypoint missing: {ENGINE}"


@when(parsers.parse('it receives the "{command}" command'))
def receive_command(uci_session, command):
    result = subprocess.run(
        [sys.executable, str(ENGINE)],
        input=f"{command}\nquit\n",
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    uci_session["stdout"] = result.stdout
    uci_session["returncode"] = result.returncode


@then(parsers.parse('it replies "{token}"'))
def replies_with(uci_session, token):
    assert uci_session["returncode"] == 0, uci_session
    assert token in uci_session["stdout"], uci_session["stdout"]
