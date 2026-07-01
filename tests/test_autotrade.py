from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from trade_signal_app import autotrade


class AutoTradeCliTests(unittest.TestCase):
    def test_run_once_uses_shared_execution_gate(self) -> None:
        with patch("trade_signal_app.autotrade._run_trading_once", return_value={"mode": "paper"}) as run:
            self.assertEqual(autotrade.run_once(), {"mode": "paper"})

        run.assert_called_once_with(force_paper=False)

    def test_main_can_force_paper_run(self) -> None:
        with patch("trade_signal_app.autotrade._run_trading_once", return_value={"mode": "paper", "events": []}) as run:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                autotrade.main(["--paper"])

        run.assert_called_once_with(force_paper=True)
        self.assertEqual(json.loads(stdout.getvalue()), {"mode": "paper", "events": []})


if __name__ == "__main__":
    unittest.main()
