from __future__ import annotations

from typing import Any

from data.mobula import get_token_trader_positions

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


def _looks_like_trader(item: Any) -> bool:
    """
    التحقق من أن العنصر يشبه سجل متداول Mobula.
    """

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
    """
    البحث بشكل recursive عن قائمة تحتوي
    على سجلات المتداولين.

    هذا يجعل المحرك متوافقًا مع اختلاف
    بنية استجابة Mobula.
    """

    if isinstance(value, list):

        trader_items = [
            item
            for item in value
            if _looks_like_trader(item)
        ]

        if trader_items:
            return trader_items

        for item in value:

            result = _find_trader_list(item)

            if result:
                return result

        return []

    if isinstance(value, dict):

        # الحالات الشائعة أولًا
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

        # البحث داخل جميع القيم
        for nested_value in value.values():

            result = _find_trader_list(
                nested_value
            )

            if result:
                return result

    return []


async def analyze_intelligence_layers(
    mint: str,
    security_score: float,
    liquidity_score: float,
    holder_score: float,
) -> dict[str, Any]:
    """
    تشغيل طبقات الذكاء التحليلي:

    Mobula
        ↓
    Trader Intelligence
        ↓
    Smart Money
        ↓
    Funding Intelligence
        ↓
    Composite Score

    لا توجد أي عمليات تداول.
    """

    result: dict[str, Any] = {
        "status": "ok",
        "mint": mint,
        "trader_count": 0,
        "traders": None,
        "smart_money": None,
        "funding": None,
        "composite": None,
        "warnings": [],
    }

    # ==================================================
    # 1. الحصول على بيانات المتداولين من Mobula
    # ==================================================

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

    # ==================================================
    # 2. استخراج قائمة المتداولين
    # ==================================================

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

    # ==================================================
    # 3. Trader Intelligence
    # ==================================================

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

    # ==================================================
    # 4. Smart Money
    # ==================================================

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

    # ==================================================
    # 5. Funding Intelligence
    # ==================================================

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

    # ==================================================
    # 6. Composite Score
    # ==================================================

    try:

        composite = (
            calculate_composite_score(

                security_score=security_score,

                liquidity_score=liquidity_score,

                holder_score=holder_score,

                trader_analysis=(
                    trader_analysis
                ),

                smart_money_analysis=(
                    smart_money_analysis
                ),

                funding_analysis=(
                    funding_analysis
                ),
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

    return result
