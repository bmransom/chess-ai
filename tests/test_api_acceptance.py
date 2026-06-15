"""HTTP acceptance: drive the real Flask API as a client, never a mock.

Runs the shared move outcome Scenario through the HTTP entrypoint, and checks the
JSON contract directly: validation, the transposition-table listing, and the
gated decision tree.
"""

import sys
from pathlib import Path

import chess
import pytest
from pytest_bdd import given, scenarios, then, when

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from api import app, searcher  # noqa: E402

scenarios("../features/move.feature")


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def api_session():
    return {}


# --- the shared outcome Scenario, through HTTP ---


@given("the chess engine is available")
def engine_available(client):
    assert client is not None


@when("it is asked for a move from the starting position")
def ask_for_move(client, api_session):
    api_session["response"] = client.post(
        "/next_move", json={"fen": chess.STARTING_FEN}
    )


@then("it returns a legal move")
def returns_legal_move(api_session):
    response = api_session["response"]
    assert response.status_code == 200, response.get_data(as_text=True)
    move = response.get_json()["move"]
    assert chess.Move.from_uci(move) in chess.Board(chess.STARTING_FEN).legal_moves


# --- the JSON contract ---


def test_invalid_fen_returns_422():
    response = app.test_client().post("/next_move", json={"fen": "not a fen"})
    assert response.status_code == 422


def test_missing_fen_returns_422():
    response = app.test_client().post("/next_move", json={})
    assert response.status_code == 422


def test_transposition_table_lists_entries():
    client = app.test_client()
    client.post("/next_move", json={"fen": chess.STARTING_FEN})
    response = client.get("/transposition_table")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)


def test_decision_tree_returned_after_search():
    client = app.test_client()
    client.post("/next_move", json={"fen": chess.STARTING_FEN})
    response = client.get("/decision_tree")
    assert response.status_code == 200
    assert "moves" in response.get_json()


def test_decision_tree_depth_one_has_no_children():
    client = app.test_client()
    client.post("/next_move", json={"fen": chess.STARTING_FEN, "tree_depth": 1})
    tree = client.get("/decision_tree").get_json()
    assert tree["moves"]
    assert all(node["children"] == [] for node in tree["moves"])


def test_decision_tree_depth_two_expands_children():
    client = app.test_client()
    client.post("/next_move", json={"fen": chess.STARTING_FEN, "tree_depth": 2})
    tree = client.get("/decision_tree").get_json()
    assert any(node["children"] for node in tree["moves"])


def test_invalid_tree_depth_returns_422():
    response = app.test_client().post(
        "/next_move", json={"fen": chess.STARTING_FEN, "tree_depth": 0}
    )
    assert response.status_code == 422


def test_decision_tree_404_when_none_captured():
    searcher.new_game()
    response = app.test_client().get("/decision_tree")
    assert response.status_code == 404
