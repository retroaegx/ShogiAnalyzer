"""Small USI peer that retains its old position after rejecting an illegal move."""
import sys

for raw in sys.stdin:
    command = raw.strip()
    if command == "usi":
        print("id name Regression engine", flush=True)
        print("usiok", flush=True)
    elif command == "isready":
        print("readyok", flush=True)
    elif command.startswith("position ") and ("7g7e" in command or "2g2f" in command):
        # Also reject a legal move to exercise unexpected engine-side rejection.
        print("info string Error! : Illegal Input Move : rejected", flush=True)
    elif command == "go infinite":
        print("info depth 12 score cp 150 pv 7g7f", flush=True)
    elif command == "stop":
        print("bestmove 7g7f", flush=True)
    elif command == "quit":
        break
