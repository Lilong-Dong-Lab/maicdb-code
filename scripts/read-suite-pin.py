#!/usr/bin/env python3
"""Read a suite signature from the single JSON pin source."""

import argparse
import json
from pathlib import Path
from typing import NoReturn


PIN_FILE = Path(__file__).resolve().parent.parent / "tests" / "suite-signatures.json"


def fail(message: str) -> NoReturn:
    raise SystemExit(f"read-suite-pin: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=("local", "novault", "notag"))
    parser.add_argument("field", nargs="?", choices=("passed", "collected"))
    args = parser.parse_args()

    try:
        pins = json.loads(PIN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read {PIN_FILE}: {error}")

    state = pins.get(args.state)
    if not isinstance(state, dict):
        fail(f"{args.state} must be an object")

    if args.field:
        value = state.get(args.field)
        if not isinstance(value, int) or isinstance(value, bool):
            fail(f"{args.state}.{args.field} must be an integer")
        if value < 0:
            fail(f"{args.state}.{args.field} must be non-negative")
        if args.field == "collected":
            print(f"{value} tests collected")
        else:
            print(value)
        return

    counts = [state.get(key) for key in ("passed", "skipped", "warnings")]
    valid = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in counts
    )
    if not valid:
        fail(f"{args.state} must contain non-negative integer counts")
    if args.state == "local":
        fail("local is a reference object, not a complete pytest summary")
    print(f"{counts[0]} passed, {counts[1]} skipped, {counts[2]} warning")


if __name__ == "__main__":
    main()
