from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Candlestick:
    open_time: datetime
    close_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float


@dataclass(frozen=True)
class MarketTicker:
    symbol: str
    last_price: float
    price_change_percent: float
    quote_volume: float
    volume: float
    trade_count: int


@dataclass(frozen=True)
class CommunitySignal:
    score: float
    source: str
    mentions: int | None = None
    sentiment: float | None = None
    sample_size: int | None = None


@dataclass(frozen=True)
class IndicatorSnapshot:
    close_price: float
    ema_20: float
    ema_50: float
    ema_spread_pct: float
    price_vs_ema20_pct: float
    rsi_14: float
    macd: float
    macd_signal: float
    macd_hist: float
    bullish_macd_cross: bool
    macd_hist_rising: bool
    k_value: float
    d_value: float
    j_value: float
    bullish_kdj_cross: bool
    volume_ratio: float
    buy_pressure_ratio: float
    recent_change_pct: float
    closes: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ScoreBreakdown:
    trend: float
    momentum: float
    timing: float
    volume: float
    liquidity: float
    market: float
    community: float | None


@dataclass(frozen=True)
class TradeSignal:
    symbol: str
    score: float
    grade: str
    reasons: list[str]
    warnings: list[str]
    ticker: MarketTicker
    indicators: IndicatorSnapshot
    breakdown: ScoreBreakdown
    liquidity_score: float
    community_signal: CommunitySignal | None
    fetched_at: datetime


@dataclass(frozen=True)
class ScanSummary:
    quote_asset: str
    interval: str
    scanned_symbols: int
    returned_signals: int
    min_quote_volume: float
    min_trade_count: int
    fetched_at: datetime


@dataclass(frozen=True)
class ForwardReturnStat:
    horizon_bars: int
    signal_count: int
    avg_return_pct: float
    median_return_pct: float
    win_rate_pct: float
    best_return_pct: float
    worst_return_pct: float


@dataclass(frozen=True)
class BacktestSignalEvent:
    symbol: str
    interval: str
    entry_time: datetime
    entry_price: float
    score: float
    grade: str
    reasons: list[str]
    forward_returns_pct: dict[int, float] = field(default_factory=dict)
    signal_time: datetime | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    gross_return_pct: float | None = None
    realized_return_pct: float | None = None
    bars_held: int | None = None
    max_drawdown_pct: float | None = None
    max_runup_pct: float | None = None
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    capital_fraction_pct: float = 100.0
    effective_slippage_bps: float | None = None
    entry_fee_bps: float | None = None
    exit_fee_bps: float | None = None


@dataclass(frozen=True)
class TradePerformanceStat:
    trade_count: int
    avg_return_pct: float
    median_return_pct: float
    win_rate_pct: float
    best_return_pct: float
    worst_return_pct: float
    avg_bars_held: float
    avg_max_drawdown_pct: float
    profit_factor: float


@dataclass(frozen=True)
class EquityPoint:
    time: datetime
    equity: float
    drawdown_pct: float
    period_return_pct: float


@dataclass(frozen=True)
class BacktestReport:
    symbol: str
    interval: str
    candle_count: int
    evaluated_bars: int
    signal_count: int
    lookback_bars: int
    score_threshold: float
    cooldown_bars: int
    fee_bps: float
    slippage_bps: float
    capital_fraction_pct: float
    generated_at: datetime
    fee_model: str = "flat"
    fee_source: str = "manual"
    maker_fee_bps: float = 10.0
    taker_fee_bps: float = 10.0
    entry_fee_role: str = "taker"
    exit_fee_role: str = "taker"
    fee_discount_pct: float = 0.0
    stats: list[ForwardReturnStat] = field(default_factory=list)
    trade_stat: TradePerformanceStat | None = None
    equity_curve: list[EquityPoint] = field(default_factory=list)
    events: list[BacktestSignalEvent] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioSelection:
    entry_time: datetime
    picks: list[BacktestSignalEvent] = field(default_factory=list)
    average_forward_returns_pct: dict[int, float] = field(default_factory=dict)
    exit_time: datetime | None = None
    gross_return_pct: float | None = None
    realized_return_pct: float | None = None
    capital_fraction_pct: float = 0.0
    capital_per_pick_pct: float = 0.0


@dataclass(frozen=True)
class PortfolioReturnStat:
    horizon_bars: int
    batch_count: int
    pick_count: int
    avg_batch_return_pct: float
    median_batch_return_pct: float
    avg_pick_return_pct: float
    win_rate_pct: float
    best_batch_return_pct: float
    worst_batch_return_pct: float


@dataclass(frozen=True)
class PortfolioBacktestReport:
    interval: str
    top_n: int
    symbol_count: int
    batch_count: int
    pick_count: int
    score_threshold: float
    fee_bps: float
    slippage_bps: float
    capital_fraction_pct: float
    generated_at: datetime
    fee_model: str = "flat"
    fee_source: str = "manual"
    maker_fee_bps: float = 10.0
    taker_fee_bps: float = 10.0
    entry_fee_role: str = "taker"
    exit_fee_role: str = "taker"
    fee_discount_pct: float = 0.0
    stats: list[PortfolioReturnStat] = field(default_factory=list)
    trade_stat: TradePerformanceStat | None = None
    equity_curve: list[EquityPoint] = field(default_factory=list)
    selections: list[PortfolioSelection] = field(default_factory=list)


def utc_datetime_from_epoch(epoch: int) -> datetime:
    scale = 1_000_000 if epoch > 10_000_000_000_000 else 1_000
    return datetime.fromtimestamp(epoch / scale, tz=timezone.utc)
