from __future__ import annotations

from datetime import datetime, timedelta

from .binance_client import BinancePublicAPIError, BinanceSpotGateway, parse_ticker
from .community import CommunityScoreProvider
from .config import AppSettings
from .indicators import build_indicator_snapshot
from .models import MarketTicker, ScanSummary, TradeSignal
from .scoring import build_reasons, build_subscores, composite_score, compute_liquidity_score, grade_from_score
from .time_utils import now_app_time

STABLELIKE_BASES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
SCAN_LIQUIDITY_SPECIAL_BASES = ("BTC", "ETH", "XRP", "SOL", "BNB")
SCAN_LIQUIDITY_TIERS = (*SCAN_LIQUIDITY_SPECIAL_BASES, "top30", "alt")
SCAN_TOP_RANK_SIZE = 30
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
    normalized_quote = quote_asset.upper()
    for ticker in ranked:
        base = ticker.symbol[: -len(normalized_quote)] if ticker.symbol.endswith(normalized_quote) else ticker.symbol
        tier = base if base in SCAN_LIQUIDITY_SPECIAL_BASES else "top30" if ticker.symbol in top_symbols else "alt"
        stats[tier]["universe"] += 1
        threshold = profiles[tier]
        if (
            ticker.quote_volume >= float(threshold["min_quote_volume"])
            and ticker.trade_count >= int(threshold["min_trade_count"])
        ):
            filtered.append(ticker)
            stats[tier]["eligible"] += 1
    return filtered, profiles, stats


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
        filtered, liquidity_profiles, liquidity_tier_stats = filter_tickers_by_liquidity_tier(
            tickers,
            eligible_symbols=eligible_symbols,
            quote_asset=quote_asset,
            profile_source=self.settings,
            alt_min_quote_volume=min_quote_volume,
            alt_min_trade_count=min_trade_count,
        )
        selected = filtered[:candidate_pool]
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
            ready.append((ticker, indicators, self.community_provider.get(ticker.symbol)))

        if not ready:
            summary = ScanSummary(
                quote_asset=quote_asset,
                interval=interval,
                scanned_symbols=len(selected),
                returned_signals=0,
                min_quote_volume=min_quote_volume,
                min_trade_count=min_trade_count,
                fetched_at=now_app_time(),
                eligible_symbols=len(filtered),
                candidate_symbols=len(selected),
                candidate_pool=candidate_pool,
                liquidity_profiles=liquidity_profiles,
                liquidity_tier_stats=liquidity_tier_stats,
            )
            return summary, []

        quote_volumes = [ticker.quote_volume for ticker, _, _ in ready]
        trade_counts = [ticker.trade_count for ticker, _, _ in ready]
        signals: list[TradeSignal] = []
        now = now_app_time()

        for ticker, indicators, community_signal in ready:
            liquidity_score = compute_liquidity_score(ticker, quote_volumes, trade_counts)
            breakdown = build_subscores(
                ticker=ticker,
                indicators=indicators,
                liquidity_score=liquidity_score,
                community_signal=community_signal,
            )
            reasons, warnings = build_reasons(ticker, indicators, community_signal)
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
                )
            )

        signals.sort(key=lambda item: item.score, reverse=True)
        summary = ScanSummary(
            quote_asset=quote_asset,
            interval=interval,
            scanned_symbols=len(selected),
            returned_signals=len(signals),
            min_quote_volume=min_quote_volume,
            min_trade_count=min_trade_count,
            fetched_at=now,
            eligible_symbols=len(filtered),
            candidate_symbols=len(selected),
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
