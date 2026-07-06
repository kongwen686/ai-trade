from __future__ import annotations

from datetime import datetime, timedelta

from .binance_client import BinancePublicAPIError, BinanceSpotGateway, parse_ticker
from .community import CommunityScoreProvider
from .config import AppSettings
from .indicators import build_indicator_snapshot
from .models import ScanSummary, TradeSignal
from .scoring import build_reasons, build_subscores, composite_score, compute_liquidity_score, grade_from_score
from .time_utils import now_app_time

STABLELIKE_BASES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI"}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
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
        candidate_pool = candidate_pool or self.settings.candidate_pool
        min_quote_volume = min_quote_volume or self.settings.min_quote_volume
        min_trade_count = min_trade_count or self.settings.min_trade_count

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
        filtered = [
            ticker
            for ticker in tickers
            if ticker.symbol in eligible_symbols
            and ticker.quote_volume >= min_quote_volume
            and ticker.trade_count >= min_trade_count
        ]
        filtered.sort(key=lambda item: item.quote_volume, reverse=True)
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
