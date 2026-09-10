from __future__ import annotations

from typing import Any


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    if value is None:
        return default

    try:
        return float(value)

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


def calculate_composite_score(
    security_score: float,
    liquidity_score: float,
    holder_score: float,
    trader_analysis: dict[str, Any],
    smart_money_analysis: dict[str, Any],
    funding_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    دمج طبقات التحليل المختلفة.

    هذا المحرك لا يعطي ضمانًا للربح.
    الهدف هو ترتيب جودة الفرصة بناءً
    على عدة أدلة مستقلة.

    الأوزان الحالية:

    Security       25%
    Liquidity      15%
    Holders        15%
    Traders        10%
    Smart Money    25%
    Funding Risk   10%

    يتم فصل:
    - Opportunity Score
    - Risk Score
    - Confidence
    """

    security = _clamp(
        _safe_float(
            security_score
        )
    )

    liquidity = _clamp(
        _safe_float(
            liquidity_score
        )
    )

    holders = _clamp(
        _safe_float(
            holder_score
        )
    )

    trader_score = _clamp(
        _safe_float(
            trader_analysis.get(
                "average_score"
            )
        )
    )

    smart_money_score = _clamp(
        _safe_float(
            smart_money_analysis.get(
                "smart_money_score"
            )
        )
    )

    funding_risk = _clamp(
        _safe_float(
            funding_analysis.get(
                "risk_score"
            )
        )
    )

    # --------------------------------
    # Base opportunity score
    # --------------------------------

    base_score = (

        security * 0.25

        + liquidity * 0.15

        + holders * 0.15

        + trader_score * 0.10

        + smart_money_score * 0.25

        + (100 - funding_risk) * 0.10

    )

    # --------------------------------
    # Smart Money flow adjustment
    # --------------------------------

    flow = smart_money_analysis.get(
        "flow"
    )

    flow_adjustment = 0.0

    if flow == "accumulation":

        flow_adjustment = 5.0

    elif flow == "distribution":

        flow_adjustment = -5.0

    elif flow == "balanced":

        flow_adjustment = 0.0

    base_score += flow_adjustment

    # --------------------------------
    # Risk score
    # --------------------------------

    risk_score = 100 - base_score

    # Security weakness deserves
    # additional consideration.

    if security < 50:

        risk_score += 15

    elif security < 70:

        risk_score += 7

    # Liquidity weakness.

    if liquidity < 40:

        risk_score += 15

    elif liquidity < 60:

        risk_score += 7

    # Funding risk.

    risk_score += (
        funding_risk * 0.20
    )

    risk_score = _clamp(
        risk_score
    )

    # --------------------------------
    # Opportunity score
    # --------------------------------

    opportunity_score = _clamp(
        100 - risk_score
    )

    # --------------------------------
    # Confidence
    # --------------------------------

    trader_confidence = _safe_float(
        trader_analysis.get(
            "confidence"
        )
    )

    smart_confidence = _safe_float(
        smart_money_analysis.get(
            "confidence"
        )
    )

    funding_confidence = _safe_float(
        funding_analysis.get(
            "confidence"
        )
    )

    confidence_components = [
        trader_confidence,
        smart_confidence,
        funding_confidence,
    ]

    valid_confidence = [
        value
        for value in confidence_components
        if value > 0
    ]

    if valid_confidence:

        confidence = (
            sum(valid_confidence)
            / len(valid_confidence)
        )

    else:

        confidence = 50.0

    # --------------------------------
    # Data quality penalties
    # --------------------------------

    warnings = []

    if trader_confidence < 60:

        confidence -= 10

        warnings.append(
            "ثقة بيانات المتداولين منخفضة."
        )

    if smart_confidence < 60:

        confidence -= 10

        warnings.append(
            "ثقة بيانات Smart Money منخفضة."
        )

    if funding_confidence < 60:

        confidence -= 5

        warnings.append(
            "ثقة بيانات التمويل منخفضة."
        )

    confidence = _clamp(
        confidence
    )

    # --------------------------------
    # Decision state
    # --------------------------------

    if security < 40:

        decision = "AVOID"

        decision_ar = "تجنب"

    elif risk_score >= 75:

        decision = "AVOID"

        decision_ar = "تجنب"

    elif opportunity_score >= 75 and confidence >= 70:

        decision = "WATCH"

        decision_ar = "مراقبة قوية"

    elif opportunity_score >= 60 and confidence >= 60:

        decision = "WATCH"

        decision_ar = "مراقبة"

    else:

        decision = "NEUTRAL"

        decision_ar = "محايد"

    # --------------------------------
    # Grade
    # --------------------------------

    if opportunity_score >= 80:

        grade = "A"

    elif opportunity_score >= 70:

        grade = "B"

    elif opportunity_score >= 60:

        grade = "C"

    elif opportunity_score >= 50:

        grade = "D"

    else:

        grade = "F"

    return {
        "opportunity_score": round(
            opportunity_score,
            2,
        ),

        "risk_score": round(
            risk_score,
            2,
        ),

        "confidence": round(
            confidence,
            2,
        ),

        "grade": grade,

        "decision": decision,

        "decision_ar": decision_ar,

        "components": {
            "security": round(
                security,
                2,
            ),

            "liquidity": round(
                liquidity,
                2,
            ),

            "holders": round(
                holders,
                2,
            ),

            "traders": round(
                trader_score,
                2,
            ),

            "smart_money": round(
                smart_money_score,
                2,
            ),

            "funding_risk": round(
                funding_risk,
                2,
            ),
        },

        "smart_money_flow": flow,

        "flow_adjustment": (
            flow_adjustment
        ),

        "warnings": warnings,
  }
