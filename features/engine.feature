Feature: UCI chess engine
  brandobot speaks the UCI protocol over stdin/stdout. Every bridge — lichess-bot,
  a GUI, the acceptance harness — depends on this handshake.

  Scenario: the engine announces itself over UCI
    Given the chess engine is available
    When it receives the "uci" command
    Then it replies "uciok"

  Scenario: it reports a move and a principal variation under a movetime budget
    Given the chess engine is available
    When it searches the start position with "movetime 200"
    Then it replies "bestmove"
    And it reports a principal variation
