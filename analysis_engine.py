from __future__ import annotations

from typing import Any

from data.mobula import get_token_trader_positions

from intelligence.trader_intelligence import analyze_traders
from intelligence.smart_money import analyze_smart_money
from intelligence.funding_intelligence import (
    analyze_funding_relationships,
)

from scoring.composite_score import calculate_composite_score


def _extract_list(response: Any) -> list[dict[str, Any]]:
    """
    استخراج قائمة المتداولين من استجابة Mobula
    مع دعم أكثر من شكل للاستجابة.
    """

    if not isinstance(response, dict):
        return []

    data = response.get("data")

    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    if isinstance(data, dict):
        nested = data.get("data")

        if isinstance(nested, list):
            return [
                item
                for item in nested
                if isinstance(item, dict)
            ]

    return []


async def analyze_intelligence_layers(
    mint: str,
    security_score: float,
    liquidity_score: float,
    holder_score: float,
) -> dict[str, Any]:
    """
    تشغيل طبقات Trader Intelligence وSmart Money
    وFunding ثم دمجها في Composite Score.

    هذه الطبقة لا تنفذ أي تداول.
    """

    result: dict[str, Any] = {
        "status": "ok",
        "traders": None,
        "smart_money": None,
        "funding": None,
        "composite": None,
        "warnings": [],
    }

    # -----------------------------------------
    # 1. Mobula Trader Positions
    # -----------------------------------------

    try:
        trader_response = await get_token_trader_positions(
            mint
        )

        traders = _extract_list(
            trader_response
        )

    except Exception as error:
        result["status"] = "partial"

        result["warnings"].append(
            f"تعذر الحصول على بيانات المتداولين: {error}"
        )

        traders = []

    # -----------------------------------------
    # 2. Trader Intelligence
    # -----------------------------------------

    trader_analysis = analyze_traders(
        traders
    )

    result["traders"] = trader_analysis

    # -----------------------------------------
    # 3. Smart Money
    # -----------------------------------------

    smart_money_analysis = analyze_smart_money(
        traders
    )

    result["smart_money"] = (
        smart_money_analysis
    )

    # -----------------------------------------
    # 4. Funding Intelligence
    # -----------------------------------------

    funding_analysis = (
        analyze_funding_relationships(
            traders
        )
    )

    result["funding"] = funding_analysis

    # -----------------------------------------
    # 5. Composite Score
    # -----------------------------------------

    composite = calculate_composite_score(
        security_score=security_score,
        liquidity_score=liquidity_score,
        holder_score=holder_score,
        trader_analysis=trader_analysis,
        smart_money_analysis=smart_money_analysis,
        funding_analysis=funding_analysis,
    )

    result["composite"] = composite

    return result
