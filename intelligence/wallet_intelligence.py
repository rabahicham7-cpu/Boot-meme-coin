import os
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv


load_dotenv()


HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

HELIUS_TRANSACTIONS_URL = (
    "https://api.helius.xyz/v0/addresses"
)


async def get_wallet_transactions(
    wallet_address: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    جلب آخر معاملات محفظة Solana عبر Helius.

    هذه الدالة تجمع البيانات الخام فقط.
    لا تعتبر المحفظة Smart Money.
    """

    if not HELIUS_API_KEY:
        raise RuntimeError(
            "HELIUS_API_KEY غير موجود"
        )

    if not wallet_address:
        return []

    limit = max(
        1,
        min(int(limit), 100)
    )

    url = (
        f"{HELIUS_TRANSACTIONS_URL}/"
        f"{wallet_address}/transactions"
    )

    params = {
        "api-key": HELIUS_API_KEY,
        "limit": limit,
    }

    timeout = aiohttp.ClientTimeout(
        total=20
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.get(
            url,
            params=params
        ) as response:

            data = await response.json(
                content_type=None
            )

            if response.status != 200:

                raise RuntimeError(
                    "Helius transactions HTTP error: "
                    f"{response.status} - {data}"
                )

            if not isinstance(data, list):

                return []

            return data


def analyze_wallet_activity(
    transactions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    تحليل أولي لنشاط المحفظة.

    لا يصدر حكم Smart Money.
    """

    if not isinstance(
        transactions,
        list
    ):

        transactions = []


    transaction_count = len(
        transactions
    )


    swaps = 0
    transfers = 0
    failed = 0


    timestamps = []


    for tx in transactions:

        if not isinstance(
            tx,
            dict
        ):
            continue


        tx_type = str(
            tx.get("type", "")
        ).upper()


        if tx_type == "SWAP":

            swaps += 1


        elif tx_type == "TRANSFER":

            transfers += 1


        if tx.get("transactionError"):

            failed += 1


        timestamp = tx.get(
            "timestamp"
        )


        if isinstance(
            timestamp,
            (int, float)
        ):

            timestamps.append(
                timestamp
            )


    swap_ratio = 0.0

    if transaction_count > 0:

        swap_ratio = (
            swaps
            / transaction_count
        )


    activity_score = 0


    # وجود معاملات فعلية
    if transaction_count >= 5:

        activity_score += 20


    if transaction_count >= 15:

        activity_score += 15


    # نشاط Swap
    if swaps >= 3:

        activity_score += 20


    if swaps >= 10:

        activity_score += 15


    # ارتفاع نسبة عمليات التداول
    if swap_ratio >= 0.30:

        activity_score += 10


    if swap_ratio >= 0.60:

        activity_score += 10


    # فشل معاملات كثيرة يعتبر إشارة سلبية
    if failed > 0:

        activity_score -= min(
            failed * 2,
            15
        )


    activity_score = max(
        0,
        min(
            100,
            activity_score
        )
    )


    warnings = []
    positive = []


    if transaction_count == 0:

        warnings.append(
            "لا توجد معاملات كافية لتحليل نشاط المحفظة"
        )


    if transaction_count < 5:

        warnings.append(
            "العينة صغيرة ولا تسمح بتقييم موثوق"
        )


    if swaps >= 5:

        positive.append(
            f"نشاط تداول واضح: {swaps} عمليات Swap"
        )


    if swap_ratio >= 0.50:

        positive.append(
            "نسبة مرتفعة نسبيًا من المعاملات مرتبطة بالتداول"
        )


    if failed > 0:

        warnings.append(
            f"تم رصد {failed} معاملات فاشلة"
        )


    confidence = 0


    if transaction_count >= 5:

        confidence += 30


    if transaction_count >= 15:

        confidence += 30


    if transaction_count >= 20:

        confidence += 20


    if swaps >= 5:

        confidence += 20


    confidence = min(
        confidence,
        100
    )


    return {
        "activity_score": activity_score,
        "confidence": confidence,
        "transaction_count": transaction_count,
        "swap_count": swaps,
        "transfer_count": transfers,
        "failed_count": failed,
        "swap_ratio": round(
            swap_ratio,
            3
        ),
        "warnings": warnings,
        "positive": positive,
    }


async def analyze_wallet(
    wallet_address: str,
    transaction_limit: int = 20,
) -> Dict[str, Any]:
    """
    جلب وتحليل نشاط محفظة واحدة.
    """

    transactions = (
        await get_wallet_transactions(
            wallet_address,
            transaction_limit
        )
    )


    analysis = analyze_wallet_activity(
        transactions
    )


    return {
        "wallet": wallet_address,
        "analysis": analysis,
        "transactions": transactions,
}
