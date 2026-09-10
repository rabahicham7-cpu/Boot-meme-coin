from __future__ import annotations

from typing import Any


SMART_LABELS = {
    "smartTrader",
    "proTrader",
}

RISK_LABELS = {
    "bundler",
    "sniper",
    "insider",
}


def _safe_float(value: Any) -> float | None:

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:

    if value is None:
        return 0

    try:
        return int(value)

    except (TypeError, ValueError):
        return 0


def _normalize_labels(value: Any) -> set[str]:

    if not value:
        return set()

    if isinstance(value, str):
        return {value}

    if isinstance(value, (list, tuple, set)):

        return {
            str(label)
            for label in value
            if label
        }

    return set()


def _get_total_pnl(
    trader: dict[str, Any],
) -> float | None:

    total = _safe_float(
        trader.get("totalPnlUSD")
    )

    if total is not None:
        return total

    realized = _safe_float(
        trader.get("realizedPnlUSD")
    )

    unrealized = _safe_float(
        trader.get("unrealizedPnlUSD")
    )

    if realized is None and unrealized is None:
        return None

    return (
        (realized or 0.0)
        + (unrealized or 0.0)
    )


def _analyze_smart_trader(
    trader: dict[str, Any],
) -> dict[str, Any]:

    labels = _normalize_labels(
        trader.get("labels")
    )

    smart_labels = (
        labels & SMART_LABELS
    )

    risk_labels = (
        labels & RISK_LABELS
    )

    buy_volume = (
        _safe_float(
            trader.get("volumeBuyUSD")
        )
        or 0.0
    )

    sell_volume = (
        _safe_float(
            trader.get("volumeSellUSD")
        )
        or 0.0
    )

    total_volume = (
        buy_volume
        + sell_volume
    )

    if total_volume > 0:

        buy_ratio = (
            buy_volume
            / total_volume
        )

        sell_ratio = (
            sell_volume
            / total_volume
        )

    else:

        buy_ratio = 0.0
        sell_ratio = 0.0

    position_usd = (
        _safe_float(
            trader.get("tokenAmountUSD")
        )
    )

    position_usd = (
        position_usd
        if position_usd is not None
        else 0.0
    )

    supply_percentage = (
        _safe_float(
            trader.get(
                "percentageOfTotalSupply"
            )
        )
    )

    buys = _safe_int(
        trader.get("buys")
    )

    sells = _safe_int(
        trader.get("sells")
    )

    trade_count = buys + sells

    total_pnl = _get_total_pnl(
        trader
    )

    score = 50

    evidence = []

    # --------------------------------
    # Professional / Smart label
    # --------------------------------

    if "smartTrader" in labels:

        score += 20

        evidence.append(
            "تصنيف smartTrader موجود."
        )

    elif "proTrader" in labels:

        score += 15

        evidence.append(
            "تصنيف proTrader موجود."
        )

    # --------------------------------
    # Risk labels
    # --------------------------------

    if risk_labels:

        score -= 25

        evidence.append(
            "توجد Labels عالية المخاطر: "
            + ", ".join(
                sorted(risk_labels)
            )
        )

    # --------------------------------
    # Buy / Sell flow
    # --------------------------------

    if buy_ratio >= 0.65:

        score += 15

        evidence.append(
            "تدفق شراء قوي."
        )

        flow = "accumulation"

    elif sell_ratio >= 0.65:

        score -= 15

        evidence.append(
            "تدفق بيع قوي."
        )

        flow = "distribution"

    else:

        flow = "balanced"

        evidence.append(
            "تدفق الشراء والبيع متوازن نسبيًا."
        )

    # --------------------------------
    # Position
    # --------------------------------

    if position_usd >= 100_000:

        score += 10

        evidence.append(
            "حجم المركز كبير."
        )

    elif position_usd >= 10_000:

        score += 5

        evidence.append(
            "حجم المركز ملحوظ."
        )

    # --------------------------------
    # PnL
    # --------------------------------

    if total_pnl is not None:

        if total_pnl > 0:

            score += 5

            evidence.append(
                "إجمالي PnL موجب."
            )

        elif total_pnl < 0:

            score -= 5

            evidence.append(
                "إجمالي PnL سالب."
            )

    # --------------------------------
    # Trading activity
    # --------------------------------

    if trade_count >= 20:

        score += 5

    # --------------------------------
    # Final score
    # --------------------------------

    score = max(
        0,
        min(100, score),
    )

    if score >= 80:

        grade = "قوي جدًا"

    elif score >= 70:

        grade = "قوي"

    elif score >= 55:

        grade = "متوسط"

    elif score >= 40:

        grade = "ضعيف"

    else:

        grade = "عالي المخاطر"

    return {
        "wallet_address": trader.get(
            "walletAddress"
        ),

        "labels": sorted(labels),

        "smart_labels": sorted(
            smart_labels
        ),

        "risk_labels": sorted(
            risk_labels
        ),

        "position_usd": round(
            position_usd,
            2,
        ),

        "supply_percentage": (
            supply_percentage
        ),

        "buy_volume_usd": round(
            buy_volume,
            2,
        ),

        "sell_volume_usd": round(
            sell_volume,
            2,
        ),

        "buy_ratio": round(
            buy_ratio,
            4,
        ),

        "sell_ratio": round(
            sell_ratio,
            4,
        ),

        "buys": buys,

        "sells": sells,

        "trade_count": trade_count,

        "total_pnl_usd": total_pnl,

        "flow": flow,

        "score": score,

        "grade": grade,

        "evidence": evidence,
    }


def analyze_smart_money(
    traders: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    تحليل تدفق Smart Money.

    لا يعتمد على Label واحدة.
    يتم دمج:
    - Smart/Pro labels
    - حجم الشراء والبيع
    - حجم المركز
    - PnL
    - Risk labels
    """

    if not traders:

        return {
            "status": "insufficient_data",
            "confidence": 0,
            "total_traders": 0,
            "smart_traders": 0,
            "smart_money_buy_volume_usd": 0,
            "smart_money_sell_volume_usd": 0,
            "smart_money_buy_ratio": 0,
            "smart_money_sell_ratio": 0,
            "smart_money_score": 0,
            "flow": "unknown",
            "warnings": [
                "لا توجد بيانات متداولين."
            ],
        }

    analyzed = [
        _analyze_smart_trader(
            trader
        )
        for trader in traders
    ]

    smart_traders = [
        trader
        for trader in analyzed
        if trader["smart_labels"]
    ]

    if not smart_traders:

        return {
            "status": "no_smart_traders",
            "confidence": 60,
            "total_traders": len(traders),
            "smart_traders": 0,
            "smart_money_buy_volume_usd": 0,
            "smart_money_sell_volume_usd": 0,
            "smart_money_buy_ratio": 0,
            "smart_money_sell_ratio": 0,
            "smart_money_score": 50,
            "flow": "unknown",
            "traders": [],
            "warnings": [
                "لم يتم العثور على محافظ مصنفة "
                "smartTrader أو proTrader."
            ],
        }

    buy_volume = sum(
        trader["buy_volume_usd"]
        for trader in smart_traders
    )

    sell_volume = sum(
        trader["sell_volume_usd"]
        for trader in smart_traders
    )

    total_volume = (
        buy_volume
        + sell_volume
    )

    if total_volume > 0:

        buy_ratio = (
            buy_volume
            / total_volume
        )

        sell_ratio = (
            sell_volume
            / total_volume
        )

    else:

        buy_ratio = 0.0
        sell_ratio = 0.0

    # --------------------------------
    # Flow classification
    # --------------------------------

    if buy_ratio >= 0.65:

        flow = "accumulation"

    elif sell_ratio >= 0.65:

        flow = "distribution"

    else:

        flow = "balanced"

    # --------------------------------
    # Smart trader quality
    # --------------------------------

    average_trader_score = (
        sum(
            trader["score"]
            for trader in smart_traders
        )
        / len(smart_traders)
    )

    # --------------------------------
    # Risk traders among Smart Money
    # --------------------------------

    risk_smart_traders = sum(
        1
        for trader in smart_traders
        if trader["risk_labels"]
    )

    risk_ratio = (
        risk_smart_traders
        / len(smart_traders)
    )

    # --------------------------------
    # Flow score
    # --------------------------------

    if buy_ratio >= 0.80:

        flow_score = 90

    elif buy_ratio >= 0.70:

        flow_score = 80

    elif buy_ratio >= 0.60:

        flow_score = 70

    elif buy_ratio >= 0.50:

        flow_score = 55

    elif buy_ratio >= 0.40:

        flow_score = 45

    else:

        flow_score = 30

    # --------------------------------
    # Risk adjustment
    # --------------------------------

    risk_penalty = round(
        risk_ratio * 25
    )

    smart_money_score = (
        flow_score
        + (
            average_trader_score
            - 50
        ) * 0.35
        - risk_penalty
    )

    smart_money_score = max(
        0,
        min(
            100,
            round(
                smart_money_score
            ),
        ),
    )

    # --------------------------------
    # Confidence
    # --------------------------------

    confidence = 60

    if len(smart_traders) >= 5:

        confidence += 10

    if len(smart_traders) >= 10:

        confidence += 10

    if total_volume > 0:

        confidence += 10

    if risk_ratio <= 0.20:

        confidence += 5

    confidence = min(
        95,
        confidence,
    )

    warnings = []

    if len(smart_traders) < 5:

        warnings.append(
            "عدد محافظ Smart Money صغير."
        )

    if risk_ratio >= 0.30:

        warnings.append(
            "نسبة مرتفعة من محافظ Smart Money "
            "لديها Labels عالية المخاطر."
        )

    if flow == "accumulation":

        warnings.append(
            "توجد إشارة تراكم من المحافظ المصنفة "
            "Smart/Pro، لكنها ليست إشارة شراء مستقلة."
        )

    elif flow == "distribution":

        warnings.append(
            "توجد إشارة توزيع من المحافظ المصنفة "
            "Smart/Pro."
        )

    else:

        warnings.append(
            "تدفق Smart Money متوازن نسبيًا."
        )

    return {
        "status": "ok",

        "confidence": confidence,

        "total_traders": len(traders),

        "smart_traders": len(
            smart_traders
        ),

        "risk_smart_traders": (
            risk_smart_traders
        ),

        "risk_ratio": round(
            risk_ratio,
            4,
        ),

        "smart_money_buy_volume_usd": round(
            buy_volume,
            2,
        ),

        "smart_money_sell_volume_usd": round(
            sell_volume,
            2,
        ),

        "smart_money_buy_ratio": round(
            buy_ratio,
            4,
        ),

        "smart_money_sell_ratio": round(
            sell_ratio,
            4,
        ),

        "average_smart_trader_score": round(
            average_trader_score,
            2,
        ),

        "smart_money_score": (
            smart_money_score
        ),

        "flow": flow,

        "traders": smart_traders,

        "warnings": warnings,
  }
