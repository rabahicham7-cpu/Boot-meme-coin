import os
from typing import Any, Dict, List

import aiohttp
from dotenv import load_dotenv


load_dotenv()


HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

HELIUS_RPC_URL = (
    "https://mainnet.helius-rpc.com/"
)


async def helius_rpc(
    method: str,
    params: List[Any],
) -> Dict[str, Any]:
    """
    إرسال طلب JSON-RPC إلى Helius.
    """

    if not HELIUS_API_KEY:
        raise RuntimeError(
            "HELIUS_API_KEY غير موجود"
        )

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }

    url = (
        f"{HELIUS_RPC_URL}"
        f"?api-key={HELIUS_API_KEY}"
    )

    timeout = aiohttp.ClientTimeout(
        total=20
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json"
            },
        ) as response:

            data = await response.json(
                content_type=None
            )

            if response.status != 200:

                raise RuntimeError(
                    "Helius RPC HTTP error: "
                    f"{response.status} - {data}"
                )

            if "error" in data:

                raise RuntimeError(
                    "Helius RPC error: "
                    f"{data['error']}"
                )

            return data


async def get_wallet_signatures(
    wallet_address: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    جلب آخر توقيعات معاملات المحفظة.
    """

    if not wallet_address:
        return []

    limit = max(
        1,
        min(int(limit), 100)
    )

    data = await helius_rpc(
        "getSignaturesForAddress",
        [
            wallet_address,
            {
                "limit": limit
            }
        ]
    )

    result = data.get(
        "result",
        []
    )

    if not isinstance(
        result,
        list
    ):
        return []

    return result


async def get_transaction(
    signature: str,
) -> Dict[str, Any] | None:
    """
    جلب تفاصيل معاملة واحدة.
    """

    if not signature:
        return None

    data = await helius_rpc(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 1,
            }
        ]
    )

    result = data.get(
        "result"
    )

    if not isinstance(
        result,
        dict
    ):
        return None

    return result


async def get_wallet_transactions(
    wallet_address: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    جلب آخر معاملات المحفظة عبر Helius RPC.

    لا تستخدم Enhanced API.
    """

    signatures = (
        await get_wallet_signatures(
            wallet_address,
            limit
        )
    )

    if not signatures:
        return []

    transactions = []

    for item in signatures:

        if not isinstance(
            item,
            dict
        ):
            continue

        signature = item.get(
            "signature"
        )

        if not signature:
            continue

        try:

            transaction = (
                await get_transaction(
                    signature
                )
            )

        except Exception:

            continue

        if transaction is None:
            continue

        transaction["_signature"] = (
            signature
        )

        transaction["_status"] = (
            item.get("confirmationStatus")
        )

        transaction["_slot"] = (
            item.get("slot")
        )

        transaction["_block_time"] = (
            item.get("blockTime")
        )

        transactions.append(
            transaction
        )

    return transactions


def _safe_number(
    value: Any,
) -> float:

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):

        return 0.0


def _extract_token_changes(
    transaction: Dict[str, Any],
) -> Dict[str, Any]:
    """
    استخراج التغيرات الأساسية في أرصدة التوكنات.
    """

    meta = transaction.get(
        "meta"
    )

    if not isinstance(
        meta,
        dict
    ):
        return {
            "token_changes": 0,
            "positive_token_changes": 0,
            "negative_token_changes": 0,
        }

    pre = meta.get(
        "preTokenBalances",
        []
    )

    post = meta.get(
        "postTokenBalances",
        []
    )

    if not isinstance(pre, list):
        pre = []

    if not isinstance(post, list):
        post = []

    pre_balances = {}
    post_balances = {}

    for item in pre:

        if not isinstance(
            item,
            dict
        ):
            continue

        account_index = item.get(
            "accountIndex"
        )

        amount = (
            item
            .get("uiTokenAmount", {})
            .get("uiAmount")
        )

        pre_balances[
            account_index
        ] = _safe_number(amount)

    for item in post:

        if not isinstance(
            item,
            dict
        ):
            continue

        account_index = item.get(
            "accountIndex"
        )

        amount = (
            item
            .get("uiTokenAmount", {})
            .get("uiAmount")
        )

        post_balances[
            account_index
        ] = _safe_number(amount)

    all_indexes = set(
        pre_balances
    ) | set(
        post_balances
    )

    token_changes = 0
    positive_changes = 0
    negative_changes = 0

    for index in all_indexes:

        before = pre_balances.get(
            index,
            0.0
        )

        after = post_balances.get(
            index,
            0.0
        )

        change = after - before

        if abs(change) < 0.0000001:
            continue

        token_changes += 1

        if change > 0:
            positive_changes += 1

        else:
            negative_changes += 1

    return {
        "token_changes": token_changes,
        "positive_token_changes": positive_changes,
        "negative_token_changes": negative_changes,
    }


def _extract_sol_change(
    transaction: Dict[str, Any],
) -> float:
    """
    حساب التغير التقريبي في رصيد SOL
    للحسابات المذكورة في المعاملة.
    """

    meta = transaction.get(
        "meta"
    )

    if not isinstance(
        meta,
        dict
    ):
        return 0.0

    pre = meta.get(
        "preBalances",
        []
    )

    post = meta.get(
        "postBalances",
        []
    )

    if not isinstance(pre, list):
        pre = []

    if not isinstance(post, list):
        post = []

    length = min(
        len(pre),
        len(post)
    )

    total_change = 0

    for index in range(length):

        before = _safe_number(
            pre[index]
        )

        after = _safe_number(
            post[index]
        )

        total_change += (
            after - before
        )

    return total_change / 1_000_000_000


def analyze_wallet_activity(
    transactions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    تحليل أولي لنشاط المحفظة.

    هذا ليس حكم Smart Money.
    """

    if not isinstance(
        transactions,
        list
    ):
        transactions = []

    transaction_count = len(
        transactions
    )

    successful = 0
    failed = 0

    token_activity = 0
    positive_token_changes = 0
    negative_token_changes = 0

    sol_activity = 0

    slots = []

    warnings = []
    positive = []

    for tx in transactions:

        if not isinstance(
            tx,
            dict
        ):
            continue

        meta = tx.get(
            "meta"
        )

        if isinstance(
            meta,
            dict
        ):

            if meta.get(
                "err"
            ) is None:

                successful += 1

            else:

                failed += 1

        slot = tx.get(
            "_slot"
        )

        if isinstance(
            slot,
            int
        ):
            slots.append(slot)

        token_changes = (
            _extract_token_changes(
                tx
            )
        )

        token_activity += (
            token_changes[
                "token_changes"
            ]
        )

        positive_token_changes += (
            token_changes[
                "positive_token_changes"
            ]
        )

        negative_token_changes += (
            token_changes[
                "negative_token_changes"
            ]
        )

        sol_change = abs(
            _extract_sol_change(
                tx
            )
        )

        if sol_change > 0:
            sol_activity += 1

    success_ratio = 0.0

    if transaction_count > 0:

        success_ratio = (
            successful
            / transaction_count
        )

    failed_ratio = 0.0

    if transaction_count > 0:

        failed_ratio = (
            failed
            / transaction_count
        )

    activity_score = 0

    # حجم العينة
    if transaction_count >= 5:
        activity_score += 20

    if transaction_count >= 15:
        activity_score += 15

    if transaction_count >= 20:
        activity_score += 10

    # نشاط التوكنات
    if token_activity >= 3:
        activity_score += 15

    if token_activity >= 10:
        activity_score += 10

    # نشاط SOL
    if sol_activity >= 5:
        activity_score += 10

    # نجاح المعاملات
    if success_ratio >= 0.90:
        activity_score += 10

    # المعاملات الفاشلة
    if failed_ratio > 0.30:
        activity_score -= 20

    elif failed_ratio > 0.10:
        activity_score -= 10

    activity_score = max(
        0,
        min(
            100,
            activity_score
        )
    )

    if transaction_count == 0:

        warnings.append(
            "لا توجد معاملات كافية لتحليل المحفظة"
        )

    if transaction_count < 5:

        warnings.append(
            "العينة صغيرة ولا تسمح بتقييم موثوق"
        )

    if failed > 0:

        warnings.append(
            f"تم رصد {failed} معاملات فاشلة"
        )

    if token_activity > 0:

        positive.append(
            f"نشاط توكنات مرصود: {token_activity} تغييرات"
        )

    if positive_token_changes > 0:

        positive.append(
            f"تدفقات توكنات داخلة: {positive_token_changes}"
        )

    if negative_token_changes > 0:

        positive.append(
            f"تدفقات توكنات خارجة: {negative_token_changes}"
        )

    if success_ratio >= 0.90 and transaction_count >= 5:

        positive.append(
            "نسبة نجاح مرتفعة للمعاملات"
        )

    confidence = 0

    if transaction_count >= 5:
        confidence += 25

    if transaction_count >= 15:
        confidence += 25

    if transaction_count >= 20:
        confidence += 20

    if token_activity > 0:
        confidence += 15

    if successful > 0:
        confidence += 15

    confidence = min(
        confidence,
        100
    )

    return {
        "activity_score": activity_score,
        "confidence": confidence,
        "transaction_count": transaction_count,
        "successful_count": successful,
        "failed_count": failed,
        "success_ratio": round(
            success_ratio,
            3
        ),
        "failed_ratio": round(
            failed_ratio,
            3
        ),
        "token_activity": token_activity,
        "positive_token_changes": (
            positive_token_changes
        ),
        "negative_token_changes": (
            negative_token_changes
        ),
        "sol_activity": sol_activity,
        "warnings": warnings,
        "positive": positive,
    }


async def analyze_wallet(
    wallet_address: str,
    transaction_limit: int = 20,
) -> Dict[str, Any]:
    """
    جلب وتحليل محفظة واحدة.
    """

    transactions = (
        await get_wallet_transactions(
            wallet_address,
            transaction_limit
        )
    )

    analysis = (
        analyze_wallet_activity(
            transactions
        )
    )

    return {
        "wallet": wallet_address,
        "analysis": analysis,
        "transactions": transactions,
                }
