from __future__ import annotations

from typing import Any


RISK_LABELS = {
    "bundler",
    "sniper",
    "insider",
}


SMART_LABELS = {
    "smartTrader",
    "proTrader",
}


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0

        return float(value)

    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0

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


def _trader_score(
    trader: dict[str, Any],
) -> dict[str, Any]:

    labels = _normalize_labels(
        trader.get("labels")
    )

    pnl = _safe_float(
        trader.get("pnlUSD")
    )

    realized_pnl = _safe_float(
        trader.get("realizedPnlUSD")
    )

    unrealized_pnl = _safe_float(
        trader.get("unrealizedPnlUSD")
    )

    buys = _safe_int(
        trader.get("buys")
    )

    sells = _safe_int(
        trader.get("sells")
    )

    buy_volume = _safe_float(
        trader.get("volumeBuyUSD")
    )

    sell_volume = _safe_float(
        trader.get("volumeSellUSD")
    )

    total_volume = buy_volume + sell_volume

    trade_count = buys + sells

    score = 50

    evidence = []

    # -------------------------
    # Labels
    # -------------------------

    if "smartTrader" in labels:
        score += 20
        evidence.append(
            "Mobula يصنف المحفظة Smart Trader."
        )

    elif "proTrader" in labels:
        score += 15
        evidence.append(
            "Mobula يصنف المحفظة Pro Trader."
        )

    risk_labels = labels & RISK_LABELS

    if risk_labels:
        score -= 20

        evidence.append(
            "توجد Labels عالية المخاطر: "
            + ", ".join(sorted(risk_labels))
        )

    # -------------------------
    # PnL
    # -------------------------

    if pnl > 0:
        score += 10

        evidence.append(
            "PnL الإجمالي موجب."
        )

    elif pnl < 0:
        score -= 10

        evidence.append(
            "PnL الإجمالي سالب."
        )

    if realized_pnl > 0:
        score += 5

    elif realized_pnl < 0:
        score -= 5

    # -------------------------
    # Trading activity
    # -------------------------

    if trade_count >= 20:
        score += 5

    elif trade_count == 0:
        score -= 10

        evidence.append(
            "لا توجد عمليات تداول كافية."
        )

    # -------------------------
    # Buy / Sell balance
    # -------------------------

    if total_volume > 0:

        buy_ratio = (
            buy_volume / total_volume
        )

        sell_ratio = (
            sell_volume / total_volume
        )

    else:

        buy_ratio = 0.0
        sell_ratio = 0.0

    # نشاط شراء قوي، لكن لا نعتبره إيجابيًا تلقائيًا.
    if buy_ratio >= 0.70:

        evidence.append(
            "هيمنة واضحة لحجم الشراء."
        )

    elif sell_ratio >= 0.70:

        evidence.append(
            "هيمنة واضحة لحجم البيع."
        )

    # -------------------------
    # Clamp
    # -------------------------

    score = max(
        0,
        min(100, score),
    )

    if score >= 80:
        grade = "قوي"

    elif score >= 65:
        grade = "جيد"

    elif score >= 50:
        grade = "محايد"

    elif score >= 35:
        grade = "ضعيف"

    else:
        grade = "عالي المخاطر"

    return {
        "wallet_address": trader.get(
            "walletAddress"
        ),
        "labels": sorted(labels),
        "risk_labels": sorted(risk_labels),
        "pnl_usd": pnl,
        "realized_pnl_usd": realized_pnl,
        "unrealized_pnl_usd": unrealized_pnl,
        "buys": buys,
        "sells": sells,
        "buy_volume_usd": buy_volume,
        "sell_volume_usd": sell_volume,
        "trade_count": trade_count,
        "buy_ratio": round(
            buy_ratio,
            4,
        ),
        "sell_ratio": round(
            sell_ratio,
            4,
        ),
        "score": score,
        "grade": grade,
        "evidence": evidence,
    }


def analyze_traders(
    traders: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    تحليل مجموعة المتداولين.

    مهم:
    هذا المحلل لا يعتبر Labels وحدها دليلًا
    على Smart Money أو التلاعب.
    """

    if not traders:

        return {
            "status": "insufficient_data",
            "confidence": 0,
            "total_traders": 0,
            "smart_traders": 0,
            "risk_traders": 0,
            "profitable_traders": 0,
            "average_score": 0,
            "warnings": [
                "لا توجد بيانات متداولين كافية."
            ],
        }

    analyzed = [
        _trader_score(trader)
        for trader in traders
    ]

    smart_traders = 0
    risk_traders = 0
    profitable_traders = 0

    total_score = 0

    total_buy_volume = 0.0
    total_sell_volume = 0.0

    for trader in analyzed:

        labels = set(
            trader["labels"]
        )

        if labels & SMART_LABELS:
            smart_traders += 1

        if labels & RISK_LABELS:
            risk_traders += 1

        if trader["pnl_usd"] > 0:
            profitable_traders += 1

        total_score += trader["score"]

        total_buy_volume += (
            trader["buy_volume_usd"]
        )

        total_sell_volume += (
            trader["sell_volume_usd"]
        )

    average_score = (
        total_score / len(analyzed)
    )

    total_volume = (
        total_buy_volume
        + total_sell_volume
    )

    if total_volume > 0:

        aggregate_buy_ratio = (
            total_buy_volume
            / total_volume
        )

        aggregate_sell_ratio = (
            total_sell_volume
            / total_volume
        )

    else:

        aggregate_buy_ratio = 0.0
        aggregate_sell_ratio = 0.0

    coverage = len(analyzed) / len(traders)

    confidence = round(
        coverage * 100
    )

    warnings = []

    if len(analyzed) < 30:
        warnings.append(
            "عينة المتداولين صغيرة."
        )

    if risk_traders > 0:
        warnings.append(
            f"تم العثور على {risk_traders} "
            "متداولين لديهم Labels عالية المخاطر."
        )

    if smart_traders > 0:
        warnings.append(
            f"تم العثور على {smart_traders} "
            "متداولين لديهم Labels إيجابية."
        )

    return {
        "status": "ok",
        "confidence": confidence,
        "total_traders": len(analyzed),

        "smart_traders": smart_traders,
        "risk_traders": risk_traders,
        "profitable_traders": profitable_traders,

        "average_score": round(
            average_score,
            2,
        ),

        "total_buy_volume_usd": round(
            total_buy_volume,
            2,
        ),

        "total_sell_volume_usd": round(
            total_sell_volume,
            2,
        ),

        "aggregate_buy_ratio": round(
            aggregate_buy_ratio,
            4,
        ),

        "aggregate_sell_ratio": round(
            aggregate_sell_ratio,
            4,
        ),

        "traders": analyzed,

        "warnings": warnings,
      }
