from __future__ import annotations

from .models import BacktestReport, PortfolioBacktestReport, TradeSignal


def sparkline_points(values: list[float], width: int = 160, height: int = 44) -> str:
    if len(values) < 2:
        return ""
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum or 1.0
    step = width / (len(values) - 1)
    points = []
    for index, value in enumerate(values):
        x = index * step
        y = height - (((value - minimum) / span) * height)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def equity_sparkline(points: list[float]) -> str:
    return sparkline_points(points, width=220, height=56)


def format_signal_row(signal: TradeSignal) -> dict:
    return {
        "symbol": signal.symbol,
        "score": signal.score,
        "grade": signal.grade,
        "reasons": signal.reasons,
        "warnings": signal.warnings,
        "quote_volume_m": signal.ticker.quote_volume / 1_000_000,
        "price_change_percent": signal.ticker.price_change_percent,
        "rsi_14": signal.indicators.rsi_14,
        "ema_spread_pct": signal.indicators.ema_spread_pct,
        "volume_ratio": signal.indicators.volume_ratio,
        "macd_hist": signal.indicators.macd_hist,
        "community_score": None if signal.community_signal is None else signal.community_signal.score,
        "community_source": None if signal.community_signal is None else signal.community_signal.source,
        "community_mentions": None if signal.community_signal is None else signal.community_signal.mentions,
        "community_sentiment": None if signal.community_signal is None else signal.community_signal.sentiment,
        "community_sample_size": None if signal.community_signal is None else signal.community_signal.sample_size,
        "breakdown": {
            "trend": signal.breakdown.trend,
            "momentum": signal.breakdown.momentum,
            "timing": signal.breakdown.timing,
            "volume": signal.breakdown.volume,
            "liquidity": signal.breakdown.liquidity,
            "market": signal.breakdown.market,
            "community": signal.breakdown.community,
        },
        "sparkline_points": sparkline_points(signal.indicators.closes),
    }


def format_backtest_report(report: BacktestReport) -> dict:
    return {
        "symbol": report.symbol,
        "interval": report.interval,
        "candle_count": report.candle_count,
        "evaluated_bars": report.evaluated_bars,
        "signal_count": report.signal_count,
        "score_threshold": report.score_threshold,
        "fee_bps": report.fee_bps,
        "fee_model": report.fee_model,
        "fee_source": report.fee_source,
        "maker_fee_bps": report.maker_fee_bps,
        "taker_fee_bps": report.taker_fee_bps,
        "entry_fee_role": report.entry_fee_role,
        "exit_fee_role": report.exit_fee_role,
        "fee_discount_pct": report.fee_discount_pct,
        "slippage_bps": report.slippage_bps,
        "capital_fraction_pct": report.capital_fraction_pct,
        "trade_stat": None
        if report.trade_stat is None
        else {
            "trade_count": report.trade_stat.trade_count,
            "avg_return_pct": report.trade_stat.avg_return_pct,
            "median_return_pct": report.trade_stat.median_return_pct,
            "win_rate_pct": report.trade_stat.win_rate_pct,
            "best_return_pct": report.trade_stat.best_return_pct,
            "worst_return_pct": report.trade_stat.worst_return_pct,
            "avg_bars_held": report.trade_stat.avg_bars_held,
            "avg_max_drawdown_pct": report.trade_stat.avg_max_drawdown_pct,
            "profit_factor": report.trade_stat.profit_factor,
        },
        "stats": [
            {
                "horizon_bars": stat.horizon_bars,
                "signal_count": stat.signal_count,
                "avg_return_pct": stat.avg_return_pct,
                "median_return_pct": stat.median_return_pct,
                "win_rate_pct": stat.win_rate_pct,
                "best_return_pct": stat.best_return_pct,
                "worst_return_pct": stat.worst_return_pct,
            }
            for stat in report.stats
        ],
        "events": [
            {
                "entry_time": event.entry_time.isoformat(),
                "exit_time": None if event.exit_time is None else event.exit_time.isoformat(),
                "entry_price": event.entry_price,
                "exit_price": event.exit_price,
                "score": event.score,
                "grade": event.grade,
                "reasons": event.reasons[:3],
                "exit_reason": event.exit_reason,
                "gross_return_pct": event.gross_return_pct,
                "realized_return_pct": event.realized_return_pct,
                "bars_held": event.bars_held,
                "max_drawdown_pct": event.max_drawdown_pct,
                "effective_slippage_bps": event.effective_slippage_bps,
                "entry_fee_bps": event.entry_fee_bps,
                "exit_fee_bps": event.exit_fee_bps,
            }
            for event in report.events[-8:]
        ],
        "equity_points": [point.equity for point in report.equity_curve],
        "equity_sparkline": equity_sparkline([point.equity for point in report.equity_curve]),
        "final_equity": report.equity_curve[-1].equity if report.equity_curve else 1.0,
        "max_drawdown_pct": min((point.drawdown_pct for point in report.equity_curve), default=0.0),
    }


def format_portfolio_report(report: PortfolioBacktestReport) -> dict:
    return {
        "interval": report.interval,
        "top_n": report.top_n,
        "symbol_count": report.symbol_count,
        "batch_count": report.batch_count,
        "pick_count": report.pick_count,
        "score_threshold": report.score_threshold,
        "fee_bps": report.fee_bps,
        "fee_model": report.fee_model,
        "fee_source": report.fee_source,
        "maker_fee_bps": report.maker_fee_bps,
        "taker_fee_bps": report.taker_fee_bps,
        "entry_fee_role": report.entry_fee_role,
        "exit_fee_role": report.exit_fee_role,
        "fee_discount_pct": report.fee_discount_pct,
        "slippage_bps": report.slippage_bps,
        "capital_fraction_pct": report.capital_fraction_pct,
        "trade_stat": None
        if report.trade_stat is None
        else {
            "trade_count": report.trade_stat.trade_count,
            "avg_return_pct": report.trade_stat.avg_return_pct,
            "median_return_pct": report.trade_stat.median_return_pct,
            "win_rate_pct": report.trade_stat.win_rate_pct,
            "best_return_pct": report.trade_stat.best_return_pct,
            "worst_return_pct": report.trade_stat.worst_return_pct,
            "avg_bars_held": report.trade_stat.avg_bars_held,
            "avg_max_drawdown_pct": report.trade_stat.avg_max_drawdown_pct,
            "profit_factor": report.trade_stat.profit_factor,
        },
        "stats": [
            {
                "horizon_bars": stat.horizon_bars,
                "batch_count": stat.batch_count,
                "pick_count": stat.pick_count,
                "avg_batch_return_pct": stat.avg_batch_return_pct,
                "median_batch_return_pct": stat.median_batch_return_pct,
                "avg_pick_return_pct": stat.avg_pick_return_pct,
                "win_rate_pct": stat.win_rate_pct,
                "best_batch_return_pct": stat.best_batch_return_pct,
                "worst_batch_return_pct": stat.worst_batch_return_pct,
            }
            for stat in report.stats
        ],
        "selections": [
            {
                "entry_time": selection.entry_time.isoformat(),
                "exit_time": None if selection.exit_time is None else selection.exit_time.isoformat(),
                "gross_return_pct": selection.gross_return_pct,
                "realized_return_pct": selection.realized_return_pct,
                "capital_fraction_pct": selection.capital_fraction_pct,
                "capital_per_pick_pct": selection.capital_per_pick_pct,
                "picks": [
                    {
                        "symbol": pick.symbol,
                        "grade": pick.grade,
                        "score": pick.score,
                        "realized_return_pct": pick.realized_return_pct,
                    }
                    for pick in selection.picks
                ],
            }
            for selection in report.selections[-8:]
        ],
        "equity_points": [point.equity for point in report.equity_curve],
        "equity_sparkline": equity_sparkline([point.equity for point in report.equity_curve]),
        "final_equity": report.equity_curve[-1].equity if report.equity_curve else 1.0,
        "max_drawdown_pct": min((point.drawdown_pct for point in report.equity_curve), default=0.0),
    }
