from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
from urllib.request import Request, urlopen

from .config import AppSettings
from .data_services import get_llm_provider
from .models import TradeSignal
from .onchain import OpenMultiChainOnchainProvider
from .runtime_config import IntelligenceDefaults, RuntimeConfig
from .service import SignalScanner
from .strategy_hits import score_strategy_hits
from .time_utils import now_app_time


@dataclass(frozen=True)
class ExchangeIntelItem:
    source: str
    symbol: str
    title: str
    category: str
    severity: float
    sentiment: float
    url: str = ""


@dataclass(frozen=True)
class TwitterAccountInsight:
    username: str
    mode: str
    weight_pct: float
    focus: str
    status: str


@dataclass(frozen=True)
class OnchainEvent:
    chain: str
    symbol: str
    event_type: str
    amount_usd: float
    direction: str
    severity: float
    tx_hash: str = ""


@dataclass(frozen=True)
class SpreadOpportunity:
    symbol: str
    spot_exchange: str
    futures_exchange: str
    spot_price: float
    futures_price: float
    spread_bps: float
    direction: str


@dataclass(frozen=True)
class FundingRateSnapshot:
    symbol: str
    futures_exchange: str
    funding_rate: float
    funding_rate_bps: float
    annualized_pct: float
    mark_price: float = 0.0
    index_price: float = 0.0
    next_funding_time: str = ""
    source: str = "local_csv"


@dataclass(frozen=True)
class StrategyHit:
    symbol: str
    strategy: str
    score: float
    grade: str
    action: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LlmInsight:
    provider: str
    model: str
    status: str
    summary: str


@dataclass(frozen=True)
class ExecutionRiskDecision:
    status: str
    risk_score: float
    allowed_symbols: list[str] = field(default_factory=list)
    blocked_symbols: dict[str, str] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class IntelligenceSnapshot:
    generated_at: datetime
    scanned_symbols: int
    returned_signals: int
    intel_items: list[ExchangeIntelItem]
    twitter_accounts: list[TwitterAccountInsight]
    onchain_events: list[OnchainEvent]
    spreads: list[SpreadOpportunity]
    funding_rates: list[FundingRateSnapshot]
    strategy_hits: list[StrategyHit]
    llm_insight: LlmInsight
    execution_risk: ExecutionRiskDecision


class LlmInsightClient:
    def __init__(self, *, provider: str, api_key: str, model: str, base_url: str = "", timeout: int = 20) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model = model
        preset = get_llm_provider(provider)
        self.api_style = preset.api_style
        self.base_url = (base_url or preset.base_url).rstrip("/")
        self.timeout = timeout

    def analyze(self, payload: dict[str, object]) -> str:
        if not self.api_key:
            raise ValueError("LLM API Key 未配置。")
        prompt = (
            "你是量化交易风控分析助手。基于以下 JSON 快照，输出中文，"
            "包含市场状态、主要机会、关键风险和自动交易建议。禁止承诺收益。\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        if self.api_style == "anthropic_messages":
            return self._analyze_anthropic(prompt)
        if self.api_style == "openai_responses":
            return self._analyze_openai_responses(prompt)
        return self._analyze_openai_chat(prompt)

    def _analyze_openai_responses(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "input": prompt,
                "max_output_tokens": 500,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/responses",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        return self._extract_output_text(data)

    def _analyze_openai_chat(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        return self._extract_chat_text(data)

    def _analyze_anthropic(self, prompt: str) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/messages",
            data=body,
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        return self._extract_anthropic_text(data)

    @staticmethod
    def _extract_output_text(payload: dict[str, object]) -> str:
        output = payload.get("output", [])
        if not isinstance(output, list):
            return ""
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = str(part.get("text", "")).strip()
                    if text:
                        parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _extract_chat_text(payload: dict[str, object]) -> str:
        choices = payload.get("choices", [])
        if not isinstance(choices, list):
            return ""
        parts: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message", {})
            if isinstance(message, dict):
                text = str(message.get("content", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _extract_anthropic_text(payload: dict[str, object]) -> str:
        content = payload.get("content", [])
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts)


class OpenAIInsightClient(LlmInsightClient):
    def __init__(self, *, api_key: str, model: str, timeout: int = 20) -> None:
        super().__init__(provider="openai", api_key=api_key, model=model, timeout=timeout)


class IntelligenceHub:
    def __init__(
        self,
        *,
        scanner: SignalScanner,
        runtime_config: RuntimeConfig,
        settings: AppSettings,
        use_live_funding: bool = False,
    ) -> None:
        self.scanner = scanner
        self.runtime_config = runtime_config
        self.settings = settings
        self.config = runtime_config.intelligence_defaults
        self.use_live_funding = use_live_funding

    def snapshot(self) -> IntelligenceSnapshot:
        summary, signals = self.scanner.scan()
        top_signals = signals[:8]
        intel_items = self._load_exchange_intel(top_signals)
        onchain_events = self._load_onchain_events(top_signals)
        spreads = self._build_spreads(top_signals)
        funding_rates = self._build_funding_rates(top_signals)
        strategy_hits = self._build_strategy_hits(top_signals, funding_rates, spreads)
        twitter_accounts = self._build_twitter_accounts()
        execution_risk = self._build_execution_risk(
            onchain_events=onchain_events,
            spreads=spreads,
            funding_rates=funding_rates,
            strategy_hits=strategy_hits,
        )
        llm_insight = self._build_llm_insight(
            intel_items=intel_items,
            onchain_events=onchain_events,
            spreads=spreads,
            funding_rates=funding_rates,
            strategy_hits=strategy_hits,
        )
        return IntelligenceSnapshot(
            generated_at=now_app_time(),
            scanned_symbols=summary.scanned_symbols,
            returned_signals=summary.returned_signals,
            intel_items=intel_items,
            twitter_accounts=twitter_accounts,
            onchain_events=onchain_events,
            spreads=spreads,
            funding_rates=funding_rates,
            strategy_hits=strategy_hits,
            llm_insight=llm_insight,
            execution_risk=execution_risk,
        )

    def _load_exchange_intel(self, signals: list[TradeSignal]) -> list[ExchangeIntelItem]:
        items = self._read_exchange_intel_csv(self.settings.exchange_intel_csv)
        if not items:
            items = [
                ExchangeIntelItem(
                    source="signal-engine",
                    symbol=signal.symbol,
                    title=f"{signal.symbol} 分数 {signal.score:.1f}，{'; '.join(signal.reasons[:2]) or '技术面改善'}",
                    category="signal",
                    severity=min(100.0, signal.score),
                    sentiment=1.0 if signal.score >= 75 else 0.4,
                )
                for signal in signals[:6]
            ]
        return [
            item
            for item in sorted(items, key=lambda candidate: candidate.severity, reverse=True)
            if item.severity >= self.config.min_intel_severity
        ][:12]

    @staticmethod
    def _read_exchange_intel_csv(path: Path) -> list[ExchangeIntelItem]:
        if not path.exists():
            return []
        items: list[ExchangeIntelItem] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                items.append(
                    ExchangeIntelItem(
                        source=(row.get("source") or "exchange").strip(),
                        symbol=(row.get("symbol") or "").strip().upper(),
                        title=(row.get("title") or "").strip(),
                        category=(row.get("category") or "market").strip(),
                        severity=float(row.get("severity", 0) or 0),
                        sentiment=float(row.get("sentiment", 0) or 0),
                        url=(row.get("url") or "").strip(),
                    )
                )
        return items

    def _build_twitter_accounts(self) -> list[TwitterAccountInsight]:
        accounts = self.runtime_config.x_tracked_accounts
        return [
            TwitterAccountInsight(
                username=account.lstrip("@"),
                mode=self.runtime_config.x_account_mode,
                weight_pct=self.runtime_config.x_account_weight_pct,
                focus=self._account_focus(account),
                status=self._x_provider_status(),
            )
            for account in accounts[:12]
        ]

    def _x_provider_status(self) -> str:
        if self.runtime_config.x_provider == "official_api":
            return "configured" if self.runtime_config.x_bearer_token else "token_missing"
        if self.runtime_config.x_provider == "nitter_rss":
            return "configured" if self.runtime_config.x_nitter_base_url else "nitter_missing"
        if self.runtime_config.x_provider == "session_scrape":
            return "configured" if self.runtime_config.x_session_command else "session_command_missing"
        return "provider_invalid"

    @staticmethod
    def _account_focus(account: str) -> str:
        lowered = account.lower()
        if lowered in {"grayscale", "ishares", "vaneck_us", "arkinvest", "21shares_us"}:
            return "ETF 与基金流向"
        if lowered in {"saylor", "strategy", "btctreasuries"}:
            return "BTC 持仓大户"
        if lowered in {"bitcoin", "ethereum", "solana", "bnbchain", "ripple", "chainlink", "suinetwork", "ton_blockchain"}:
            return "核心项目方"
        if lowered in {"cryptocred", "pentosh1", "daancrypto", "scottmelker", "bobloukas", "cryptohayes", "apompliano"}:
            return "交易员与宏观观点"
        if "chain" in lowered or "lookon" in lowered:
            return "链上异动"
        if "block" in lowered or "news" in lowered:
            return "交易所与行业新闻"
        if "binance" in lowered or "okx" in lowered:
            return "交易所公告"
        return "社区热度"

    def _load_onchain_events(self, signals: list[TradeSignal]) -> list[OnchainEvent]:
        events = self._read_onchain_csv(self.settings.onchain_events_csv)
        if self.runtime_config.onchain_data_preset == "open_multichain_keyless":
            price_map = {signal.symbol.upper(): float(signal.ticker.last_price) for signal in signals}
            try:
                events.extend(
                    OnchainEvent(
                        chain=item.chain,
                        symbol=item.symbol,
                        event_type=item.event_type,
                        amount_usd=item.amount_usd,
                        direction=item.direction,
                        severity=item.severity,
                        tx_hash=item.tx_hash,
                    )
                    for item in OpenMultiChainOnchainProvider(
                        whale_threshold_usd=self.config.whale_transfer_threshold_usd,
                        base_url_override=self.runtime_config.onchain_api_base_url,
                    ).fetch_events([signal.symbol for signal in signals], price_map)
                )
            except Exception:  # noqa: BLE001
                pass
        return [
            event
            for event in sorted(events, key=lambda candidate: candidate.severity, reverse=True)
            if event.amount_usd >= self.config.whale_transfer_threshold_usd
            or event.severity >= 70
            or (event.event_type == "network_snapshot" and event.severity >= 45)
        ][:10]

    @staticmethod
    def _read_onchain_csv(path: Path) -> list[OnchainEvent]:
        if not path.exists():
            return []
        events: list[OnchainEvent] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                events.append(
                    OnchainEvent(
                        chain=(row.get("chain") or "").strip(),
                        symbol=(row.get("symbol") or "").strip().upper(),
                        event_type=(row.get("event_type") or "").strip(),
                        amount_usd=float(row.get("amount_usd", 0) or 0),
                        direction=(row.get("direction") or "").strip(),
                        severity=float(row.get("severity", 0) or 0),
                        tx_hash=(row.get("tx_hash") or "").strip(),
                    )
                )
        return events

    def _build_spreads(self, signals: list[TradeSignal]) -> list[SpreadOpportunity]:
        spreads = self._read_spread_csv(self.settings.futures_basis_csv)
        return [
            item
            for item in sorted(spreads, key=lambda candidate: abs(candidate.spread_bps), reverse=True)
            if abs(item.spread_bps) >= self.config.min_spread_bps
        ][:10]

    def _build_funding_rates(self, signals: list[TradeSignal]) -> list[FundingRateSnapshot]:
        csv_rates = self._read_funding_csv(self.settings.futures_funding_csv)
        rates_by_symbol = {item.symbol: item for item in csv_rates}
        if self.use_live_funding:
            for signal in signals[:8]:
                symbol = signal.symbol.upper()
                if symbol in rates_by_symbol:
                    continue
                live_rate = self._fetch_binance_funding_rate(symbol)
                if live_rate is not None:
                    rates_by_symbol[symbol] = live_rate
        return sorted(rates_by_symbol.values(), key=lambda item: abs(item.funding_rate_bps), reverse=True)[:12]

    @staticmethod
    def _read_funding_csv(path: Path) -> list[FundingRateSnapshot]:
        if not path.exists():
            return []
        rates: list[FundingRateSnapshot] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                funding_rate = float(row.get("funding_rate", row.get("last_funding_rate", 0)) or 0)
                rates.append(
                    FundingRateSnapshot(
                        symbol=(row.get("symbol") or "").strip().upper(),
                        futures_exchange=(row.get("futures_exchange") or "BINANCE-PERP").strip(),
                        funding_rate=funding_rate,
                        funding_rate_bps=round(funding_rate * 10_000, 4),
                        annualized_pct=round(funding_rate * 3 * 365 * 100, 4),
                        mark_price=float(row.get("mark_price", 0) or 0),
                        index_price=float(row.get("index_price", 0) or 0),
                        next_funding_time=(row.get("next_funding_time") or "").strip(),
                        source=(row.get("source") or "local_csv").strip(),
                    )
                )
        return [item for item in rates if item.symbol]

    @staticmethod
    def _fetch_binance_funding_rate(symbol: str) -> FundingRateSnapshot | None:
        request = Request(
            f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol.upper()}",
            headers={"User-Agent": "trade-signal-app/0.1"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                payload = json.load(response)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict) or "lastFundingRate" not in payload:
            return None
        funding_rate = float(payload.get("lastFundingRate") or 0.0)
        next_time = payload.get("nextFundingTime")
        next_funding_time = ""
        if next_time:
            next_funding_time = datetime.fromtimestamp(int(next_time) / 1000, tz=timezone.utc).isoformat()
        return FundingRateSnapshot(
            symbol=str(payload.get("symbol") or symbol).upper(),
            futures_exchange="BINANCE-PERP",
            funding_rate=funding_rate,
            funding_rate_bps=round(funding_rate * 10_000, 4),
            annualized_pct=round(funding_rate * 3 * 365 * 100, 4),
            mark_price=float(payload.get("markPrice") or 0.0),
            index_price=float(payload.get("indexPrice") or 0.0),
            next_funding_time=next_funding_time,
            source="binance_futures_public",
        )

    @staticmethod
    def _read_spread_csv(path: Path) -> list[SpreadOpportunity]:
        if not path.exists():
            return []
        spreads: list[SpreadOpportunity] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                spot_price = float(row.get("spot_price", 0) or 0)
                futures_price = float(row.get("futures_price", 0) or 0)
                spread_bps = float(row.get("spread_bps") or (((futures_price - spot_price) / spot_price) * 10_000 if spot_price else 0))
                spreads.append(
                    SpreadOpportunity(
                        symbol=(row.get("symbol") or "").strip().upper(),
                        spot_exchange=(row.get("spot_exchange") or "BINANCE").strip(),
                        futures_exchange=(row.get("futures_exchange") or "BINANCE-PERP").strip(),
                        spot_price=spot_price,
                        futures_price=futures_price,
                        spread_bps=spread_bps,
                        direction=(row.get("direction") or "basis").strip(),
                    )
                )
        return spreads

    def _build_strategy_hits(
        self,
        signals: list[TradeSignal],
        funding_rates: list[FundingRateSnapshot] | None = None,
        spreads: list[SpreadOpportunity] | None = None,
    ) -> list[StrategyHit]:
        hits: list[StrategyHit] = []
        funding_by_symbol = {item.symbol: item for item in (funding_rates or [])}
        spread_by_symbol = {item.symbol: item for item in (spreads or [])}
        for signal in signals:
            for decision in score_strategy_hits(
                signal,
                config=self.runtime_config.autotrade_defaults,
                funding=funding_by_symbol.get(signal.symbol.upper()),
                spread=spread_by_symbol.get(signal.symbol.upper()),
            ):
                hits.append(
                    StrategyHit(
                        symbol=signal.symbol,
                        strategy=decision.strategy,
                        score=decision.score,
                        grade=decision.grade,
                        action=decision.action,
                        reasons=decision.reasons,
                    )
                )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:12]

    def _build_execution_risk(
        self,
        *,
        onchain_events: list[OnchainEvent],
        spreads: list[SpreadOpportunity],
        funding_rates: list[FundingRateSnapshot],
        strategy_hits: list[StrategyHit],
    ) -> ExecutionRiskDecision:
        blocked: dict[str, str] = {}
        for event in onchain_events:
            direction = event.direction.lower()
            if event.severity >= 85 and ("inflow" in direction or "deposit" in direction):
                blocked[event.symbol] = f"链上高严重度交易所流入：{event.severity:.0f}"
        for spread in spreads:
            if abs(spread.spread_bps) >= max(self.config.min_spread_bps * 4, 80):
                blocked.setdefault(spread.symbol, f"现货/合约价差异常：{spread.spread_bps:+.1f}bps")
        for funding in funding_rates:
            if funding.funding_rate >= 0.001:
                blocked.setdefault(funding.symbol, f"合约资金费率过热：{funding.funding_rate_bps:+.2f}bps/8h")

        hit_symbols = []
        for hit in strategy_hits:
            if hit.action in {
                "wait_pullback",
                "wait_support",
                "wait_volatility",
                "wait_volume",
                "wait_buy_pressure",
            }:
                continue
            if hit.symbol not in hit_symbols:
                hit_symbols.append(hit.symbol)
        allowed = [symbol for symbol in hit_symbols if symbol not in blocked]
        max_onchain = max((event.severity for event in onchain_events), default=0.0)
        max_spread = max((abs(spread.spread_bps) for spread in spreads), default=0.0)
        max_funding = max((abs(funding.funding_rate_bps) for funding in funding_rates), default=0.0)
        risk_score = min(100.0, max(max_onchain, max_spread * 0.8, max_funding * 8, len(blocked) * 25.0))
        status = "blocked" if blocked and not allowed else "caution" if blocked or risk_score >= 70 else "clear"
        summary = (
            f"执行前风控：允许 {len(allowed)} 个候选，阻断 {len(blocked)} 个标的，"
            f"风险分 {risk_score:.1f}。"
        )
        return ExecutionRiskDecision(
            status=status,
            risk_score=round(risk_score, 2),
            allowed_symbols=allowed,
            blocked_symbols=blocked,
            summary=summary,
        )

    def _build_llm_insight(
        self,
        *,
        intel_items: list[ExchangeIntelItem],
        onchain_events: list[OnchainEvent],
        spreads: list[SpreadOpportunity],
        funding_rates: list[FundingRateSnapshot],
        strategy_hits: list[StrategyHit],
    ) -> LlmInsight:
        payload = {
            "intel_items": [asdict(item) for item in intel_items[:6]],
            "onchain_events": [asdict(item) for item in onchain_events[:6]],
            "spreads": [asdict(item) for item in spreads[:6]],
            "funding_rates": [asdict(item) for item in funding_rates[:6]],
            "strategy_hits": [asdict(item) for item in strategy_hits[:6]],
        }
        provider = self.config.llm_provider or "openai"
        api_key = self.config.llm_api_key or self.config.openai_api_key
        model = self.config.llm_model or self.config.openai_model
        if self.config.llm_enabled and api_key:
            try:
                summary = LlmInsightClient(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    base_url=self.config.llm_base_url,
                ).analyze(payload)
                if summary:
                    return LlmInsight(provider=provider, model=model, status="ok", summary=summary)
            except Exception as exc:  # noqa: BLE001
                return LlmInsight(
                    provider=provider,
                    model=model,
                    status="fallback",
                    summary=f"大模型分析失败，已切换本地规则：{exc}",
                )
        return LlmInsight(
            provider="local",
            model="rules",
            status="ok",
            summary=self._local_summary(intel_items, onchain_events, spreads, funding_rates, strategy_hits),
        )

    @staticmethod
    def _local_summary(
        intel_items: list[ExchangeIntelItem],
        onchain_events: list[OnchainEvent],
        spreads: list[SpreadOpportunity],
        funding_rates: list[FundingRateSnapshot],
        strategy_hits: list[StrategyHit],
    ) -> str:
        risk = "中性"
        if onchain_events and max(item.severity for item in onchain_events) >= 85:
            risk = "偏高"
        if strategy_hits and not onchain_events:
            risk = "偏积极"
        return (
            f"综合监控显示：策略命中 {len(strategy_hits)} 个，链上异动 {len(onchain_events)} 条，"
            f"价差机会 {len(spreads)} 个，资金费率样本 {len(funding_rates)} 个，交易所/社区关键情报 {len(intel_items)} 条。"
            f"当前风险状态为{risk}；建议优先处理高分策略命中。"
            f"{' 未配置真实链上事件源，链上风控不参与阻断。' if not onchain_events else ' 实盘前需复核链上大额流入风险。'}"
            f"{' 未配置真实现货/合约 basis 源，价差风控不参与阻断。' if not spreads else ' 实盘前需复核价差回归风险。'}"
            f"{' 未接入合约资金费率，三类小市值策略会降级为观察。' if not funding_rates else ' 小市值动量/分布/暴跌反弹策略已纳入资金费率拥挤度。'}"
        )
