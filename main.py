#!/usr/bin/env python3
"""
main.py
Single entrypoint for LCYcode.ai.

  python main.py          -> starts the GUI server on :8420
  python main.py cli       -> starts the terminal chat
"""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from lcycode.cli.main import main as cli_main
        cli_main()
    else:
        import uvicorn
        print("LCYcode.ai GUI starting at http://localhost:8420")
        uvicorn.run("lcycode.api.server:app", host="0.0.0.0", port=8420)


if __name__ == "__main__":
    main()
