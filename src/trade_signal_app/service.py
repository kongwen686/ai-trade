from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from .binance_client import BinancePublicAPIError, BinanceSpotGateway, parse_ticker
from .community import CommunityScoreProvider
from .config import AppSettings
from .indicators import build_indicator_snapshot
from .models import Candlestick, MarketActivityProfile, MarketTicker, ScanSummary, TradeSignal
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
ACTIVITY_WINDOWS_BY_INTERVAL = {
    "15m": (1,),
    "1h": (1,),
    "2h": (1, 2),
    "4h": (1, 2, 4),
    "8h": (1, 2, 4, 8),
    "12h": (1, 2, 4, 8, 12),
    "1d": (1, 2, 4, 8, 12),
}
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


def activity_windows_for_interval(interval: str) -> tuple[int, ...]:
    return ACTIVITY_WINDOWS_BY_INTERVAL.get(interval.lower(), ACTIVITY_WINDOWS_BY_INTERVAL["4h"])


def _longest_adjacent_match(windows: tuple[int, ...], matched: set[int]) -> int:
    longest = 0
    current = 0
    for window in windows:
        if window in matched:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def analyze_market_activity(
    candles: list[Candlestick],
    *,
    interval: str,
    baseline_hours: int,
    surge_ratio: float,
    trade_surge_ratio: float,
    contraction_ratio: float,
    trade_contraction_ratio: float,
    min_consecutive_windows: int,
    now: datetime | None = None,
) -> MarketActivityProfile:
    windows = activity_windows_for_interval(interval)
    max_window = max(windows)
    current_time = now or now_app_time()
    closed = [candle for candle in candles if candle.close_time <= current_time]
    minimum_baseline = min(24, baseline_hours)
    if len(closed) < max_window + minimum_baseline:
        return MarketActivityProfile(windows_hours=list(windows))

    baseline_end = len(closed) - max_window
    baseline_start = max(0, baseline_end - baseline_hours)
    baseline = closed[baseline_start:baseline_end]
    baseline_quote = median([candle.quote_volume for candle in baseline]) if baseline else 0.0
    baseline_trades = median([candle.trade_count for candle in baseline]) if baseline else 0.0
    if baseline_quote <= 0 or baseline_trades <= 0:
        return MarketActivityProfile(windows_hours=list(windows))

    volume_ratios: dict[int, float] = {}
    trade_ratios: dict[int, float] = {}
    surge_windows: set[int] = set()
    contraction_windows: set[int] = set()
    for window in windows:
        recent = closed[-window:]
        quote_per_hour = sum(candle.quote_volume for candle in recent) / window
        trades_per_hour = sum(candle.trade_count for candle in recent) / window
        volume_ratios[window] = quote_per_hour / baseline_quote
        trade_ratios[window] = trades_per_hour / baseline_trades
        if volume_ratios[window] >= surge_ratio and trade_ratios[window] >= trade_surge_ratio:
            surge_windows.add(window)
        if volume_ratios[window] <= contraction_ratio and trade_ratios[window] <= trade_contraction_ratio:
            contraction_windows.add(window)

    surge_streak = _longest_adjacent_match(windows, surge_windows)
    contraction_streak = _longest_adjacent_match(windows, contraction_windows)
    required_streak = min(max(1, min_consecutive_windows), len(windows))
    if surge_streak >= required_streak:
        regime = "surge"
        matched = sorted(surge_windows)
        label = "连续放量 " + "/".join(f"{window}H" for window in matched)
        normalization_window = max(matched)
        consecutive = surge_streak
    elif contraction_streak >= required_streak:
        regime = "contraction"
        matched = sorted(contraction_windows)
        label = "连续缩量 " + "/".join(f"{window}H" for window in matched)
        normalization_window = max(matched)
        consecutive = contraction_streak
    else:
        regime = "normal"
        matched = []
        label = "量能常态"
        normalization_window = max_window
        consecutive = max(surge_streak, contraction_streak)

    normalized = closed[-normalization_window:]
    normalized_quote_volume_24h = sum(candle.quote_volume for candle in normalized) / normalization_window * 24
    normalized_trade_count_24h = round(sum(candle.trade_count for candle in normalized) / normalization_window * 24)
    return MarketActivityProfile(
        regime=regime,
        label=label,
        windows_hours=list(windows),
        matched_windows=matched,
        volume_ratios={window: round(value, 4) for window, value in volume_ratios.items()},
        trade_ratios={window: round(value, 4) for window, value in trade_ratios.items()},
        consecutive_windows=consecutive,
        max_volume_ratio=max(volume_ratios.values(), default=1.0),
        max_trade_ratio=max(trade_ratios.values(), default=1.0),
        normalized_quote_volume_24h=normalized_quote_volume_24h,
        normalized_trade_count_24h=normalized_trade_count_24h,
    )


def _liquidity_gate_status(
    ticker: MarketTicker,
    *,
    tier: str,
    threshold: dict[str, float | int],
    activity: MarketActivityProfile | None = None,
    dynamic_enabled: bool = False,
    liquidity_floor_ratio: float = 0.2,
    normalized_threshold_ratio: float = 0.5,
) -> dict[str, object]:
    min_quote_volume = float(threshold["min_quote_volume"])
    min_trade_count = int(threshold["min_trade_count"])
    volume_pass = ticker.quote_volume >= min_quote_volume
    trades_pass = ticker.trade_count >= min_trade_count
    issues = []
    if not volume_pass:
        issues.append(f"24H成交额 {ticker.quote_volume / 1_000_000:.1f}M < {min_quote_volume / 1_000_000:.1f}M")
    if not trades_pass:
        issues.append(f"24H成交笔数 {ticker.trade_count} < {min_trade_count}")
    fixed_eligible = volume_pass and trades_pass
    dynamic_floor_pass = bool(
        activity
        and ticker.quote_volume >= min_quote_volume * liquidity_floor_ratio
        and ticker.trade_count >= min_trade_count * liquidity_floor_ratio
    )
    normalized_pass = bool(
        activity
        and activity.normalized_quote_volume_24h >= min_quote_volume * normalized_threshold_ratio
        and activity.normalized_trade_count_24h >= min_trade_count * normalized_threshold_ratio
    )
    dynamic_override = bool(
        dynamic_enabled
        and not fixed_eligible
        and activity
        and activity.regime == "surge"
        and dynamic_floor_pass
        and normalized_pass
    )
    eligible = fixed_eligible or dynamic_override
    if dynamic_override:
        message = ""
        eligibility_reason = f"{activity.label}，动态替代固定24H门槛"
    elif eligible:
        message = ""
        eligibility_reason = "固定24H流动性达标"
    else:
        message = "仅扫描观察，不进入自动交易：" + "；".join(issues)
        if activity and activity.regime == "surge" and not dynamic_floor_pass:
            message += "；突然放量但低于动态安全底线"
        elif activity and activity.regime == "surge" and not normalized_pass:
            message += "；近期折算活跃度仍不足"
        eligibility_reason = ""
    return {
        "tier": tier,
        "eligible": eligible,
        "fixed_eligible": fixed_eligible,
        "dynamic_override": dynamic_override,
        "dynamic_floor_pass": dynamic_floor_pass,
        "normalized_pass": normalized_pass,
        "volume_pass": volume_pass,
        "trades_pass": trades_pass,
        "message": message,
        "eligibility_reason": eligibility_reason,
        "activity": activity,
    }


def _activity_discovery_tickers(
    tickers: list[MarketTicker],
    *,
    quote_asset: str,
    profiles: dict[str, dict[str, float | int]],
    qualified_symbols: set[str],
    discovery_pool: int,
    candidate_pool: int,
) -> list[MarketTicker]:
    ranked = sorted(tickers, key=lambda item: item.quote_volume, reverse=True)
    top_symbols = {ticker.symbol for ticker in ranked[:SCAN_TOP_RANK_SIZE]}
    qualified = [ticker for ticker in ranked if ticker.symbol in qualified_symbols]

    def threshold_coverage(ticker: MarketTicker) -> tuple[float, float]:
        tier = _ticker_liquidity_tier(ticker, quote_asset=quote_asset, top_symbols=top_symbols)
        threshold = profiles[tier]
        volume_floor = max(float(threshold["min_quote_volume"]), 1.0)
        trades_floor = max(int(threshold["min_trade_count"]), 1)
        coverage = min(ticker.quote_volume / volume_floor, ticker.trade_count / trades_floor)
        return coverage, ticker.quote_volume

    underqualified = sorted(
        [ticker for ticker in ranked if ticker.symbol not in qualified_symbols],
        key=threshold_coverage,
        reverse=True,
    )
    size = min(len(ranked), max(candidate_pool, discovery_pool))
    qualified_budget = min(len(qualified), max(candidate_pool, size // 2))
    selected = [*qualified[:qualified_budget], *underqualified[: size - qualified_budget]]
    if len(selected) < size:
        selected_symbols = {ticker.symbol for ticker in selected}
        selected.extend(ticker for ticker in ranked if ticker.symbol not in selected_symbols)
    return selected[:size]


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
    activity_by_symbol: dict[str, MarketActivityProfile] | None = None,
    dynamic_activity_enabled: bool = False,
    activity_liquidity_floor_ratio: float = 0.2,
    activity_normalized_threshold_ratio: float = 0.5,
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
    activity_by_symbol = activity_by_symbol or {}
    qualified_symbols = {ticker.symbol for ticker in qualified}
    top_symbols = {ticker.symbol for ticker in ranked[:SCAN_TOP_RANK_SIZE]}
    all_status: dict[str, dict[str, object]] = {}
    for ticker in ranked:
        tier = _ticker_liquidity_tier(ticker, quote_asset=quote_asset, top_symbols=top_symbols)
        status = _liquidity_gate_status(
            ticker,
            tier=tier,
            threshold=profiles[tier],
            activity=activity_by_symbol.get(ticker.symbol),
            dynamic_enabled=dynamic_activity_enabled,
            liquidity_floor_ratio=activity_liquidity_floor_ratio,
            normalized_threshold_ratio=activity_normalized_threshold_ratio,
        )
        all_status[ticker.symbol] = status
        if status["dynamic_override"]:
            stats[tier]["dynamic_eligible"] = stats[tier].get("dynamic_eligible", 0) + 1

    dynamic_candidates = sorted(
        [ticker for ticker in ranked if bool(all_status[ticker.symbol]["dynamic_override"])],
        key=lambda item: (
            activity_by_symbol[item.symbol].consecutive_windows,
            activity_by_symbol[item.symbol].max_volume_ratio,
            activity_by_symbol[item.symbol].max_trade_ratio,
        ),
        reverse=True,
    )
    surge_observations = sorted(
        [
            ticker
            for ticker in ranked
            if ticker.symbol not in qualified_symbols
            and not bool(all_status[ticker.symbol]["dynamic_override"])
            and getattr(activity_by_symbol.get(ticker.symbol), "regime", "") == "surge"
        ],
        key=lambda item: activity_by_symbol[item.symbol].max_volume_ratio,
        reverse=True,
    )
    contraction_observations = sorted(
        [
            ticker
            for ticker in ranked
            if ticker.symbol not in qualified_symbols
            and getattr(activity_by_symbol.get(ticker.symbol), "regime", "") == "contraction"
        ],
        key=lambda item: activity_by_symbol[item.symbol].consecutive_windows,
        reverse=True,
    )
    ordered_groups = (dynamic_candidates, qualified, surge_observations, contraction_observations, ranked)
    selected = []
    selected_symbols: set[str] = set()
    for group in ordered_groups:
        for ticker in group:
            if ticker.symbol in selected_symbols:
                continue
            selected.append(ticker)
            selected_symbols.add(ticker.symbol)
            if len(selected) >= candidate_pool:
                break
        if len(selected) >= candidate_pool:
            break

    status_by_symbol = {ticker.symbol: all_status[ticker.symbol] for ticker in selected}
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
        ranked_tickers = sorted(
            [ticker for ticker in tickers if ticker.symbol in eligible_symbols],
            key=lambda item: item.quote_volume,
            reverse=True,
        )
        fixed_qualified, preliminary_profiles, _ = filter_tickers_by_liquidity_tier(
            ranked_tickers,
            eligible_symbols=eligible_symbols,
            quote_asset=quote_asset,
            profile_source=self.settings,
            alt_min_quote_volume=min_quote_volume,
            alt_min_trade_count=min_trade_count,
        )
        activity_by_symbol: dict[str, MarketActivityProfile] = {}
        activity_discovery_count = 0
        if self.settings.dynamic_activity_enabled and ranked_tickers:
            discovery_tickers = _activity_discovery_tickers(
                ranked_tickers,
                quote_asset=quote_asset,
                profiles=preliminary_profiles,
                qualified_symbols={ticker.symbol for ticker in fixed_qualified},
                discovery_pool=self.settings.activity_discovery_pool,
                candidate_pool=candidate_pool + SCAN_CANDIDATE_RESERVE_SIZE,
            )
            activity_discovery_count = len(discovery_tickers)
            activity_limit = self.settings.activity_baseline_hours + max(activity_windows_for_interval(interval)) + 2
            activity_kline_map = self.gateway.map_klines(
                [ticker.symbol for ticker in discovery_tickers],
                interval="1h",
                limit=activity_limit,
                max_workers=self.settings.max_workers,
            )
            for ticker in discovery_tickers:
                candles = activity_kline_map.get(ticker.symbol)
                if not candles:
                    continue
                activity_by_symbol[ticker.symbol] = analyze_market_activity(
                    candles,
                    interval=interval,
                    baseline_hours=self.settings.activity_baseline_hours,
                    surge_ratio=self.settings.activity_surge_ratio,
                    trade_surge_ratio=self.settings.activity_trade_surge_ratio,
                    contraction_ratio=self.settings.activity_contraction_ratio,
                    trade_contraction_ratio=self.settings.activity_trade_contraction_ratio,
                    min_consecutive_windows=self.settings.activity_min_consecutive_windows,
                )
        selected, filtered, liquidity_profiles, liquidity_tier_stats, liquidity_status = select_tickers_for_scan(
            tickers,
            eligible_symbols=eligible_symbols,
            quote_asset=quote_asset,
            profile_source=self.settings,
            candidate_pool=candidate_pool + SCAN_CANDIDATE_RESERVE_SIZE,
            alt_min_quote_volume=min_quote_volume,
            alt_min_trade_count=min_trade_count,
            activity_by_symbol=activity_by_symbol,
            dynamic_activity_enabled=self.settings.dynamic_activity_enabled,
            activity_liquidity_floor_ratio=self.settings.activity_liquidity_floor_ratio,
            activity_normalized_threshold_ratio=self.settings.activity_normalized_threshold_ratio,
        )
        dynamic_eligible_count = sum(
            tier_stats.get("dynamic_eligible", 0) for tier_stats in liquidity_tier_stats.values()
        )
        total_eligible_count = len(filtered) + dynamic_eligible_count
        target_candidate_count = min(candidate_pool, len(selected))
        self.community_provider.prepare([ticker.symbol for ticker in selected])

        kline_map = self.gateway.map_klines(
            [ticker.symbol for ticker in selected],
            interval=interval,
            limit=self.settings.kline_limit,
            max_workers=self.settings.max_workers,
        )

        ready: list[tuple] = []
        indicator_cutoff = now_app_time()
        for ticker in selected:
            candles = kline_map.get(ticker.symbol)
            if not candles:
                continue
            closed_candles = [candle for candle in candles if candle.close_time <= indicator_cutoff]
            if not closed_candles:
                continue
            try:
                indicators = build_indicator_snapshot(closed_candles)
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
                eligible_symbols=total_eligible_count,
                candidate_symbols=target_candidate_count,
                candidate_pool=candidate_pool,
                liquidity_profiles=liquidity_profiles,
                liquidity_tier_stats=liquidity_tier_stats,
                dynamic_activity_enabled=self.settings.dynamic_activity_enabled,
                activity_discovery_symbols=activity_discovery_count,
                activity_surge_symbols=sum(profile.regime == "surge" for profile in activity_by_symbol.values()),
                activity_contraction_symbols=sum(profile.regime == "contraction" for profile in activity_by_symbol.values()),
                dynamic_eligible_symbols=dynamic_eligible_count,
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
            activity = status.get("activity")
            if isinstance(activity, MarketActivityProfile):
                if bool(status["dynamic_override"]):
                    reasons = [str(status["eligibility_reason"]), *reasons][:4]
                elif activity.regime == "surge":
                    reasons = [f"{activity.label} · 峰值 {activity.max_volume_ratio:.2f}x", *reasons][:4]
                elif activity.regime == "contraction":
                    warnings = [f"{activity.label} · 峰值 {activity.max_volume_ratio:.2f}x", *warnings][:3]
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
                    activity_profile=activity if isinstance(activity, MarketActivityProfile) else None,
                    dynamic_liquidity_override=bool(status["dynamic_override"]),
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
            eligible_symbols=total_eligible_count,
            candidate_symbols=target_candidate_count,
            candidate_pool=candidate_pool,
            liquidity_profiles=liquidity_profiles,
            liquidity_tier_stats=liquidity_tier_stats,
            dynamic_activity_enabled=self.settings.dynamic_activity_enabled,
            activity_discovery_symbols=activity_discovery_count,
            activity_surge_symbols=sum(profile.regime == "surge" for profile in activity_by_symbol.values()),
            activity_contraction_symbols=sum(profile.regime == "contraction" for profile in activity_by_symbol.values()),
            dynamic_eligible_symbols=dynamic_eligible_count,
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
