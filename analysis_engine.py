from __future__ import annotations

from typing import Any

from data.mobula import get_token_trader_positions

from market.market_intelligence import (
    analyze_market_intelligence,
)

from intelligence.trader_intelligence import (
    analyze_traders,
)

from intelligence.smart_money import (
    analyze_smart_money,
)

from intelligence.funding_intelligence import (
    analyze_funding_relationships,
)

from scoring.composite_score import (
    calculate_composite_score,
)


# =========================================================
# Trader Extraction
# =========================================================

def _looks_like_trader(
    item: Any,
) -> bool:

    if not isinstance(item, dict):
        return False

    trader_fields = {
        "walletAddress",
        "tokenAmount",
        "tokenAmountUSD",
        "percentageOfTotalSupply",
        "buys",
        "sells",
        "volumeBuyUSD",
        "volumeSellUSD",
        "labels",
    }

    matches = 0

    for field in trader_fields:

        if field in item:
            matches += 1

    return matches >= 2


def _find_trader_list(
    value: Any,
) -> list[dict[str, Any]]:

    if isinstance(value, list):

        trader_items = [
            item
            for item in value
            if _looks_like_trader(item)
        ]

        if trader_items:
            return trader_items

        for item in value:

            result = _find_trader_list(
                item
            )

            if result:
                return result

        return []

    if isinstance(value, dict):

        preferred_keys = [
            "data",
            "traders",
            "positions",
            "items",
            "results",
        ]

        for key in preferred_keys:

            if key in value:

                result = _find_trader_list(
                    value[key]
                )

                if result:
                    return result

        for nested_value in value.values():

            result = _find_trader_list(
                nested_value
            )

            if result:
                return result

    return []


# =========================================================
# Main Intelligence Engine
# =========================================================

async def analyze_intelligence_layers(
    mint: str,
    security_score: float,
    liquidity_score: float,
    holder_score: float,
    pair: dict[str, Any] | None = None,
) -> dict[str, Any]:

    result = {
        "status": "ok",
        "mint": mint,

        "market": None,

        "trader_count": 0,
        "traders": None,

        "smart_money": None,

        "funding": None,

        "composite": None,

        "warnings": [],
    }

    # =====================================================
    # 1. Market Intelligence
    # =====================================================

    if pair is not None:

        try:

            market_analysis = (
                analyze_market_intelligence(
                    pair
                )
            )

            result["market"] = (
                market_analysis
            )

        except Exception as error:

            result["status"] = "partial"

            result["warnings"].append(
                "حدث خطأ في Market Intelligence."
            )

            result["warnings"].append(
                str(error)
            )

    else:

        result["status"] = "partial"

        result["warnings"].append(
            "لم يتم تمرير بيانات السوق إلى Market Intelligence."
        )

    # =====================================================
    # 2. Trader Intelligence
    # =====================================================

    try:

        trader_response = (
            await get_token_trader_positions(
                mint
            )
        )

    except Exception as error:

        result["status"] = "partial"

        result["warnings"].append(
            "تعذر الحصول على بيانات المتداولين من Mobula."
        )

        result["warnings"].append(
            str(error)
        )

        trader_response = {}

    traders = _find_trader_list(
        trader_response
    )

    result["trader_count"] = len(
        traders
    )

    if not traders:

        result["status"] = "partial"

        result["warnings"].append(
            "تم الاتصال بـ Mobula ولكن لم يتم العثور "
            "على قائمة متداولين قابلة للتحليل."
        )

    # =====================================================
    # 3. Trader Analysis
    # =====================================================

    try:

        trader_analysis = analyze_traders(
            traders
        )

        result["traders"] = (
            trader_analysis
        )

    except Exception as error:

        result["status"] = "partial"

        result["warnings"].append(
            "حدث خطأ في Trader Intelligence."
        )

        result["warnings"].append(
            str(error)
        )

        trader_analysis = {
            "status": "error",
            "confidence": 0,
            "average_score": 0,
        }

    # =====================================================
    # 4. Smart Money
    # =====================================================

    try:

        smart_money_analysis = (
            analyze_smart_money(
                traders
            )
        )

        result["smart_money"] = (
            smart_money_analysis
        )

    except Exception as error:

        result["status"] = "partial"

        result["warnings"].append(
            "حدث خطأ في Smart Money."
        )

        result["warnings"].append(
            str(error)
        )

        smart_money_analysis = {
            "status": "error",
            "confidence": 0,
            "smart_money_score": 0,
            "flow": "balanced",
        }

    # =====================================================
    # 5. Funding Intelligence
    # =====================================================

    try:

        funding_analysis = (
            analyze_funding_relationships(
                traders
            )
        )

        result["funding"] = (
            funding_analysis
        )

    except Exception as error:

        result["status"] = "partial"

        result["warnings"].append(
            "حدث خطأ في Funding Intelligence."
        )

        result["warnings"].append(
            str(error)
        )

        funding_analysis = {
            "status": "error",
            "confidence": 0,
            "risk_score": 50,
        }

    # =====================================================
    # 6. Composite Score
    # =====================================================

    try:

        composite = (
            calculate_composite_score(
                security_score=security_score,
                liquidity_score=liquidity_score,
                holder_score=holder_score,
                trader_analysis=trader_analysis,
                smart_money_analysis=smart_money_analysis,
                funding_analysis=funding_analysis,
            )
        )

        result["composite"] = (
            composite
        )

    except Exception as error:

        result["status"] = "partial"

        result["warnings"].append(
            "حدث خطأ في Composite Score."
        )

        result["warnings"].append(
            str(error)
        )

    # =====================================================
    # 7. Market Summary Warnings
    # =====================================================

    market = result.get(
        "market"
    )

    if isinstance(
        market,
        dict,
    ):

        market_warnings = market.get(
            "warnings",
            [],
        )

        if isinstance(
            market_warnings,
            list,
        ):

            result["warnings"].extend(
                market_warnings[:10]
            )

    # =====================================================
    # 8. Remove Duplicate Warnings
    # =====================================================

    unique_warnings = []

    for warning in result["warnings"]:

        if warning not in unique_warnings:

            unique_warnings.append(
                warning
            )

    result["warnings"] = (
        unique_warnings[:15]
    )

    return result
