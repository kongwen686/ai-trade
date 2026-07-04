from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import dataclass
from math import log10
from typing import Callable
from urllib.request import Request, urlopen
import json


DEFAULT_ONCHAIN_SYMBOLS = ("BTCUSDT", "ETHUSDT", "DOGEUSDT", "SOLUSDT", "ZECUSDT", "XRPUSDT")


@dataclass(frozen=True)
class OnchainMonitorEvent:
    chain: str
    symbol: str
    event_type: str
    amount_usd: float
    direction: str
    severity: float
    tx_hash: str = ""


@dataclass(frozen=True)
class OnchainChainConfig:
    chain: str
    symbol: str
    native_asset: str
    source: str
    base_url: str
    decimals: int
    blockchair_slug: str = ""


OPEN_MULTICHAIN_CONFIGS: tuple[OnchainChainConfig, ...] = (
    OnchainChainConfig("bitcoin", "BTCUSDT", "BTC", "blockstream", "https://blockstream.info/api", 8),
    OnchainChainConfig("ethereum", "ETHUSDT", "ETH", "evm_rpc", "https://ethereum-rpc.publicnode.com", 18),
    OnchainChainConfig("dogecoin", "DOGEUSDT", "DOGE", "blockchair_stats", "https://api.blockchair.com", 8, "dogecoin"),
    OnchainChainConfig("solana", "SOLUSDT", "SOL", "solana_rpc", "https://api.mainnet-beta.solana.com", 9),
    OnchainChainConfig("zcash", "ZECUSDT", "ZEC", "blockchair_stats", "https://api.blockchair.com", 8, "zcash"),
    OnchainChainConfig("xrp", "XRPUSDT", "XRP", "xrpl_rpc", "https://s1.ripple.com:51234", 6),
)


JsonFetcher = Callable[[str, str, object | None, dict[str, str] | None, int], object]


def http_json_request(method: str, url: str, payload: object | None = None, headers: dict[str, str] | None = None, timeout: int = 5) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"User-Agent": "trade-signal-app/0.3", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()


class OpenMultiChainOnchainProvider:
    def __init__(
        self,
        *,
        whale_threshold_usd: float,
        base_url_override: str = "",
        timeout: int = 5,
        max_workers: int = 6,
        fetcher: JsonFetcher = http_json_request,
    ) -> None:
        self.whale_threshold_usd = whale_threshold_usd
        self.base_url_override = base_url_override.rstrip("/")
        self.timeout = timeout
        self.max_workers = max(1, max_workers)
        self.fetcher = fetcher

    def fetch_events(self, symbols: list[str], price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        requested = {symbol.upper() for symbol in symbols}
        requested.update(DEFAULT_ONCHAIN_SYMBOLS)
        configs = [config for config in OPEN_MULTICHAIN_CONFIGS if config.symbol in requested]
        events: list[OnchainMonitorEvent] = []
        executor = ThreadPoolExecutor(max_workers=min(self.max_workers, len(configs) or 1))
        try:
            future_map = {executor.submit(self._fetch_chain_events, config, price_map): config for config in configs}
            for future in as_completed(future_map, timeout=self.timeout):
                try:
                    events.extend(future.result())
                except Exception:  # noqa: BLE001
                    continue
        except FutureTimeoutError:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return sorted(events, key=lambda event: event.severity, reverse=True)

    def _fetch_chain_events(self, config: OnchainChainConfig, price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        if config.source == "blockstream":
            return self._fetch_blockstream_events(config, price_map)
        if config.source == "evm_rpc":
            return self._fetch_evm_events(config, price_map)
        if config.source == "solana_rpc":
            return self._fetch_solana_events(config, price_map)
        if config.source == "xrpl_rpc":
            return self._fetch_xrpl_events(config, price_map)
        if config.source == "blockchair_stats":
            return self._fetch_blockchair_stats(config)
        return []

    def _base_url(self, config: OnchainChainConfig) -> str:
        return self.base_url_override or config.base_url.rstrip("/")

    def _fetch_blockstream_events(self, config: OnchainChainConfig, price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        base_url = self._base_url(config)
        block_hash = str(self.fetcher("GET", f"{base_url}/blocks/tip/hash", None, None, self.timeout))
        try:
            txs = self.fetcher("GET", f"{base_url}/block/{block_hash}/txs/0", None, None, self.timeout)
        except Exception:  # noqa: BLE001
            height = self.fetcher("GET", f"{base_url}/blocks/tip/height", None, None, self.timeout)
            return [
                OnchainMonitorEvent(
                    chain=config.chain,
                    symbol=config.symbol,
                    event_type="network_snapshot",
                    amount_usd=0.0,
                    direction=f"tip_height={height}",
                    severity=50.0,
                    tx_hash=block_hash,
                )
            ]
        if not isinstance(txs, list):
            return []
        price = price_map.get(config.symbol, 0.0)
        max_transfer = 0.0
        max_txid = ""
        for tx in txs[:100]:
            if not isinstance(tx, dict):
                continue
            value = sum(float(vout.get("value", 0) or 0) for vout in tx.get("vout", []) if isinstance(vout, dict)) / (10 ** config.decimals)
            if value > max_transfer:
                max_transfer = value
                max_txid = str(tx.get("txid") or "")
        return self._events_from_block_sample(
            config=config,
            tx_count=len(txs),
            max_transfer_native=max_transfer,
            max_txid=max_txid,
            price=price,
        )

    def _fetch_evm_events(self, config: OnchainChainConfig, price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        payload = {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": ["latest", True], "id": 1}
        response = self.fetcher("POST", self._base_url(config), payload, None, self.timeout)
        block = response.get("result") if isinstance(response, dict) else None
        if not isinstance(block, dict):
            return []
        txs = block.get("transactions") if isinstance(block.get("transactions"), list) else []
        max_transfer = 0.0
        max_hash = ""
        for tx in txs[:300]:
            if not isinstance(tx, dict):
                continue
            value = int(str(tx.get("value") or "0x0"), 16) / (10 ** config.decimals)
            if value > max_transfer:
                max_transfer = value
                max_hash = str(tx.get("hash") or "")
        return self._events_from_block_sample(
            config=config,
            tx_count=len(txs),
            max_transfer_native=max_transfer,
            max_txid=max_hash,
            price=price_map.get(config.symbol, 0.0),
        )

    def _fetch_solana_events(self, config: OnchainChainConfig, price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        slot_payload = {"jsonrpc": "2.0", "method": "getSlot", "params": [{"commitment": "confirmed"}], "id": 1}
        slot_response = self.fetcher("POST", self._base_url(config), slot_payload, None, self.timeout)
        slot = slot_response.get("result") if isinstance(slot_response, dict) else None
        if slot is None:
            return []
        block = None
        for candidate_slot in range(int(slot), max(int(slot) - 20, 0), -1):
            block_payload = {
                "jsonrpc": "2.0",
                "method": "getBlock",
                "params": [
                    candidate_slot,
                    {
                        "encoding": "json",
                        "transactionDetails": "signatures",
                        "rewards": False,
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
                "id": 2,
            }
            try:
                response = self.fetcher("POST", self._base_url(config), block_payload, None, self.timeout)
            except Exception:  # noqa: BLE001
                continue
            block = response.get("result") if isinstance(response, dict) else None
            if isinstance(block, dict):
                break
        if not isinstance(block, dict):
            return [
                OnchainMonitorEvent(
                    chain=config.chain,
                    symbol=config.symbol,
                    event_type="network_snapshot",
                    amount_usd=0.0,
                    direction=f"confirmed_slot={slot}",
                    severity=50.0,
                )
            ]
        txs = block.get("signatures") if isinstance(block.get("signatures"), list) else []
        return self._events_from_block_sample(
            config=config,
            tx_count=len(txs),
            max_transfer_native=0.0,
            max_txid=str(txs[0]) if txs else "",
            price=price_map.get(config.symbol, 0.0),
        )

    def _fetch_xrpl_events(self, config: OnchainChainConfig, price_map: dict[str, float]) -> list[OnchainMonitorEvent]:
        payload = {"method": "ledger", "params": [{"ledger_index": "validated", "transactions": True, "expand": True}]}
        response = self.fetcher("POST", self._base_url(config), payload, None, self.timeout)
        result = response.get("result") if isinstance(response, dict) else None
        ledger = result.get("ledger") if isinstance(result, dict) and isinstance(result.get("ledger"), dict) else None
        if not isinstance(ledger, dict):
            return []
        txs = ledger.get("transactions") if isinstance(ledger.get("transactions"), list) else []
        max_transfer = 0.0
        max_hash = ""
        for tx in txs[:300]:
            if not isinstance(tx, dict):
                continue
            amount = tx.get("Amount") if tx.get("TransactionType") == "Payment" else None
            if isinstance(amount, str) and amount.isdigit():
                value = int(amount) / (10 ** config.decimals)
                if value > max_transfer:
                    max_transfer = value
                    max_hash = str(tx.get("hash") or "")
        return self._events_from_block_sample(
            config=config,
            tx_count=len(txs),
            max_transfer_native=max_transfer,
            max_txid=max_hash,
            price=price_map.get(config.symbol, 0.0),
        )

    def _fetch_blockchair_stats(self, config: OnchainChainConfig) -> list[OnchainMonitorEvent]:
        base_url = self._base_url(config)
        response = self.fetcher("GET", f"{base_url}/{config.blockchair_slug}/stats", None, None, self.timeout)
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            return []
        tx_24h = _float_first(data, "transactions_24h", "transactions_last_24h", "txs_24h")
        mempool_txs = _float_first(data, "mempool_transactions", "mempool_txs")
        severity = _network_severity(tx_count=tx_24h, mempool_count=mempool_txs)
        return [
            OnchainMonitorEvent(
                chain=config.chain,
                symbol=config.symbol,
                event_type="network_snapshot",
                amount_usd=0.0,
                direction=f"tx24h={tx_24h:.0f};mempool={mempool_txs:.0f}",
                severity=severity,
            )
        ]

    def _events_from_block_sample(
        self,
        *,
        config: OnchainChainConfig,
        tx_count: int,
        max_transfer_native: float,
        max_txid: str,
        price: float,
    ) -> list[OnchainMonitorEvent]:
        events = [
            OnchainMonitorEvent(
                chain=config.chain,
                symbol=config.symbol,
                event_type="network_snapshot",
                amount_usd=0.0,
                direction=f"latest_block_txs={tx_count}",
                severity=_network_severity(tx_count=tx_count, mempool_count=0.0),
            )
        ]
        amount_usd = max_transfer_native * price if price else 0.0
        if amount_usd >= self.whale_threshold_usd:
            events.append(
                OnchainMonitorEvent(
                    chain=config.chain,
                    symbol=config.symbol,
                    event_type="large_native_transfer",
                    amount_usd=round(amount_usd, 2),
                    direction="large_transfer",
                    severity=_whale_severity(amount_usd, self.whale_threshold_usd),
                    tx_hash=max_txid,
                )
            )
        return events


def _float_first(data: dict[str, object], *keys: str) -> float:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _network_severity(*, tx_count: float, mempool_count: float) -> float:
    activity_score = min(18.0, log10(max(tx_count, 1.0)) * 3.5)
    mempool_score = min(17.0, log10(max(mempool_count, 1.0)) * 4.0)
    return round(45.0 + activity_score + mempool_score, 2)


def _whale_severity(amount_usd: float, threshold_usd: float) -> float:
    if threshold_usd <= 0:
        return 90.0
    return round(min(100.0, 78.0 + log10(max(amount_usd / threshold_usd, 1.0)) * 12.0), 2)
