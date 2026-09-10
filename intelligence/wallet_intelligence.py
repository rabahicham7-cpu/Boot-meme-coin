import os
from typing import Any, Dict, List, Optional

import aiohttp
from dotenv import load_dotenv


load_dotenv()


HELIUS_API_KEY = os.getenv(
    "HELIUS_API_KEY"
)

HELIUS_RPC_URL = (
    "https://mainnet.helius-rpc.com/"
)


# ============================================================
# Helius RPC
# ============================================================

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


# ============================================================
# Wallet signatures
# ============================================================

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


# ============================================================
# Transaction
# ============================================================

async def get_transaction(
    signature: str,
) -> Optional[Dict[str, Any]]:
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


# ============================================================
# Wallet transactions
# ============================================================

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
            item.get(
                "confirmationStatus"
            )
        )

        transaction["_slot"] = (
            item.get(
                "slot"
            )
        )

        transaction["_block_time"] = (
            item.get(
                "blockTime"
            )
        )

        transactions.append(
            transaction
        )

    return transactions


# ============================================================
# Safe helpers
# ============================================================

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


def _safe_int(
    value: Any,
) -> int:

    try:

        return int(value)

    except (
        TypeError,
        ValueError
    ):

        return 0


# ============================================================
# Token balance extraction
# ============================================================

def _extract_token_balance_amount(
    item: Dict[str, Any],
) -> int:
    """
    استخراج الكمية الخام للتوكن.

    نستخدم amount بدل uiAmount
    لتجنب مشاكل الدقة العشرية.
    """

    if not isinstance(
        item,
        dict
    ):
        return 0

    ui_token_amount = item.get(
        "uiTokenAmount",
        {}
    )

    if not isinstance(
        ui_token_amount,
        dict
    ):
        return 0

    amount = ui_token_amount.get(
        "amount"
    )

    return _safe_int(
        amount
    )


def _extract_token_balance_decimals(
    item: Dict[str, Any],
) -> int:
    """
    استخراج عدد المنازل العشرية للتوكن.
    """

    if not isinstance(
        item,
        dict
    ):
        return 0

    ui_token_amount = item.get(
        "uiTokenAmount",
        {}
    )

    if not isinstance(
        ui_token_amount,
        dict
    ):
        return 0

    return _safe_int(
        ui_token_amount.get(
            "decimals",
            0
        )
    )


def _raw_to_ui_amount(
    amount: int,
    decimals: int,
) -> float:
    """
    تحويل الكمية الخام إلى كمية قابلة للعرض.
    """

    if decimals < 0:
        decimals = 0

    return amount / (
        10 ** decimals
    )


# ============================================================
# Token balance changes - generic
# ============================================================

def _extract_token_balance_changes(
    transaction: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    استخراج تغيّر أرصدة التوكنات في معاملة واحدة.

    كل نتيجة تمثل:
    owner + mint + الرصيد السابق + الرصيد اللاحق + التغير.
    """

    if not isinstance(
        transaction,
        dict
    ):
        return []

    meta = transaction.get(
        "meta"
    )

    if not isinstance(
        meta,
        dict
    ):
        return []

    pre = meta.get(
        "preTokenBalances",
        []
    )

    post = meta.get(
        "postTokenBalances",
        []
    )

    if not isinstance(
        pre,
        list
    ):
        pre = []

    if not isinstance(
        post,
        list
    ):
        post = []

    # --------------------------------------------------------
    # تجميع حسب owner + mint
    # لأن المحفظة قد تملك أكثر من Token Account
    # لنفس التوكن.
    # --------------------------------------------------------

    before: Dict[
        tuple,
        Dict[str, Any]
    ] = {}

    after: Dict[
        tuple,
        Dict[str, Any]
    ] = {}

    for item in pre:

        if not isinstance(
            item,
            dict
        ):
            continue

        owner = item.get(
            "owner"
        )

        mint = item.get(
            "mint"
        )

        if not isinstance(
            owner,
            str
        ):
            continue

        if not isinstance(
            mint,
            str
        ):
            continue

        key = (
            owner,
            mint
        )

        amount = (
            _extract_token_balance_amount(
                item
            )
        )

        decimals = (
            _extract_token_balance_decimals(
                item
            )
        )

        if key not in before:

            before[key] = {
                "amount": 0,
                "decimals": decimals,
            }

        before[key]["amount"] += amount

        before[key]["decimals"] = max(
            before[key]["decimals"],
            decimals
        )

    for item in post:

        if not isinstance(
            item,
            dict
        ):
            continue

        owner = item.get(
            "owner"
        )

        mint = item.get(
            "mint"
        )

        if not isinstance(
            owner,
            str
        ):
            continue

        if not isinstance(
            mint,
            str
        ):
            continue

        key = (
            owner,
            mint
        )

        amount = (
            _extract_token_balance_amount(
                item
            )
        )

        decimals = (
            _extract_token_balance_decimals(
                item
            )
        )

        if key not in after:

            after[key] = {
                "amount": 0,
                "decimals": decimals,
            }

        after[key]["amount"] += amount

        after[key]["decimals"] = max(
            after[key]["decimals"],
            decimals
        )

    # --------------------------------------------------------
    # مقارنة قبل / بعد
    # --------------------------------------------------------

    keys = (
        set(before.keys())
        | set(after.keys())
    )

    changes = []

    for owner, mint in keys:

        before_data = before.get(
            (owner, mint),
            {
                "amount": 0,
                "decimals": 0,
            }
        )

        after_data = after.get(
            (owner, mint),
            {
                "amount": 0,
                "decimals": 0,
            }
        )

        before_amount = _safe_int(
            before_data.get(
                "amount"
            )
        )

        after_amount = _safe_int(
            after_data.get(
                "amount"
            )
        )

        decimals = max(
            _safe_int(
                before_data.get(
                    "decimals"
                )
            ),
            _safe_int(
                after_data.get(
                    "decimals"
                )
            )
        )

        change = (
            after_amount
            - before_amount
        )

        if change == 0:
            continue

        changes.append(
            {
                "owner": owner,
                "mint": mint,

                "before_raw": (
                    before_amount
                ),

                "after_raw": (
                    after_amount
                ),

                "change_raw": change,

                "before_amount": (
                    _raw_to_ui_amount(
                        before_amount,
                        decimals
                    )
                ),

                "after_amount": (
                    _raw_to_ui_amount(
                        after_amount,
                        decimals
                    )
                ),

                "change_amount": (
                    _raw_to_ui_amount(
                        change,
                        decimals
                    )
                ),

                "decimals": decimals,

                "direction": (
                    "in"
                    if change > 0
                    else "out"
                ),
            }
        )

    return changes


# ============================================================
# Wallet token balance changes
# ============================================================

def analyze_wallet_token_balance_changes(
    transactions: List[Dict[str, Any]],
    wallet_address: str,
    mint_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    تحليل تغيّر رصيد توكن معين لمحفظة معينة.

    هذا التحليل يجيب عن:

    - هل زاد رصيد التوكن؟
    - هل انخفض؟
    - كم دخل؟
    - كم خرج؟
    - ما هو صافي التغير؟
    - كم عدد عمليات الدخول والخروج؟
    """

    if not isinstance(
        transactions,
        list
    ):
        transactions = []

    if not wallet_address:

        return {
            "wallet": wallet_address,
            "mint": mint_address,
            "transaction_count": 0,
            "balance_changes": [],
            "total_in": 0.0,
            "total_out": 0.0,
            "net_change": 0.0,
            "in_count": 0,
            "out_count": 0,
            "direction": "unknown",
            "confidence": 0,
            "warnings": [
                "عنوان المحفظة غير موجود"
            ],
        }

    balance_changes = []

    for transaction in transactions:

        changes = (
            _extract_token_balance_changes(
                transaction
            )
        )

        for change in changes:

            if change.get(
                "owner"
            ) != wallet_address:

                continue

            if (
                mint_address
                and change.get(
                    "mint"
                ) != mint_address
            ):

                continue

            signature = transaction.get(
                "_signature"
            )

            block_time = transaction.get(
                "_block_time"
            )

            slot = transaction.get(
                "_slot"
            )

            item = dict(
                change
            )

            item["signature"] = (
                signature
            )

            item["block_time"] = (
                block_time
            )

            item["slot"] = (
                slot
            )

            balance_changes.append(
                item
            )

    total_in = 0.0
    total_out = 0.0

    in_count = 0
    out_count = 0

    for item in balance_changes:

        change_amount = _safe_number(
            item.get(
                "change_amount"
            )
        )

        if change_amount > 0:

            total_in += change_amount
            in_count += 1

        elif change_amount < 0:

            total_out += abs(
                change_amount
            )
            out_count += 1

    net_change = (
        total_in
        - total_out
    )

    if net_change > 0:

        direction = "in"

    elif net_change < 0:

        direction = "out"

    else:

        direction = "neutral"

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = 0

    if len(transactions) >= 5:
        confidence += 20

    if len(transactions) >= 15:
        confidence += 20

    if len(transactions) >= 20:
        confidence += 20

    if len(balance_changes) >= 1:
        confidence += 20

    if len(balance_changes) >= 3:
        confidence += 10

    if len(balance_changes) >= 5:
        confidence += 10

    confidence = min(
        confidence,
        100
    )

    warnings = []

    if not transactions:

        warnings.append(
            "لا توجد معاملات للتحليل"
        )

    elif len(transactions) < 5:

        warnings.append(
            "العينة صغيرة"
        )

    if not balance_changes:

        warnings.append(
            "لم يتم رصد تغير واضح في رصيد التوكن"
        )

    # --------------------------------------------------------
    # نتيجة التحليل
    # --------------------------------------------------------

    if net_change > 0:

        interpretation = (
            "الرصيد الصافي للتوكن ارتفع"
        )

    elif net_change < 0:

        interpretation = (
            "الرصيد الصافي للتوكن انخفض"
        )

    else:

        interpretation = (
            "لا يوجد تغير صافٍ واضح"
        )

    return {
        "wallet": wallet_address,
        "mint": mint_address,

        "transaction_count": (
            len(transactions)
        ),

        "balance_changes": (
            balance_changes
        ),

        "balance_change_count": (
            len(balance_changes)
        ),

        "in_count": in_count,
        "out_count": out_count,

        "total_in": round(
            total_in,
            12
        ),

        "total_out": round(
            total_out,
            12
        ),

        "net_change": round(
            net_change,
            12
        ),

        "direction": direction,

        "interpretation": (
            interpretation
        ),

        "confidence": confidence,

        "warnings": warnings,
    }


# ============================================================
# Generic token changes in transaction
# ============================================================

def _extract_token_changes(
    transaction: Dict[str, Any],
) -> Dict[str, Any]:
    """
    إحصاء عام لتغيرات أرصدة التوكنات
    داخل معاملة واحدة.
    """

    changes = (
        _extract_token_balance_changes(
            transaction
        )
    )

    positive_changes = 0
    negative_changes = 0

    for change in changes:

        direction = change.get(
            "direction"
        )

        if direction == "in":

            positive_changes += 1

        elif direction == "out":

            negative_changes += 1

    return {
        "token_changes": len(
            changes
        ),

        "positive_token_changes": (
            positive_changes
        ),

        "negative_token_changes": (
            negative_changes
        ),
    }


# ============================================================
# SOL change
# ============================================================

def _extract_sol_change(
    transaction: Dict[str, Any],
) -> float:
    """
    حساب التغير الإجمالي التقريبي في أرصدة SOL
    داخل المعاملة.

    ملاحظة:
    هذا ليس تغير SOL لمحفظة محددة.
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

    if not isinstance(
        pre,
        list
    ):
        pre = []

    if not isinstance(
        post,
        list
    ):
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

    return (
        total_change
        / 1_000_000_000
    )


# ============================================================
# Extract candidate wallets
# ============================================================

def extract_wallets_from_transaction(
    transaction: Dict[str, Any]
) -> List[str]:
    """
    استخراج عناوين المحافظ المرتبطة
    بتغييرات أرصدة التوكن.

    هذه المحافظ مرشحة فقط للتحليل اللاحق.

    لا تعتبر Smart Money.
    """

    if not isinstance(
        transaction,
        dict
    ):
        return []

    changes = (
        _extract_token_balance_changes(
            transaction
        )
    )

    wallets = set()

    for change in changes:

        owner = change.get(
            "owner"
        )

        if not isinstance(
            owner,
            str
        ):
            continue

        if len(owner) < 32:
            continue

        wallets.add(
            owner
        )

    return sorted(
        wallets
    )


def extract_wallets_from_transactions(
    transactions: List[Dict[str, Any]]
) -> List[str]:
    """
    استخراج جميع المحافظ الفريدة
    من مجموعة معاملات.
    """

    if not isinstance(
        transactions,
        list
    ):
        return []

    wallets = set()

    for transaction in transactions:

        wallets.update(
            extract_wallets_from_transaction(
                transaction
            )
        )

    return sorted(
        wallets
    )


# ============================================================
# Wallet activity analysis
# ============================================================

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

    if transaction_count >= 5:
        activity_score += 20

    if transaction_count >= 15:
        activity_score += 15

    if transaction_count >= 20:
        activity_score += 10

    if token_activity >= 3:
        activity_score += 15

    if token_activity >= 10:
        activity_score += 10

    if sol_activity >= 5:
        activity_score += 10

    if success_ratio >= 0.90:
        activity_score += 10

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

    if (
        success_ratio >= 0.90
        and transaction_count >= 5
    ):

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

        "transaction_count": (
            transaction_count
        ),

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

        "token_activity": (
            token_activity
        ),

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


# ============================================================
# Full wallet analysis
# ============================================================

async def analyze_wallet(
    wallet_address: str,
    transaction_limit: int = 20,
    mint_address: Optional[str] = None,
) -> Dict[str, Any]:
    """
    جلب وتحليل محفظة واحدة.

    إذا تم تمرير mint_address:
    يتم أيضًا تحليل تغيّر رصيد ذلك التوكن
    للمحفظة.
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

    candidate_wallets = (
        extract_wallets_from_transactions(
            transactions
        )
    )

    token_balance_analysis = (
        analyze_wallet_token_balance_changes(
            transactions,
            wallet_address,
            mint_address
        )
    )

    return {
        "wallet": wallet_address,

        "analysis": analysis,

        "token_balance_analysis": (
            token_balance_analysis
        ),

        "candidate_wallets": (
            candidate_wallets
        ),

        "transactions": transactions,
    }
