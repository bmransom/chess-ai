Feature: choosing a move
  brandobot's reason for existing: given a position, return a legal move. Every
  entrypoint — the UCI engine and the HTTP API — must produce one. This is the
  shared outcome contract; each runner proves it through its own surface.

  Scenario: it returns a legal move from the starting position
    Given the chess engine is available
    When it is asked for a move from the starting position
    Then it returns a legal move
