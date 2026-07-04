from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicDataPreset:
    preset_id: str
    name: str
    category: str
    auth_required: bool
    base_url: str
    description: str


@dataclass(frozen=True)
class LlmProviderPreset:
    provider_id: str
    name: str
    api_style: str
    base_url: str
    default_model: str
    description: str


PUBLIC_DATA_PRESETS: tuple[PublicDataPreset, ...] = (
    PublicDataPreset(
        "binance_public",
        "Binance Public Market Data",
        "market",
        False,
        "https://data-api.binance.vision",
        "Binance 公开行情 REST/WebSocket；不需要 API key，只能读取公开市场数据。",
    ),
    PublicDataPreset(
        "okx_public",
        "OKX Public Market Data",
        "market",
        False,
        "https://www.okx.com",
        "OKX 公开行情、产品和 K 线接口；账户与交易接口仍需要 OKX key/secret/passphrase。",
    ),
    PublicDataPreset(
        "coingecko_keyless",
        "CoinGecko Keyless",
        "market",
        False,
        "https://api.coingecko.com/api/v3",
        "CoinGecko Keyless 市场数据；适合补充价格、趋势和全局市场指标。",
    ),
    PublicDataPreset(
        "tradingview_unofficial",
        "TradingView Unofficial",
        "market",
        False,
        "TradingView WebSocket + local CSV cache",
        "TradingView 非官方历史 K 线拉取；会先缓存为本地 CSV，再交给回测引擎读取，适合作为补充数据源。",
    ),
    PublicDataPreset(
        "open_multichain_keyless",
        "Open Multi-chain Keyless",
        "onchain",
        False,
        "Blockstream + PublicNode + Solana RPC + XRPL + Blockchair",
        "BTC/ETH/DOGE/SOL/ZEC/XRP 主流链公开监控组合；无密钥，适合基础链上健康、最新区块和大额原生资产转账监控。",
    ),
    PublicDataPreset(
        "geckoterminal_keyless",
        "GeckoTerminal Keyless",
        "onchain",
        False,
        "https://api.geckoterminal.com/api/v2",
        "GeckoTerminal Keyless DEX/池子/链上 OHLCV；适合无需密钥的链上交易数据补充。",
    ),
    PublicDataPreset(
        "defillama_free",
        "DefiLlama Free API",
        "onchain",
        False,
        "https://api.llama.fi",
        "DefiLlama 免费 DeFi、TVL、稳定币、收益和链数据；不需要认证。",
    ),
    PublicDataPreset(
        "local_csv",
        "Local CSV",
        "onchain",
        False,
        "data/onchain_events.csv",
        "读取本地链上事件 CSV，适合个人自定义监控或离线数据。",
    ),
)


LLM_PROVIDER_PRESETS: tuple[LlmProviderPreset, ...] = (
    LlmProviderPreset("openai", "OpenAI", "openai_responses", "https://api.openai.com/v1", "gpt-5.5", "Responses API；默认兼容现有 OpenAI 配置。"),
    LlmProviderPreset("anthropic", "Anthropic Claude", "anthropic_messages", "https://api.anthropic.com/v1", "claude-sonnet-4-6", "Anthropic Messages API。"),
    LlmProviderPreset("google", "Google Gemini", "openai_chat", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash", "Gemini OpenAI-compatible endpoint。"),
    LlmProviderPreset("deepseek", "DeepSeek", "openai_chat", "https://api.deepseek.com/v1", "deepseek-chat", "DeepSeek OpenAI-compatible chat endpoint。"),
    LlmProviderPreset("xai", "xAI Grok", "openai_chat", "https://api.x.ai/v1", "grok-4", "xAI OpenAI-compatible chat endpoint。"),
    LlmProviderPreset("mistral", "Mistral AI", "openai_chat", "https://api.mistral.ai/v1", "mistral-large-latest", "Mistral chat completions endpoint。"),
    LlmProviderPreset("qwen", "Alibaba Qwen", "openai_chat", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "DashScope OpenAI-compatible endpoint。"),
    LlmProviderPreset("moonshot", "Moonshot Kimi", "openai_chat", "https://api.moonshot.cn/v1", "kimi-k2-latest", "Moonshot OpenAI-compatible chat endpoint。"),
)


def public_data_preset_ids(category: str | None = None) -> set[str]:
    return {
        item.preset_id
        for item in PUBLIC_DATA_PRESETS
        if category is None or item.category == category
    }


def llm_provider_ids() -> set[str]:
    return {item.provider_id for item in LLM_PROVIDER_PRESETS}


def get_llm_provider(provider_id: str) -> LlmProviderPreset:
    for provider in LLM_PROVIDER_PRESETS:
        if provider.provider_id == provider_id:
            return provider
    return LLM_PROVIDER_PRESETS[0]


def get_public_data_preset(preset_id: str) -> PublicDataPreset:
    for preset in PUBLIC_DATA_PRESETS:
        if preset.preset_id == preset_id:
            return preset
    return PUBLIC_DATA_PRESETS[0]
