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


def _safe_float(value: Any) -> float | None:
    """
    تحويل القيمة إلى float.
    نرجع None إذا لم تكن البيانات موجودة أو صالحة.
    """

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


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


def _get_total_pnl(
    trader: dict[str, Any],
) -> tuple[float | None, str]:

    """
    استخدام Total PnL الحقيقي إذا كان متوفرًا.

    الأولوية:
    1. totalPnlUSD
    2. realizedPnlUSD + unrealizedPnlUSD

    لا نعتمد pnlUSD القديم.
    """

    total = _safe_float(
        trader.get("totalPnlUSD")
    )

    if total is not None:
        return total, "totalPnlUSD"

    realized = _safe_float(
        trader.get("realizedPnlUSD")
    )

    unrealized = _safe_float(
        trader.get("unrealizedPnlUSD")
    )

    if realized is not None or unrealized is not None:

        realized = (
            realized
            if realized is not None
            else 0.0
        )

        unrealized = (
            unrealized
            if unrealized is not None
            else 0.0
        )

        return (
            realized + unrealized,
            "realizedPnlUSD+unrealizedPnlUSD",
        )

    return None, "missing"


def _analyze_single_trader(
    trader: dict[str, Any],
) -> dict[str, Any]:

    labels = _normalize_labels(
        trader.get("labels")
    )

    total_pnl, pnl_source = _get_total_pnl(
        trader
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

    buy_volume = (
        buy_volume
        if buy_volume is not None
        else 0.0
    )

    sell_volume = (
        sell_volume
        if sell_volume is not None
        else 0.0
    )

    total_volume = (
        buy_volume
        + sell_volume
    )

    trade_count = (
        buys
        + sells
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

    risk_labels = (
        labels & RISK_LABELS
    )

    smart_labels = (
        labels & SMART_LABELS
    )

    score = 50

    evidence = []

    # -------------------------
    # Smart / professional labels
    # -------------------------

    if "smartTrader" in labels:

        score += 20

        evidence.append(
            "لدى المحفظة تصنيف smartTrader."
        )

    elif "proTrader" in labels:

        score += 15

        evidence.append(
            "لدى المحفظة تصنيف proTrader."
        )

    # -------------------------
    # Risk labels
    # -------------------------

    if risk_labels:

        score -= 20

        evidence.append(
            "توجد Labels عالية المخاطر: "
            + ", ".join(
                sorted(risk_labels)
            )
        )

    # -------------------------
    # PnL
    # -------------------------

    pnl_available = (
        total_pnl is not None
    )

    profitable = False

    losing = False

    if pnl_available:

        if total_pnl > 0:

            profitable = True

            score += 10

            evidence.append(
                "إجمالي PnL موجب."
            )

        elif total_pnl < 0:

            losing = True

            score -= 10

            evidence.append(
                "إجمالي PnL سالب."
            )

        else:

            evidence.append(
                "إجمالي PnL يساوي تقريبًا صفر."
            )

    else:

        evidence.append(
            "بيانات PnL غير متوفرة."
        )

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
    # Buy / Sell pressure
    # -------------------------

    if buy_ratio >= 0.70:

        evidence.append(
            "هيمنة قوية لحجم الشراء."
        )

    elif sell_ratio >= 0.70:

        evidence.append(
            "هيمنة قوية لحجم البيع."
        )

    # -------------------------
    # Score
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

        "smart_labels": sorted(
            smart_labels
        ),

        "risk_labels": sorted(
            risk_labels
        ),

        "total_pnl_usd": total_pnl,

        "pnl_source": pnl_source,

        "pnl_available": pnl_available,

        "profitable": profitable,

        "losing": losing,

        "realized_pnl_usd": realized_pnl,

        "unrealized_pnl_usd": unrealized_pnl,

        "buys": buys,

        "sells": sells,

        "trade_count": trade_count,

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

        "score": score,

        "grade": grade,

        "evidence": evidence,
    }


def analyze_traders(
    traders: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    تحليل مجموعة المتداولين.

    لا نعتبر Label وحدها دليلًا على
    Smart Money أو التلاعب.

    ولا نعتبر PnL مفقودًا مساويًا للصفر.
    """

    if not traders:

        return {
            "status": "insufficient_data",
            "confidence": 0,
            "total_traders": 0,
            "pnl_available_traders": 0,
            "profitable_traders": 0,
            "losing_traders": 0,
            "smart_traders": 0,
            "risk_traders": 0,
            "average_score": 0,
            "warnings": [
                "لا توجد بيانات متداولين كافية."
            ],
        }

    analyzed = [
        _analyze_single_trader(
            trader
        )
        for trader in traders
    ]

    total = len(analyzed)

    pnl_available_traders = sum(
        1
        for trader in analyzed
        if trader["pnl_available"]
    )

    profitable_traders = sum(
        1
        for trader in analyzed
        if trader["profitable"]
    )

    losing_traders = sum(
        1
        for trader in analyzed
        if trader["losing"]
    )

    smart_traders = sum(
        1
        for trader in analyzed
        if trader["smart_labels"]
    )

    risk_traders = sum(
        1
        for trader in analyzed
        if trader["risk_labels"]
    )

    total_score = sum(
        trader["score"]
        for trader in analyzed
    )

    average_score = (
        total_score / total
    )

    total_buy_volume = sum(
        trader["buy_volume_usd"]
        for trader in analyzed
    )

    total_sell_volume = sum(
        trader["sell_volume_usd"]
        for trader in analyzed
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

    # -------------------------
    # PnL coverage
    # -------------------------

    pnl_coverage = (
        pnl_available_traders
        / total
    )

    # -------------------------
    # Confidence
    # -------------------------

    confidence = round(
        pnl_coverage * 100
    )

    warnings = []

    if total < 30:

        warnings.append(
            "عينة المتداولين صغيرة."
        )

    if pnl_available_traders == 0:

        warnings.append(
            "لا توجد بيانات PnL صالحة."
        )

    elif pnl_coverage < 0.50:

        warnings.append(
            "تغطية PnL أقل من 50%."
        )

    if risk_traders > 0:

        warnings.append(
            f"تم العثور على {risk_traders} "
            "متداولين لديهم Labels عالية المخاطر."
        )

    if smart_traders > 0:

        warnings.append(
            f"تم العثور على {smart_traders} "
            "متداولين لديهم Labels احترافية."
        )

    if aggregate_buy_ratio > 0.60:

        warnings.append(
            "ضغط الشراء أعلى من ضغط البيع."
        )

    elif aggregate_sell_ratio > 0.60:

        warnings.append(
            "ضغط البيع أعلى من ضغط الشراء."
        )

    # -------------------------
    # PnL ratio
    # -------------------------

    if pnl_available_traders > 0:

        profitable_ratio = (
            profitable_traders
            / pnl_available_traders
        )

        losing_ratio = (
            losing_traders
            / pnl_available_traders
        )

    else:

        profitable_ratio = 0.0
        losing_ratio = 0.0

    return {
        "status": "ok",

        "confidence": confidence,

        "total_traders": total,

        "pnl_available_traders": (
            pnl_available_traders
        ),

        "pnl_coverage": round(
            pnl_coverage,
            4,
        ),

        "profitable_traders": (
            profitable_traders
        ),

        "losing_traders": (
            losing_traders
        ),

        "profitable_ratio": round(
            profitable_ratio,
            4,
        ),

        "losing_ratio": round(
            losing_ratio,
            4,
        ),

        "smart_traders": (
            smart_traders
        ),

        "risk_traders": (
            risk_traders
        ),

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
