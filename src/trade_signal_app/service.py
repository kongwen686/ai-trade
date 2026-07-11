from __future__ import annotations

from datetime import datetime, timedelta

from .binance_client import BinancePublicAPIError, BinanceSpotGateway, parse_ticker
from .community import CommunityScoreProvider
from .config import AppSettings
from .indicators import build_indicator_snapshot
from .models import MarketTicker, ScanSummary, TradeSignal
from .scoring import build_reasons, build_subscores, composite_score, compute_liquidity_score, grade_from_score
from .time_utils import now_app_time

STABLELIKE_BASES = {
    "AEUR",
    "BFUSD",
    "BUSD",
    "DAI",
    "EURI",
    "FDUSD",
    "GUSD",
    "PAX",
    "PYUSD",
    "RLUSD",
    "SUSD",
    "TUSD",
    "USD1",
    "USDC",
    "USDE",
    "USDJ",
    "USDP",
    "USDS",
    "USDT",
    "USTC",
}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
SCAN_LIQUIDITY_SPECIAL_BASES = ("BTC", "ETH", "XRP", "SOL", "BNB")
SCAN_LIQUIDITY_TIERS = (*SCAN_LIQUIDITY_SPECIAL_BASES, "top30", "alt")
SCAN_TOP_RANK_SIZE = 30
SCAN_CANDIDATE_RESERVE_SIZE = 8
FALLBACK_SCAN_BASES = (
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "DOGE",
    "ADA",
    "TRX",
    "LINK",
    "AVAX",
    "SUI",
    "TON",
    "LTC",
    "BCH",
    "DOT",
    "UNI",
    "NEAR",
    "APT",
    "ICP",
    "ETC",
    "FIL",
    "ARB",
    "OP",
    "ATOM",
    "AAVE",
    "INJ",
    "SEI",
    "TIA",
    "WLD",
    "ENA",
    "PEPE",
    "SHIB",
    "ZEC",
)


def scan_liquidity_profiles(
    source: object,
    *,
    alt_min_quote_volume: float | None = None,
    alt_min_trade_count: int | None = None,
) -> dict[str, dict[str, float | int]]:
    def value(key: str, default: float | int) -> float | int:
        raw = source.get(key, default) if isinstance(source, dict) else getattr(source, key, default)
        return type(default)(raw)

    alt_quote = float(
        alt_min_quote_volume
        if alt_min_quote_volume is not None
        else value("min_quote_volume", 10_000_000.0)
    )
    alt_trades = int(
        alt_min_trade_count
        if alt_min_trade_count is not None
        else value("min_trade_count", 3000)
    )
    profiles: dict[str, dict[str, float | int]] = {}
    for base in SCAN_LIQUIDITY_SPECIAL_BASES:
        key = base.lower()
        profiles[base] = {
            "min_quote_volume": float(value(f"{key}_min_quote_volume", alt_quote)),
            "min_trade_count": int(value(f"{key}_min_trade_count", alt_trades)),
        }
    profiles["top30"] = {
        "min_quote_volume": float(value("top30_min_quote_volume", alt_quote)),
        "min_trade_count": int(value("top30_min_trade_count", alt_trades)),
    }
    profiles["alt"] = {
        "min_quote_volume": alt_quote,
        "min_trade_count": alt_trades,
    }
    return profiles


def _ticker_liquidity_tier(ticker: MarketTicker, *, quote_asset: str, top_symbols: set[str]) -> str:
    normalized_quote = quote_asset.upper()
    base = ticker.symbol[: -len(normalized_quote)] if ticker.symbol.endswith(normalized_quote) else ticker.symbol
    return base if base in SCAN_LIQUIDITY_SPECIAL_BASES else "top30" if ticker.symbol in top_symbols else "alt"


def _liquidity_gate_status(ticker: MarketTicker, *, tier: str, threshold: dict[str, float | int]) -> dict[str, object]:
    min_quote_volume = float(threshold["min_quote_volume"])
    min_trade_count = int(threshold["min_trade_count"])
    volume_pass = ticker.quote_volume >= min_quote_volume
    trades_pass = ticker.trade_count >= min_trade_count
    issues = []
    if not volume_pass:
        issues.append(f"24H成交额 {ticker.quote_volume / 1_000_000:.1f}M < {min_quote_volume / 1_000_000:.1f}M")
    if not trades_pass:
        issues.append(f"24H成交笔数 {ticker.trade_count} < {min_trade_count}")
    eligible = volume_pass and trades_pass
    return {
        "tier": tier,
        "eligible": eligible,
        "volume_pass": volume_pass,
        "trades_pass": trades_pass,
        "message": "" if eligible else "仅扫描观察，不进入自动交易：" + "；".join(issues),
    }


def filter_tickers_by_liquidity_tier(
    tickers: list[MarketTicker],
    *,
    eligible_symbols: set[str],
    quote_asset: str,
    profile_source: object,
    alt_min_quote_volume: float | None = None,
    alt_min_trade_count: int | None = None,
) -> tuple[list[MarketTicker], dict[str, dict[str, float | int]], dict[str, dict[str, int]]]:
    ranked = sorted(
        [ticker for ticker in tickers if ticker.symbol in eligible_symbols],
        key=lambda item: item.quote_volume,
        reverse=True,
    )
    top_symbols = {ticker.symbol for ticker in ranked[:SCAN_TOP_RANK_SIZE]}
    profiles = scan_liquidity_profiles(
        profile_source,
        alt_min_quote_volume=alt_min_quote_volume,
        alt_min_trade_count=alt_min_trade_count,
    )
    stats = {tier: {"universe": 0, "eligible": 0} for tier in SCAN_LIQUIDITY_TIERS}
    filtered: list[MarketTicker] = []
    for ticker in ranked:
        tier = _ticker_liquidity_tier(ticker, quote_asset=quote_asset, top_symbols=top_symbols)
        stats[tier]["universe"] += 1
        threshold = profiles[tier]
        if (
            ticker.quote_volume >= float(threshold["min_quote_volume"])
            and ticker.trade_count >= int(threshold["min_trade_count"])
        ):
            filtered.append(ticker)
            stats[tier]["eligible"] += 1
    return filtered, profiles, stats


def select_tickers_for_scan(
    tickers: list[MarketTicker],
    *,
    eligible_symbols: set[str],
    quote_asset: str,
    profile_source: object,
    candidate_pool: int,
    alt_min_quote_volume: float | None = None,
    alt_min_trade_count: int | None = None,
) -> tuple[
    list[MarketTicker],
    list[MarketTicker],
    dict[str, dict[str, float | int]],
    dict[str, dict[str, int]],
    dict[str, dict[str, object]],
]:
    ranked = sorted(
        [ticker for ticker in tickers if ticker.symbol in eligible_symbols],
        key=lambda item: item.quote_volume,
        reverse=True,
    )
    qualified, profiles, stats = filter_tickers_by_liquidity_tier(
        ranked,
        eligible_symbols=eligible_symbols,
        quote_asset=quote_asset,
        profile_source=profile_source,
        alt_min_quote_volume=alt_min_quote_volume,
        alt_min_trade_count=alt_min_trade_count,
    )
    qualified_symbols = {ticker.symbol for ticker in qualified}
    selected = qualified[:candidate_pool]
    if len(selected) < candidate_pool:
        selected.extend(
            ticker
            for ticker in ranked
            if ticker.symbol not in qualified_symbols
        )
        selected = selected[:candidate_pool]

    top_symbols = {ticker.symbol for ticker in ranked[:SCAN_TOP_RANK_SIZE]}
    status_by_symbol = {}
    for ticker in selected:
        tier = _ticker_liquidity_tier(ticker, quote_asset=quote_asset, top_symbols=top_symbols)
        status_by_symbol[ticker.symbol] = _liquidity_gate_status(ticker, tier=tier, threshold=profiles[tier])
    return selected, qualified, profiles, stats, status_by_symbol


class SignalScanner:
    def __init__(
        self,
        gateway: BinanceSpotGateway,
        community_provider: CommunityScoreProvider,
        settings: AppSettings,
    ) -> None:
        self.gateway = gateway
        self.community_provider = community_provider
        self.settings = settings
        self._exchange_info_retry_after: datetime | None = None

    def scan(
        self,
        quote_asset: str | None = None,
        interval: str | None = None,
        candidate_pool: int | None = None,
        min_quote_volume: float | None = None,
        min_trade_count: int | None = None,
    ) -> tuple[ScanSummary, list[TradeSignal]]:
        quote_asset = (quote_asset or self.settings.quote_asset).upper()
        interval = interval or self.settings.interval
        candidate_pool = candidate_pool if candidate_pool is not None else self.settings.candidate_pool
        min_quote_volume = min_quote_volume if min_quote_volume is not None else self.settings.min_quote_volume
        min_trade_count = min_trade_count if min_trade_count is not None else self.settings.min_trade_count

        now = now_app_time()
        if self._exchange_info_retry_after and self._exchange_info_retry_after > now:
            eligible_symbols = self._fallback_symbols(quote_asset)
        else:
            try:
                exchange_info = self.gateway.exchange_info()
                eligible_symbols = self._eligible_symbols(exchange_info, quote_asset)
                self._exchange_info_retry_after = None
            except BinancePublicAPIError:
                self._exchange_info_retry_after = now + timedelta(seconds=self.settings.scan_ttl_seconds)
                eligible_symbols = self._fallback_symbols(quote_asset)
        ticker_rows = self.gateway.ticker24hr_symbols(sorted(eligible_symbols))
        tickers = [parse_ticker(row) for row in ticker_rows]
        selected, filtered, liquidity_profiles, liquidity_tier_stats, liquidity_status = select_tickers_for_scan(
            tickers,
            eligible_symbols=eligible_symbols,
            quote_asset=quote_asset,
            profile_source=self.settings,
            candidate_pool=candidate_pool + SCAN_CANDIDATE_RESERVE_SIZE,
            alt_min_quote_volume=min_quote_volume,
            alt_min_trade_count=min_trade_count,
        )
        target_candidate_count = min(candidate_pool, len(selected))
        self.community_provider.prepare([ticker.symbol for ticker in selected])

        kline_map = self.gateway.map_klines(
            [ticker.symbol for ticker in selected],
            interval=interval,
            limit=self.settings.kline_limit,
            max_workers=self.settings.max_workers,
        )

        ready: list[tuple] = []
        for ticker in selected:
            candles = kline_map.get(ticker.symbol)
            if not candles:
                continue
            try:
                indicators = build_indicator_snapshot(candles)
            except ValueError:
                continue
            ready.append((ticker, indicators, self.community_provider.get(ticker.symbol), liquidity_status[ticker.symbol]))
            if len(ready) >= candidate_pool:
                break

        if not ready:
            summary = ScanSummary(
                quote_asset=quote_asset,
                interval=interval,
                scanned_symbols=target_candidate_count,
                returned_signals=0,
                min_quote_volume=min_quote_volume,
                min_trade_count=min_trade_count,
                fetched_at=now_app_time(),
                eligible_symbols=len(filtered),
                candidate_symbols=target_candidate_count,
                candidate_pool=candidate_pool,
                liquidity_profiles=liquidity_profiles,
                liquidity_tier_stats=liquidity_tier_stats,
            )
            return summary, []

        quote_volumes = [ticker.quote_volume for ticker, _, _, _ in ready]
        trade_counts = [ticker.trade_count for ticker, _, _, _ in ready]
        signals: list[TradeSignal] = []
        now = now_app_time()

        for ticker, indicators, community_signal, status in ready:
            liquidity_score = compute_liquidity_score(
                ticker,
                quote_volumes,
                trade_counts,
                eligible=bool(status["eligible"]),
            )
            breakdown = build_subscores(
                ticker=ticker,
                indicators=indicators,
                liquidity_score=liquidity_score,
                community_signal=community_signal,
            )
            reasons, warnings = build_reasons(ticker, indicators, community_signal)
            liquidity_issue = str(status["message"])
            if liquidity_issue:
                warnings = [liquidity_issue, *warnings][:3]
            score = composite_score(breakdown)
            signals.append(
                TradeSignal(
                    symbol=ticker.symbol,
                    score=score,
                    grade=grade_from_score(score),
                    reasons=reasons,
                    warnings=warnings,
                    ticker=ticker,
                    indicators=indicators,
                    breakdown=breakdown,
                    liquidity_score=liquidity_score,
                    community_signal=community_signal,
                    fetched_at=now,
                    liquidity_eligible=bool(status["eligible"]),
                    liquidity_tier=str(status["tier"]),
                    liquidity_issue=liquidity_issue,
                )
            )

        signals.sort(key=lambda item: item.score, reverse=True)
        summary = ScanSummary(
            quote_asset=quote_asset,
            interval=interval,
            scanned_symbols=target_candidate_count,
            returned_signals=len(signals),
            min_quote_volume=min_quote_volume,
            min_trade_count=min_trade_count,
            fetched_at=now,
            eligible_symbols=len(filtered),
            candidate_symbols=target_candidate_count,
            candidate_pool=candidate_pool,
            liquidity_profiles=liquidity_profiles,
            liquidity_tier_stats=liquidity_tier_stats,
        )
        return summary, signals

    @staticmethod
    def _eligible_symbols(exchange_info: dict, quote_asset: str) -> set[str]:
        eligible: set[str] = set()
        for symbol in exchange_info.get("symbols", []):
            if symbol.get("status") != "TRADING":
                continue
            if not symbol.get("isSpotTradingAllowed", True):
                continue
            if symbol.get("quoteAsset") != quote_asset:
                continue
            base_asset = symbol.get("baseAsset", "")
            if base_asset in STABLELIKE_BASES:
                continue
            if any(base_asset.endswith(suffix) for suffix in LEVERAGED_SUFFIXES):
                continue
            eligible.add(symbol["symbol"])
        return eligible

    @staticmethod
    def _fallback_symbols(quote_asset: str) -> set[str]:
        quote = quote_asset.upper()
        return {f"{base}{quote}" for base in FALLBACK_SCAN_BASES if base != quote}
