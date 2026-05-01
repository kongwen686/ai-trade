from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
from urllib.request import Request, urlopen

from .config import AppSettings
from .models import TradeSignal
from .runtime_config import IntelligenceDefaults, RuntimeConfig
from .service import SignalScanner


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
    strategy_hits: list[StrategyHit]
    llm_insight: LlmInsight
    execution_risk: ExecutionRiskDecision


class OpenAIInsightClient:
    def __init__(self, *, api_key: str, model: str, timeout: int = 20) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def analyze(self, payload: dict[str, object]) -> str:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 未配置。")
        prompt = (
            "你是量化交易风控分析助手。基于以下 JSON 快照，输出中文，"
            "包含市场状态、主要机会、关键风险和自动交易建议。禁止承诺收益。\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "input": prompt,
                "max_output_tokens": 500,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/responses",
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


class IntelligenceHub:
    def __init__(
        self,
        *,
        scanner: SignalScanner,
        runtime_config: RuntimeConfig,
        settings: AppSettings,
    ) -> None:
        self.scanner = scanner
        self.runtime_config = runtime_config
        self.settings = settings
        self.config = runtime_config.intelligence_defaults

    def snapshot(self) -> IntelligenceSnapshot:
        summary, signals = self.scanner.scan()
        top_signals = signals[:8]
        intel_items = self._load_exchange_intel(top_signals)
        onchain_events = self._load_onchain_events(top_signals)
        spreads = self._build_spreads(top_signals)
        strategy_hits = self._build_strategy_hits(top_signals)
        twitter_accounts = self._build_twitter_accounts()
        execution_risk = self._build_execution_risk(
            onchain_events=onchain_events,
            spreads=spreads,
            strategy_hits=strategy_hits,
        )
        llm_insight = self._build_llm_insight(
            intel_items=intel_items,
            onchain_events=onchain_events,
            spreads=spreads,
            strategy_hits=strategy_hits,
        )
        return IntelligenceSnapshot(
            generated_at=datetime.now(timezone.utc),
            scanned_symbols=summary.scanned_symbols,
            returned_signals=summary.returned_signals,
            intel_items=intel_items,
            twitter_accounts=twitter_accounts,
            onchain_events=onchain_events,
            spreads=spreads,
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
        accounts = self.runtime_config.x_tracked_accounts or ["lookonchain", "wu_blockchain", "TheBlock__", "binance"]
        return [
            TwitterAccountInsight(
                username=account.lstrip("@"),
                mode=self.runtime_config.x_account_mode,
                weight_pct=self.runtime_config.x_account_weight_pct,
                focus=self._account_focus(account),
                status="configured" if self.runtime_config.x_bearer_token else "token_missing",
            )
            for account in accounts[:12]
        ]

    @staticmethod
    def _account_focus(account: str) -> str:
        lowered = account.lower()
        if "chain" in lowered or "lookon" in lowered:
            return "链上异动"
        if "block" in lowered or "news" in lowered:
            return "交易所与行业新闻"
        if "binance" in lowered or "okx" in lowered:
            return "交易所公告"
        return "社区热度"

    def _load_onchain_events(self, signals: list[TradeSignal]) -> list[OnchainEvent]:
        events = self._read_onchain_csv(self.settings.onchain_events_csv)
        if not events:
            events = [
                OnchainEvent(
                    chain="derived",
                    symbol=signal.symbol,
                    event_type="volume_impulse",
                    amount_usd=signal.ticker.quote_volume * min(0.05, signal.indicators.volume_ratio / 100),
                    direction="exchange_inflow" if signal.ticker.price_change_percent < 0 else "accumulation",
                    severity=min(100.0, 45 + signal.indicators.volume_ratio * 20),
                )
                for signal in signals
                if signal.indicators.volume_ratio >= 1.2
            ]
        return [
            event
            for event in sorted(events, key=lambda candidate: candidate.severity, reverse=True)
            if event.amount_usd >= self.config.whale_transfer_threshold_usd or event.severity >= 70
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
        if not spreads:
            spreads = []
            for signal in signals[:12]:
                spot = signal.ticker.last_price
                synthetic_basis = signal.ticker.price_change_percent * 0.0008 + signal.indicators.ema_spread_pct * 0.0005
                futures = spot * (1 + synthetic_basis)
                spread_bps = ((futures - spot) / spot) * 10_000 if spot else 0.0
                spreads.append(
                    SpreadOpportunity(
                        symbol=signal.symbol,
                        spot_exchange="BINANCE",
                        futures_exchange="BINANCE-PERP",
                        spot_price=spot,
                        futures_price=futures,
                        spread_bps=spread_bps,
                        direction="long_spot_short_perp" if spread_bps > 0 else "short_spot_long_perp",
                    )
                )
        return [
            item
            for item in sorted(spreads, key=lambda candidate: abs(candidate.spread_bps), reverse=True)
            if abs(item.spread_bps) >= self.config.min_spread_bps
        ][:10]

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

    def _build_strategy_hits(self, signals: list[TradeSignal]) -> list[StrategyHit]:
        hits: list[StrategyHit] = []
        threshold = self.runtime_config.autotrade_defaults.score_threshold
        for signal in signals:
            if signal.score >= threshold:
                hits.append(
                    StrategyHit(
                        symbol=signal.symbol,
                        strategy="auto_score_breakout",
                        score=signal.score,
                        grade=signal.grade,
                        action="candidate_buy" if self.runtime_config.autotrade_defaults.enabled else "watch",
                        reasons=signal.reasons[:4],
                    )
                )
            if signal.indicators.volume_ratio >= 1.5 and signal.indicators.buy_pressure_ratio >= 0.56:
                hits.append(
                    StrategyHit(
                        symbol=signal.symbol,
                        strategy="volume_pressure",
                        score=min(100.0, signal.score + 5),
                        grade=signal.grade,
                        action="priority_watch",
                        reasons=["量能放大", "主动买盘增强", *signal.reasons[:2]],
                    )
                )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:12]

    def _build_execution_risk(
        self,
        *,
        onchain_events: list[OnchainEvent],
        spreads: list[SpreadOpportunity],
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

        hit_symbols = []
        for hit in strategy_hits:
            if hit.symbol not in hit_symbols:
                hit_symbols.append(hit.symbol)
        allowed = [symbol for symbol in hit_symbols if symbol not in blocked]
        max_onchain = max((event.severity for event in onchain_events), default=0.0)
        max_spread = max((abs(spread.spread_bps) for spread in spreads), default=0.0)
        risk_score = min(100.0, max(max_onchain, max_spread * 0.8, len(blocked) * 25.0))
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
        strategy_hits: list[StrategyHit],
    ) -> LlmInsight:
        payload = {
            "intel_items": [asdict(item) for item in intel_items[:6]],
            "onchain_events": [asdict(item) for item in onchain_events[:6]],
            "spreads": [asdict(item) for item in spreads[:6]],
            "strategy_hits": [asdict(item) for item in strategy_hits[:6]],
        }
        if self.config.llm_enabled and self.config.openai_api_key:
            try:
                summary = OpenAIInsightClient(
                    api_key=self.config.openai_api_key,
                    model=self.config.openai_model,
                ).analyze(payload)
                if summary:
                    return LlmInsight(provider="openai", model=self.config.openai_model, status="ok", summary=summary)
            except Exception as exc:  # noqa: BLE001
                return LlmInsight(
                    provider="openai",
                    model=self.config.openai_model,
                    status="fallback",
                    summary=f"OpenAI 分析失败，已切换本地规则：{exc}",
                )
        return LlmInsight(
            provider="local",
            model="rules",
            status="ok",
            summary=self._local_summary(intel_items, onchain_events, spreads, strategy_hits),
        )

    @staticmethod
    def _local_summary(
        intel_items: list[ExchangeIntelItem],
        onchain_events: list[OnchainEvent],
        spreads: list[SpreadOpportunity],
        strategy_hits: list[StrategyHit],
    ) -> str:
        risk = "中性"
        if onchain_events and max(item.severity for item in onchain_events) >= 85:
            risk = "偏高"
        if strategy_hits and not onchain_events:
            risk = "偏积极"
        return (
            f"综合监控显示：策略命中 {len(strategy_hits)} 个，链上异动 {len(onchain_events)} 条，"
            f"价差机会 {len(spreads)} 个，交易所/社区关键情报 {len(intel_items)} 条。"
            f"当前风险状态为{risk}；建议优先处理高分策略命中，并在实盘前复核链上大额流入与价差回归风险。"
        )
