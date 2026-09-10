from __future__ import annotations

from typing import Any


# =========================================================
# Helpers
# =========================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def _clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:

    return max(
        minimum,
        min(maximum, value),
    )


def _score_from_ratio(
    ratio: float,
) -> float:

    ratio = _clamp(
        ratio,
        0.0,
        1.0,
    )

    return ratio * 100.0


# =========================================================
# Transaction Extraction
# =========================================================

def _extract_txns(pair: dict[str, Any]) -> dict[str, int]:

    txns = pair.get(
        "txns",
        {},
    )

    if not isinstance(txns, dict):
        return {
            "buys": 0,
            "sells": 0,
        }

    h24 = txns.get(
        "h24",
        {},
    )

    if not isinstance(h24, dict):
        return {
            "buys": 0,
            "sells": 0,
        }

    return {
        "buys": _safe_int(
            h24.get("buys")
        ),
        "sells": _safe_int(
            h24.get("sells")
        ),
    }


# =========================================================
# Price Changes
# =========================================================

def _extract_price_changes(
    pair: dict[str, Any],
) -> dict[str, float]:

    changes = pair.get(
        "priceChange",
        {},
    )

    if not isinstance(changes, dict):
        changes = {}

    return {
        "m5": _safe_float(
            changes.get("m5")
        ),
        "h1": _safe_float(
            changes.get("h1")
        ),
        "h6": _safe_float(
            changes.get("h6")
        ),
        "h24": _safe_float(
            changes.get("h24")
        ),
    }


# =========================================================
# Buy / Sell Pressure
# =========================================================

def analyze_buy_sell_pressure(
    pair: dict[str, Any],
) -> dict[str, Any]:

    txns = _extract_txns(
        pair
    )

    buys = txns["buys"]
    sells = txns["sells"]

    total_transactions = (
        buys + sells
    )

    if total_transactions <= 0:

        return {
            "status": "insufficient_data",
            "confidence": 0,
            "buys": 0,
            "sells": 0,
            "buy_ratio": 0.0,
            "sell_ratio": 0.0,
            "pressure_score": 50.0,
            "pressure": "unknown",
            "warnings": [
                "لا توجد بيانات كافية عن عمليات الشراء والبيع."
            ],
        }

    buy_ratio = (
        buys / total_transactions
    )

    sell_ratio = (
        sells / total_transactions
    )

    pressure_score = (
        buy_ratio * 100
    )

    if buy_ratio >= 0.65:

        pressure = "strong_buy"

    elif buy_ratio >= 0.55:

        pressure = "buy"

    elif sell_ratio >= 0.65:

        pressure = "strong_sell"

    elif sell_ratio >= 0.55:

        pressure = "sell"

    else:

        pressure = "balanced"

    warnings = []

    if sell_ratio >= 0.65:

        warnings.append(
            "ضغط بيع مرتفع في عدد الصفقات."
        )

    if buy_ratio >= 0.65:

        warnings.append(
            "ضغط شراء مرتفع في عدد الصفقات."
        )

    return {
        "status": "ok",
        "confidence": 100,
        "buys": buys,
        "sells": sells,
        "total_transactions": total_transactions,
        "buy_ratio": buy_ratio,
        "sell_ratio": sell_ratio,
        "pressure_score": pressure_score,
        "pressure": pressure,
        "warnings": warnings,
    }


# =========================================================
# Volume Quality
# =========================================================

def analyze_volume_quality(
    pair: dict[str, Any],
) -> dict[str, Any]:

    liquidity_data = pair.get(
        "liquidity",
        {},
    )

    volume_data = pair.get(
        "volume",
        {},
    )

    if not isinstance(
        liquidity_data,
        dict,
    ):
        liquidity_data = {}

    if not isinstance(
        volume_data,
        dict,
    ):
        volume_data = {}

    liquidity = _safe_float(
        liquidity_data.get("usd")
    )

    volume_24h = _safe_float(
        volume_data.get("h24")
    )

    if liquidity <= 0:

        return {
            "status": "insufficient_data",
            "confidence": 0,
            "liquidity_usd": liquidity,
            "volume_24h_usd": volume_24h,
            "volume_liquidity_ratio": 0.0,
            "volume_score": 0.0,
            "quality": "unknown",
            "warnings": [
                "لا توجد بيانات سيولة كافية لتقييم جودة الحجم."
            ],
        }

    volume_liquidity_ratio = (
        volume_24h / liquidity
    )

    # -----------------------------------------------------
    # Volume quality heuristic
    #
    # 0.1x - 0.5x  = low activity
    # 0.5x - 1.0x  = healthy
    # 1.0x - 3.0x  = strong
    # 3.0x+        = unusually active
    #
    # High volume is NOT automatically good.
    # Extremely high volume relative to liquidity can
    # indicate speculative or unstable activity.
    # -----------------------------------------------------

    if volume_liquidity_ratio < 0.1:

        volume_score = 25.0
        quality = "very_low"

    elif volume_liquidity_ratio < 0.5:

        volume_score = 50.0
        quality = "low"

    elif volume_liquidity_ratio < 1.0:

        volume_score = 70.0
        quality = "healthy"

    elif volume_liquidity_ratio < 3.0:

        volume_score = 85.0
        quality = "strong"

    elif volume_liquidity_ratio < 6.0:

        volume_score = 70.0
        quality = "very_high"

    else:

        volume_score = 50.0
        quality = "extreme"

    warnings = []

    if volume_liquidity_ratio >= 6.0:

        warnings.append(
            "الحجم مرتفع جدًا مقارنة بالسيولة وقد يعكس نشاطًا مضاربيًا شديدًا."
        )

    elif volume_liquidity_ratio >= 3.0:

        warnings.append(
            "الحجم مرتفع جدًا مقارنة بالسيولة ويحتاج إلى مراقبة."
        )

    if volume_liquidity_ratio < 0.1:

        warnings.append(
            "النشاط التداولي منخفض جدًا مقارنة بالسيولة."
        )

    return {
        "status": "ok",
        "confidence": 100,
        "liquidity_usd": liquidity,
        "volume_24h_usd": volume_24h,
        "volume_liquidity_ratio": volume_liquidity_ratio,
        "volume_score": volume_score,
        "quality": quality,
        "warnings": warnings,
    }


# =========================================================
# Momentum Intelligence
# =========================================================

def analyze_momentum(
    pair: dict[str, Any],
) -> dict[str, Any]:

    changes = _extract_price_changes(
        pair
    )

    m5 = changes["m5"]
    h1 = changes["h1"]
    h6 = changes["h6"]
    h24 = changes["h24"]

    # -----------------------------------------------------
    # Multi-timeframe momentum
    # -----------------------------------------------------

    score = 50.0

    # Short-term momentum
    if m5 > 3:
        score += 10

    elif m5 > 1:
        score += 5

    elif m5 < -3:
        score -= 10

    elif m5 < -1:
        score -= 5

    # 1h momentum
    if h1 > 8:
        score += 15

    elif h1 > 3:
        score += 8

    elif h1 > 0:
        score += 3

    elif h1 < -8:
        score -= 15

    elif h1 < -3:
        score -= 8

    elif h1 < 0:
        score -= 3

    # 6h momentum
    if h6 > 15:
        score += 10

    elif h6 > 5:
        score += 5

    elif h6 < -15:
        score -= 10

    elif h6 < -5:
        score -= 5

    # 24h context
    if h24 > 25:
        score += 5

    elif h24 < -25:
        score -= 5

    score = _clamp(
        score
    )

    # -----------------------------------------------------
    # Momentum state
    # -----------------------------------------------------

    if (
        h1 >= 5
        and h6 >= 5
        and m5 >= 0
    ):

        state = "bullish"

    elif (
        h1 <= -5
        and h6 <= -5
        and m5 <= 0
    ):

        state = "bearish"

    elif (
        h1 > 0
        and h6 > 0
    ):

        state = "developing_bullish"

    elif (
        h1 < 0
        and h6 < 0
    ):

        state = "developing_bearish"

    else:

        state = "mixed"

    warnings = []

    # Strong 24h move with weak short-term momentum
    if h24 > 20 and h1 < 0:

        warnings.append(
            "ارتفاع يومي قوي مع ضعف في زخم الساعة الأخيرة."
        )

    if h24 < -20 and h1 > 0:

        warnings.append(
            "انخفاض يومي قوي مع تحسن قصير الأجل؛ قد يكون ارتدادًا."
        )

    if abs(h1) > 20:

        warnings.append(
            "تقلب مرتفع خلال آخر ساعة."
        )

    return {
        "status": "ok",
        "confidence": 100,
        "score": score,
        "state": state,
        "price_change_5m": m5,
        "price_change_1h": h1,
        "price_change_6h": h6,
        "price_change_24h": h24,
        "warnings": warnings,
    }


# =========================================================
# Market Structure Proxy
# =========================================================

def analyze_market_structure(
    pair: dict[str, Any],
) -> dict[str, Any]:

    changes = _extract_price_changes(
        pair
    )

    m5 = changes["m5"]
    h1 = changes["h1"]
    h6 = changes["h6"]
    h24 = changes["h24"]

    score = 50.0

    # Positive alignment across timeframes
    positive_frames = sum(
        1
        for value in [
            m5,
            h1,
            h6,
            h24,
        ]
        if value > 0
    )

    negative_frames = sum(
        1
        for value in [
            m5,
            h1,
            h6,
            h24,
        ]
        if value < 0
    )

    if positive_frames >= 4:

        score += 35

        structure = "bullish_alignment"

    elif positive_frames >= 3:

        score += 20

        structure = "positive_alignment"

    elif negative_frames >= 4:

        score -= 35

        structure = "bearish_alignment"

    elif negative_frames >= 3:

        score -= 20

        structure = "negative_alignment"

    else:

        structure = "mixed"

    # Acceleration / deceleration proxy
    if h1 > 0 and h6 > h1:

        score += 5

    if h1 < 0 and h6 < h1:

        score -= 5

    score = _clamp(
        score
    )

    warnings = [
        "هذا تحليل هيكلي تقريبي وليس تحليل دعم ومقاومة من شموع OHLC."
    ]

    if (
        h24 > 20
        and h1 < 0
    ):

        warnings.append(
            "السياق اليومي قوي لكن الزخم القصير لا يؤكده."
        )

    if (
        h24 < -20
        and h1 > 0
    ):

        warnings.append(
            "السياق اليومي ضعيف لكن هناك تحسنًا قصير الأجل."
        )

    return {
        "status": "ok",
        "confidence": 60,
        "score": score,
        "structure": structure,
        "positive_frames": positive_frames,
        "negative_frames": negative_frames,
        "warnings": warnings,
    }


# =========================================================
# Combined Market Intelligence
# =========================================================

def analyze_market_intelligence(
    pair: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(pair, dict):

        return {
            "status": "error",
            "confidence": 0,
            "market_score": 0,
            "warnings": [
                "بيانات السوق غير صالحة."
            ],
        }

    pressure = analyze_buy_sell_pressure(
        pair
    )

    volume = analyze_volume_quality(
        pair
    )

    momentum = analyze_momentum(
        pair
    )

    structure = analyze_market_structure(
        pair
    )

    # -----------------------------------------------------
    # Combined Market Score
    #
    # Pressure       30%
    # Volume Quality 25%
    # Momentum       30%
    # Structure      15%
    # -----------------------------------------------------

    market_score = (
        pressure["pressure_score"] * 0.30
        + volume["volume_score"] * 0.25
        + momentum["score"] * 0.30
        + structure["score"] * 0.15
    )

    market_score = _clamp(
        market_score
    )

    warnings = []

    warnings.extend(
        pressure.get(
            "warnings",
            [],
        )
    )

    warnings.extend(
        volume.get(
            "warnings",
            [],
        )
    )

    warnings.extend(
        momentum.get(
            "warnings",
            [],
        )
    )

    warnings.extend(
        structure.get(
            "warnings",
            [],
        )
    )

    # Remove duplicates while preserving order
    unique_warnings = []

    for warning in warnings:

        if warning not in unique_warnings:

            unique_warnings.append(
                warning
            )

    # -----------------------------------------------------
    # Market State
    # -----------------------------------------------------

    if (
        market_score >= 75
        and momentum["state"] in {
            "bullish",
            "developing_bullish",
        }
        and pressure["pressure"] in {
            "buy",
            "strong_buy",
        }
    ):

        market_state = "bullish"

    elif (
        market_score <= 35
        and momentum["state"] in {
            "bearish",
            "developing_bearish",
        }
        and pressure["pressure"] in {
            "sell",
            "strong_sell",
        }
    ):

        market_state = "bearish"

    elif market_score >= 60:

        market_state = "constructive"

    elif market_score <= 40:

        market_state = "weak"

    else:

        market_state = "neutral"

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    confidence_components = [
        pressure.get(
            "confidence",
            0,
        ),
        volume.get(
            "confidence",
            0,
        ),
        momentum.get(
            "confidence",
            0,
        ),
        structure.get(
            "confidence",
            0,
        ),
    ]

    confidence = (
        sum(confidence_components)
        / len(confidence_components)
    )

    return {
        "status": "ok",
        "confidence": confidence,
        "market_score": market_score,
        "market_state": market_state,
        "buy_sell_pressure": pressure,
        "volume_quality": volume,
        "momentum": momentum,
        "market_structure": structure,
        "warnings": unique_warnings[:10],
            }
