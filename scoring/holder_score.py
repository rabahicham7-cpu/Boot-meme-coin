def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def calculate_holder_score(security):
    """
    حساب Holder Score من 100.

    يعتمد على بيانات الحاملين المتاحة من GoPlus:
    - تركيز أكبر حامل
    - تركيز أكبر 10 حامليْن
    - المحافظ المقفلة
    - العناوين المصنفة كمشبوهة/ضارة
    - جودة توزيع الحيازة

    ملاحظة:
    البيانات غير المتوفرة لا تعتبر دليلًا على الأمان.
    """

    if not isinstance(security, dict):
        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "top1": 0,
            "top10": 0,
            "holder_count": 0,
            "locked_count": 0,
            "malicious_count": 0,
            "warnings": [
                "بيانات الحاملين غير متوفرة"
            ],
            "positive": [],
        }

    holders = security.get("holders")

    if not isinstance(holders, list) or not holders:

        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "top1": 0,
            "top10": 0,
            "holder_count": 0,
            "locked_count": 0,
            "malicious_count": 0,
            "warnings": [
                "لم يتم الحصول على قائمة الحاملين"
            ],
            "positive": [],
        }

    score = 100

    warnings = []
    positive = []

    percentages = []

    locked_count = 0
    malicious_count = 0

    # ==========================================
    # قراءة بيانات الحاملين
    # ==========================================

    for holder in holders[:10]:

        if not isinstance(holder, dict):
            continue

        percent = safe_float(
            holder.get("percent")
        )

        # بعض APIs قد ترجع:
        # 0.10 = 10%
        if percent <= 1:
            percent *= 100

        percent = max(
            0,
            min(percent, 100)
        )

        percentages.append(percent)

        # ======================================
        # Locked
        # ======================================

        is_locked = holder.get(
            "is_locked"
        )

        if is_locked in (
            True,
            1,
            "1",
            "true",
            "True"
        ):
            locked_count += 1

        # ======================================
        # Malicious / suspicious
        # ======================================

        malicious = (
            holder.get("malicious_address")
            or holder.get("is_malicious")
            or holder.get("malicious")
        )

        if malicious in (
            True,
            1,
            "1",
            "true",
            "True"
        ):
            malicious_count += 1

    if not percentages:

        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "top1": 0,
            "top10": 0,
            "holder_count": 0,
            "locked_count": locked_count,
            "malicious_count": malicious_count,
            "warnings": [
                "بيانات نسب الحيازة غير صالحة"
            ],
            "positive": [],
        }

    top1 = percentages[0]
    top10 = sum(percentages)

    # ==========================================
    # 1. أكبر حامل
    # ==========================================

    if top1 >= 50:

        score -= 35

        warnings.append(
            f"تركيز شديد لدى أكبر حامل: {top1:.2f}%"
        )

    elif top1 >= 30:

        score -= 25

        warnings.append(
            f"تركيز مرتفع لدى أكبر حامل: {top1:.2f}%"
        )

    elif top1 >= 20:

        score -= 15

        warnings.append(
            f"تركيز ملحوظ لدى أكبر حامل: {top1:.2f}%"
        )

    elif top1 >= 10:

        score -= 7

        warnings.append(
            f"أكبر حامل يملك {top1:.2f}%"
        )

    else:

        positive.append(
            f"تركيز أكبر حامل منخفض نسبيًا: {top1:.2f}%"
        )

    # ==========================================
    # 2. أكبر 10 حامليْن
    # ==========================================

    if top10 >= 90:

        score -= 30

        warnings.append(
            f"أكبر 10 حامليْن يملكون {top10:.2f}%"
        )

    elif top10 >= 80:

        score -= 25

        warnings.append(
            f"تركيز شديد لأكبر 10 حامليْن: {top10:.2f}%"
        )

    elif top10 >= 60:

        score -= 18

        warnings.append(
            f"تركيز مرتفع لأكبر 10 حامليْن: {top10:.2f}%"
        )

    elif top10 >= 50:

        score -= 10

        warnings.append(
            f"تركيز ملحوظ لأكبر 10 حامليْن: {top10:.2f}%"
        )

    else:

        positive.append(
            f"توزيع أكبر 10 حامليْن مقبول: {top10:.2f}%"
        )

    # ==========================================
    # 3. فجوة التركيز
    # ==========================================

    if len(percentages) >= 2:

        second = percentages[1]

        concentration_gap = top1 - second

        if concentration_gap >= 30:

            score -= 10

            warnings.append(
                "هناك فجوة كبيرة بين أكبر حامل "
                "وثاني أكبر حامل"
            )

        elif concentration_gap <= 10:

            positive.append(
                "توزيع نسبي أفضل بين كبار الحاملين"
            )

    # ==========================================
    # 4. المحافظ المقفلة
    # ==========================================

    if locked_count > 0:

        positive.append(
            f"تم رصد {locked_count} من كبار الحاملين "
            "بحالة قفل"
        )

    # ==========================================
    # 5. عناوين ضارة
    # ==========================================

    if malicious_count > 0:

        score -= min(
            malicious_count * 15,
            40
        )

        warnings.append(
            f"تم رصد {malicious_count} عنوان "
            "مصنف كمشبوه أو ضار"
        )

    # ==========================================
    # 6. عدد الحاملين المتاحين للتحليل
    # ==========================================

    holder_count = len(
        percentages
    )

    if holder_count < 5:

        score -= 10

        warnings.append(
            "بيانات Top Holders المتاحة للتحليل محدودة"
        )

    elif holder_count >= 10:

        positive.append(
            "بيانات Top 10 متاحة للتحليل"
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
        "top1": round(top1, 2),
        "top10": round(top10, 2),
        "holder_count": holder_count,
        "locked_count": locked_count,
        "malicious_count": malicious_count,
        "warnings": warnings,
        "positive": positive,
        }
