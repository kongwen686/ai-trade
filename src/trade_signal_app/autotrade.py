from __future__ import annotations

import argparse
import json
import time

from .main import _run_trading_once


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="trade-signal-autotrade", description="Run AI Trade auto execution.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Loop interval when --loop is enabled.")
    parser.add_argument("--loop", action="store_true", help="Run continuously until interrupted.")
    parser.add_argument("--paper", action="store_true", help="Force a protected paper run regardless of the saved execution mode.")
    return parser.parse_args(argv)


def run_once(*, force_paper: bool = False) -> dict[str, object]:
    return _run_trading_once(force_paper=force_paper)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    while True:
        print(json.dumps(run_once(force_paper=args.paper), ensure_ascii=False, indent=2), flush=True)
        if not args.loop:
            return
        time.sleep(max(1, args.interval_seconds))


if __name__ == "__main__":
    main()
