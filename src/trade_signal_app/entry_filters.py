from __future__ import annotations

ANTI_CHASE_DEFAULT_MAX_RSI = 72.0
ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT = 5.0
ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT = 4.0
STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT = 2.5
STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH = 2.0
STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO = 1.4
STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT = 2.0
STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT = 0.6
STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT = 0.4


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def anti_chase_reason(
    *,
    rsi: float,
    price_vs_ema20_pct: float,
    recent_change_pct: float,
    enabled: bool = True,
    max_rsi: float = ANTI_CHASE_DEFAULT_MAX_RSI,
    max_price_vs_ema20_pct: float = ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT,
    max_recent_change_pct: float = ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT,
) -> str:
    if not enabled:
        return ""

    reasons: list[str] = []
    if rsi > max_rsi:
        reasons.append(f"RSI {rsi:.1f} 高于 {max_rsi:.1f}")
    if price_vs_ema20_pct > max_price_vs_ema20_pct:
        reasons.append(f"价格偏离 EMA20 {price_vs_ema20_pct:+.1f}% 高于 {max_price_vs_ema20_pct:.1f}%")
    if recent_change_pct > max_recent_change_pct:
        reasons.append(f"近 7 根K线涨幅 {recent_change_pct:+.1f}% 高于 {max_recent_change_pct:.1f}%")

    if not reasons:
        return ""
    return "短线急拉后不追高，等待回调确认：" + "；".join(reasons)


def anti_chase_reason_from_config(
    *,
    rsi: float,
    price_vs_ema20_pct: float,
    recent_change_pct: float,
    config: object,
) -> str:
    return anti_chase_reason(
        rsi=rsi,
        price_vs_ema20_pct=price_vs_ema20_pct,
        recent_change_pct=recent_change_pct,
        enabled=bool(getattr(config, "anti_chase_enabled", True)),
        max_rsi=_safe_float(getattr(config, "max_entry_rsi", ANTI_CHASE_DEFAULT_MAX_RSI), ANTI_CHASE_DEFAULT_MAX_RSI),
        max_price_vs_ema20_pct=_safe_float(
            getattr(config, "max_entry_price_vs_ema20_pct", ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT),
            ANTI_CHASE_DEFAULT_MAX_PRICE_VS_EMA20_PCT,
        ),
        max_recent_change_pct=_safe_float(
            getattr(config, "max_entry_recent_change_pct", ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT),
            ANTI_CHASE_DEFAULT_MAX_RECENT_CHANGE_PCT,
        ),
    )


def volume_entry_reason_from_config(*, volume_ratio: float, config: object) -> str:
    minimum = _safe_float(getattr(config, "min_volume_ratio", 1.1), 1.1)
    if volume_ratio >= minimum:
        return ""
    return f"量能确认不足：当前量比 {volume_ratio:.2f}x，低于 {minimum:.2f}x"


def buy_pressure_entry_reason_from_config(*, buy_pressure_ratio: float, config: object) -> str:
    minimum = _safe_float(getattr(config, "min_buy_pressure", 0.52), 0.52)
    if buy_pressure_ratio >= minimum:
        return ""
    return f"主动买盘确认不足：当前买压 {buy_pressure_ratio * 100:.1f}%，低于 {minimum * 100:.1f}%"


def structure_entry_reason(
    *,
    close_price: float,
    support_level: float,
    resistance_level: float,
    support_distance_pct: float,
    resistance_distance_pct: float,
    support_strength: float,
    risk_reward_ratio: float,
    volume_ratio: float,
    buy_pressure_ratio: float,
    community_score: float | None = None,
    enabled: bool = True,
    max_support_distance_pct: float = STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT,
    min_support_strength: float = STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH,
    min_risk_reward_ratio: float = STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO,
    min_resistance_distance_pct: float = STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT,
    take_profit_pct: float = 9.0,
    support_stop_buffer_pct: float = STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT,
    resistance_take_profit_buffer_pct: float = STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT,
) -> str:
    if not enabled or close_price <= 0 or support_level <= 0:
        return ""

    community_confirmed = community_score is not None and community_score >= 70
    volume_confirmed = volume_ratio >= 1.5 and buy_pressure_ratio >= 0.58
    effective_min_strength = min_support_strength
    effective_min_rr = min_risk_reward_ratio
    if volume_confirmed:
        effective_min_strength -= 0.5
        effective_min_rr -= 0.1
    if community_confirmed:
        effective_min_strength -= 0.5
        effective_min_rr -= 0.1
    effective_min_strength = max(1.0, effective_min_strength)
    effective_min_rr = max(1.1, effective_min_rr)

    reasons: list[str] = []
    effective_support_distance = support_distance_pct
    if support_level < close_price:
        effective_support_distance = ((close_price - support_level) / close_price) * 100
    else:
        reasons.append("当前价格已跌破结构支撑")

    if support_level > 0 and effective_support_distance > max_support_distance_pct:
        reasons.append(f"距离支撑 {effective_support_distance:.1f}% 大于 {max_support_distance_pct:.1f}%")
    if support_level > 0 and support_strength < effective_min_strength:
        reasons.append(f"支撑触碰强度 {support_strength:.1f} 低于 {effective_min_strength:.1f}")

    has_overhead_resistance = resistance_level > close_price
    effective_resistance_distance = resistance_distance_pct
    if has_overhead_resistance:
        effective_resistance_distance = ((resistance_level - close_price) / close_price) * 100
        if effective_resistance_distance < min_resistance_distance_pct:
            reasons.append(f"上方阻力空间 {effective_resistance_distance:.1f}% 小于 {min_resistance_distance_pct:.1f}%")

    if support_level < close_price:
        risk_pct = max(effective_support_distance + support_stop_buffer_pct, 0.1)
        reward_pct = (
            max(effective_resistance_distance - resistance_take_profit_buffer_pct, 0.0)
            if has_overhead_resistance
            else max(take_profit_pct, 0.0)
        )
        risk_reward_ratio = reward_pct / risk_pct
    if risk_reward_ratio < effective_min_rr:
        reasons.append(f"结构盈亏比 {risk_reward_ratio:.2f} 低于 {effective_min_rr:.2f}")

    if not reasons:
        return ""
    return "支撑/盈亏比不足，等待更合理买点：" + "；".join(reasons)


def structure_entry_reason_from_config(
    *,
    close_price: float,
    support_level: float,
    resistance_level: float,
    support_distance_pct: float,
    resistance_distance_pct: float,
    support_strength: float,
    risk_reward_ratio: float,
    volume_ratio: float,
    buy_pressure_ratio: float,
    community_score: float | None,
    config: object,
) -> str:
    return structure_entry_reason(
        close_price=close_price,
        support_level=support_level,
        resistance_level=resistance_level,
        support_distance_pct=support_distance_pct,
        resistance_distance_pct=resistance_distance_pct,
        support_strength=support_strength,
        risk_reward_ratio=risk_reward_ratio,
        volume_ratio=volume_ratio,
        buy_pressure_ratio=buy_pressure_ratio,
        community_score=community_score,
        enabled=bool(getattr(config, "structure_filter_enabled", True)),
        max_support_distance_pct=_safe_float(
            getattr(config, "max_entry_support_distance_pct", STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT),
            STRUCTURE_DEFAULT_MAX_SUPPORT_DISTANCE_PCT,
        ),
        min_support_strength=_safe_float(
            getattr(config, "min_entry_support_strength", STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH),
            STRUCTURE_DEFAULT_MIN_SUPPORT_STRENGTH,
        ),
        min_risk_reward_ratio=_safe_float(
            getattr(config, "min_entry_risk_reward_ratio", STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO),
            STRUCTURE_DEFAULT_MIN_RISK_REWARD_RATIO,
        ),
        min_resistance_distance_pct=_safe_float(
            getattr(config, "min_entry_resistance_distance_pct", STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT),
            STRUCTURE_DEFAULT_MIN_RESISTANCE_DISTANCE_PCT,
        ),
        take_profit_pct=_safe_float(getattr(config, "take_profit_pct", 9.0), 9.0),
        support_stop_buffer_pct=_safe_float(
            getattr(config, "support_stop_buffer_pct", STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT),
            STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT,
        ),
        resistance_take_profit_buffer_pct=_safe_float(
            getattr(config, "resistance_take_profit_buffer_pct", STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT),
            STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT,
        ),
    )


def structure_adjusted_exit_prices(
    *,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    support_level: float,
    resistance_level: float,
    enabled: bool = True,
    support_stop_buffer_pct: float = STRUCTURE_DEFAULT_SUPPORT_STOP_BUFFER_PCT,
    resistance_take_profit_buffer_pct: float = STRUCTURE_DEFAULT_RESISTANCE_TAKE_PROFIT_BUFFER_PCT,
) -> tuple[float, float]:
    fixed_stop = entry_price * (1 - stop_loss_pct / 100)
    fixed_take = entry_price * (1 + take_profit_pct / 100)
    if not enabled or entry_price <= 0:
        return fixed_stop, fixed_take

    stop_price = fixed_stop
    if 0 < support_level < entry_price:
        structure_stop = support_level * (1 - support_stop_buffer_pct / 100)
        stop_price = max(fixed_stop, structure_stop)

    take_profit_price = fixed_take
    if resistance_level > entry_price:
        structure_take = resistance_level * (1 - resistance_take_profit_buffer_pct / 100)
        if structure_take > entry_price:
            take_profit_price = min(fixed_take, structure_take)
    return stop_price, take_profit_price
