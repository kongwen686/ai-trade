from __future__ import annotations

import argparse
import json
import time

from .app_state import AppState
from .config import BASE_DIR, SETTINGS
from .main import _serialize_trading_report
from .trading import AutoTrader, TradingStateStore

RUNTIME_CONFIG_PATH = BASE_DIR / "data" / "runtime_config.json"
TRADING_STATE_PATH = BASE_DIR / "data" / "trading_state.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="trade-signal-autotrade", description="Run AI Trade auto execution.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Loop interval when --loop is enabled.")
    parser.add_argument("--loop", action="store_true", help="Run continuously until interrupted.")
    return parser.parse_args(argv)


def run_once() -> dict[str, object]:
    app_state = AppState(SETTINGS, RUNTIME_CONFIG_PATH)
    runtime_config, scanner = app_state.snapshot()
    trader = AutoTrader(scanner=scanner, state_store=TradingStateStore(TRADING_STATE_PATH))
    return _serialize_trading_report(trader.run_once(runtime_config.autotrade_defaults))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    while True:
        print(json.dumps(run_once(), ensure_ascii=False, indent=2), flush=True)
        if not args.loop:
            return
        time.sleep(max(1, args.interval_seconds))


if __name__ == "__main__":
    main()
