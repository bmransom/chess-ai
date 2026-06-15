import brandobot_core
from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, Field, ValidationError, field_validator

DEPTH = 3

app = Flask(__name__)
CORS(app)

# A single Searcher holds the transposition table across requests, as the
# original did. The HTTP server is single-threaded.
searcher = brandobot_core.Searcher()


class NextMoveRequest(BaseModel):
    fen: str
    # How many plies of the decision tree to capture for diagnostics; clamped to
    # the search depth by the core.
    tree_depth: int = Field(default=1, ge=1, le=8)

    @field_validator("fen")
    @classmethod
    def fen_must_be_legal(cls, value):
        if not brandobot_core.is_valid_fen(value):
            raise ValueError("invalid FEN")
        return value


class NextMoveResponse(BaseModel):
    move: str


@app.route("/next_move", methods=["POST"])
def next_move():
    try:
        body = NextMoveRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as error:
        return jsonify({"errors": validation_errors(error)}), 422

    searcher.set_fen(body.fen)
    move = searcher.next_move(DEPTH, capture_tree=True, tree_depth=body.tree_depth)
    return jsonify(NextMoveResponse(move=move).model_dump())


@app.route("/transposition_table", methods=["GET"])
def get_transposition_table():
    return jsonify(searcher.transposition_table())


@app.route("/decision_tree", methods=["GET"])
def get_decision_tree():
    tree = searcher.decision_tree()
    if tree is None:
        return jsonify({"error": "no decision tree captured"}), 404
    return jsonify(tree)


def validation_errors(error):
    return [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
        for item in error.errors()
    ]


def main():
    app.run()


if __name__ == "__main__":
    main()
