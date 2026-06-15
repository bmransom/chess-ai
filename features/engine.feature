Feature: UCI chess engine
  brandobot speaks the UCI protocol over stdin/stdout. Every bridge — lichess-bot,
  a GUI, the acceptance harness — depends on this handshake.

  Scenario: the engine announces itself over UCI
    Given the chess engine is available
    When it receives the "uci" command
    Then it replies "uciok"
