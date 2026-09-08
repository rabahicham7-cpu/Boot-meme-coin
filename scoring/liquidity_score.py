def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def calculate_liquidity_score(pair):
    """
    حساب Liquidity Score من 100.

    يعتمد على بيانات السوق المتاحة من DEX Screener:
    - السيولة
    - حجم التداول
    - القيمة السوقية / FDV
    - نشاط التداول
    - نسبة الحجم إلى السيولة

    هذه الدرجة لا تعني أن الخروج من الصفقة مضمون.
    """

    if not isinstance(pair, dict):
        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "liquidity_usd": 0,
            "volume_24h": 0,
            "market_cap": 0,
            "fdv": 0,
            "volume_liquidity_ratio": 0,
            "warnings": [],
            "positive": [],
        }

    liquidity_data = pair.get(
        "liquidity",
        {}
    )

    volume_data = pair.get(
        "volume",
        {}
    )

    liquidity_usd = safe_float(
        liquidity_data.get("usd")
        if isinstance(liquidity_data, dict)
        else 0
    )

    volume_24h = safe_float(
        volume_data.get("h24")
        if isinstance(volume_data, dict)
        else 0
    )

    market_cap = safe_float(
        pair.get("marketCap")
    )

    fdv = safe_float(
        pair.get("fdv")
    )

    txns = pair.get(
        "txns",
        {}
    )

    txns_24h = (
        txns.get("h24", {})
        if isinstance(txns, dict)
        else {}
    )

    buys = safe_float(
        txns_24h.get("buys")
        if isinstance(txns_24h, dict)
        else 0
    )

    sells = safe_float(
        txns_24h.get("sells")
        if isinstance(txns_24h, dict)
        else 0
    )

    total_txns = buys + sells

    score = 0

    warnings = []
    positive = []

    # ==========================================
    # 1. حجم السيولة
    # ==========================================

    if liquidity_usd <= 0:

        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "liquidity_usd": liquidity_usd,
            "volume_24h": volume_24h,
            "market_cap": market_cap,
            "fdv": fdv,
            "volume_liquidity_ratio": 0,
            "warnings": [
                "لا توجد بيانات سيولة صالحة"
            ],
            "positive": [],
        }

    if liquidity_usd >= 1_000_000:

        score += 35

        positive.append(
            "سيولة مرتفعة جدًا"
        )

    elif liquidity_usd >= 500_000:

        score += 32

        positive.append(
            "سيولة مرتفعة"
        )

    elif liquidity_usd >= 250_000:

        score += 28

        positive.append(
            "سيولة جيدة"
        )

    elif liquidity_usd >= 100_000:

        score += 23

        positive.append(
            "سيولة مقبولة"
        )

    elif liquidity_usd >= 50_000:

        score += 16

        warnings.append(
            "السيولة محدودة نسبيًا"
        )

    elif liquidity_usd >= 20_000:

        score += 8

        warnings.append(
            "السيولة منخفضة"
        )

    else:

        score += 2

        warnings.append(
            "السيولة منخفضة جدًا"
        )

    # ==========================================
    # 2. حجم التداول مقابل السيولة
    # ==========================================

    volume_liquidity_ratio = (
        volume_24h / liquidity_usd
        if liquidity_usd > 0
        else 0
    )

    if volume_liquidity_ratio >= 0.5:

        score += 25

        positive.append(
            "نشاط تداول قوي مقارنة بالسيولة"
        )

    elif volume_liquidity_ratio >= 0.2:

        score += 21

        positive.append(
            "نشاط تداول جيد مقارنة بالسيولة"
        )

    elif volume_liquidity_ratio >= 0.1:

        score += 16

        positive.append(
            "نشاط تداول مقبول"
        )

    elif volume_liquidity_ratio >= 0.03:

        score += 10

        warnings.append(
            "نشاط التداول منخفض مقارنة بالسيولة"
        )

    else:

        score += 4

        warnings.append(
            "حجم التداول منخفض جدًا مقارنة بالسيولة"
        )

    # ==========================================
    # 3. السيولة مقابل القيمة السوقية
    # ==========================================

    if market_cap > 0:

        liquidity_market_cap_ratio = (
            liquidity_usd / market_cap
        )

        if liquidity_market_cap_ratio >= 0.20:

            score += 20

            positive.append(
                "نسبة السيولة إلى القيمة السوقية قوية"
            )

        elif liquidity_market_cap_ratio >= 0.10:

            score += 16

            positive.append(
                "نسبة السيولة إلى القيمة السوقية جيدة"
            )

        elif liquidity_market_cap_ratio >= 0.05:

            score += 12

        elif liquidity_market_cap_ratio >= 0.02:

            score += 7

            warnings.append(
                "السيولة منخفضة مقارنة بالقيمة السوقية"
            )

        else:

            score += 3

            warnings.append(
                "السيولة منخفضة جدًا مقارنة بالقيمة السوقية"
            )

    else:

        warnings.append(
            "القيمة السوقية غير متوفرة"
        )

    # ==========================================
    # 4. نشاط المعاملات
    # ==========================================

    if total_txns >= 10_000:

        score += 20

        positive.append(
            "نشاط معاملات مرتفع"
        )

    elif total_txns >= 5_000:

        score += 17

        positive.append(
            "نشاط معاملات جيد"
        )

    elif total_txns >= 2_000:

        score += 13

    elif total_txns >= 500:

        score += 9

    elif total_txns >= 100:

        score += 5

        warnings.append(
            "نشاط المعاملات منخفض"
        )

    else:

        score += 2

        warnings.append(
            "نشاط المعاملات منخفض جدًا"
        )

    # ==========================================
    # 5. حماية من بعض الحالات غير الطبيعية
    # ==========================================

    if volume_liquidity_ratio > 10:

        warnings.append(
            "حجم التداول مرتفع جدًا مقارنة بالسيولة؛ "
            "يحتاج إلى فحص جودة الحجم والتلاعب"
        )

    if liquidity_usd < 20_000:

        warnings.append(
            "قد يكون الخروج من مركز كبير صعبًا"
        )

    # ==========================================
    # الدرجة النهائية
    # ==========================================

    score = clamp(
        round(score)
    )

    if score >= 90:

        grade = "🟢 ممتاز"

    elif score >= 75:

        grade = "🟢 جيد"

    elif score >= 60:

        grade = "🟡 متوسط"

    elif score >= 40:

        grade = "🟠 ضعيف"

    else:

        grade = "🔴 خطير"

    return {
        "score": score,
        "grade": grade,
        "liquidity_usd": round(
            liquidity_usd,
            2
        ),
        "volume_24h": round(
            volume_24h,
            2
        ),
        "market_cap": round(
            market_cap,
            2
        ),
        "fdv": round(
            fdv,
            2
        ),
        "volume_liquidity_ratio": round(
            volume_liquidity_ratio,
            3
        ),
        "warnings": warnings,
        "positive": positive,
      }
