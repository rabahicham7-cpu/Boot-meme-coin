def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def is_enabled(value):
    return value in ("1", 1, True)


def get_status_value(data, key):
    value = data.get(key, {})

    if isinstance(value, dict):
        return value.get("status")

    return value


def calculate_security_score(security):
    """
    حساب درجة أمان أولية من 100.
    البيانات المفقودة لا تعتبر دليلًا على الأمان.
    """

    if not isinstance(security, dict):
        return {
            "score": 0,
            "grade": "بيانات غير كافية",
            "critical": [],
            "warnings": [],
            "positive": [],
        }

    score = 100

    critical = []
    warnings = []
    positive = []

    # Mint Authority
    mintable = get_status_value(security, "mintable")

    if is_enabled(mintable):
        score -= 25
        critical.append(
            "صلاحية إنشاء Tokens جديدة ما زالت مفعلة"
        )
    else:
        positive.append(
            "صلاحية Mint غير مفعلة"
        )

    # Freeze Authority
    freezable = get_status_value(security, "freezable")

    if is_enabled(freezable):
        score -= 20
        critical.append(
            "صلاحية تجميد الحسابات ما زالت مفعلة"
        )
    else:
        positive.append(
            "صلاحية Freeze غير مفعلة"
        )

    # Balance Mutable Authority
    balance_mutable = get_status_value(
        security,
        "balance_mutable_authority"
    )

    if is_enabled(balance_mutable):
        score -= 25
        critical.append(
            "صلاحية تعديل أرصدة المستخدمين موجودة"
        )
    else:
        positive.append(
            "لا توجد صلاحية ظاهرة لتعديل الأرصدة"
        )

    # Closable
    closable = get_status_value(
        security,
        "closable"
    )

    if is_enabled(closable):
        score -= 10
        warnings.append(
            "إمكانية إغلاق برنامج التوكن موجودة"
        )
    else:
        positive.append(
            "إمكانية إغلاق البرنامج غير مفعلة"
        )

    # Metadata
    metadata_mutable = get_status_value(
        security,
        "metadata_mutable"
    )

    if is_enabled(metadata_mutable):
        score -= 5
        warnings.append(
            "بيانات Metadata قابلة للتعديل"
        )
    else:
        positive.append(
            "Metadata غير قابلة للتعديل"
        )

    # Non Transferable
    if is_enabled(
        security.get("non_transferable")
    ):
        score -= 30
        critical.append(
            "التوكن غير قابل للتحويل"
        )

    # Transfer Hook
    transfer_hook = security.get(
        "transfer_hook"
    )

    if isinstance(transfer_hook, dict):

        if is_enabled(
            transfer_hook.get(
                "malicious_address"
            )
        ):
            score -= 30
            critical.append(
                "Transfer Hook مرتبط بعنوان مصنف ضار"
            )

    # Transfer Fee
    transfer_fee = security.get(
        "transfer_fee"
    )

    if isinstance(transfer_fee, dict):

        current_fee = transfer_fee.get(
            "current_fee_rate"
        )

        try:

            if current_fee is not None:

                fee = float(current_fee)

                if fee > 10000:
                    score -= 20
                    warnings.append(
                        "رسوم التحويل مرتفعة جدًا"
                    )

                elif fee > 1000:
                    score -= 10
                    warnings.append(
                        "رسوم التحويل مرتفعة"
                    )

        except (TypeError, ValueError):
            pass

    # Holder Concentration
    holders = security.get(
        "holders",
        []
    )

    top1 = 0.0
    top10 = 0.0

    if isinstance(holders, list):

        percentages = []

        for holder in holders[:10]:

            if not isinstance(
                holder,
                dict
            ):
                continue

            try:

                percent = float(
                    holder.get(
                        "percent",
                        0
                    )
                )

            except (TypeError, ValueError):

                percent = 0

            if percent <= 1:
                percent *= 100

            percentages.append(
                percent
            )

        if percentages:

            top1 = percentages[0]
            top10 = sum(percentages)

    if top1 >= 50:

        score -= 30

        critical.append(
            f"أكبر حامل يملك {top1:.2f}%"
        )

    elif top1 >= 30:

        score -= 20

        warnings.append(
            f"تركيز مرتفع لدى أكبر حامل: {top1:.2f}%"
        )

    elif top1 >= 20:

        score -= 10

        warnings.append(
            f"تركيز ملحوظ لدى أكبر حامل: {top1:.2f}%"
        )

    else:

        positive.append(
            f"تركيز أكبر حامل ضمن نطاق منخفض: {top1:.2f}%"
        )

    if top10 >= 80:

        score -= 25

        critical.append(
            f"أكبر 10 حامليْن يملكون {top10:.2f}%"
        )

    elif top10 >= 60:

        score -= 15

        warnings.append(
            f"تركيز مرتفع لأكبر 10 حامليْن: {top10:.2f}%"
        )

    elif top10 >= 50:

        score -= 8

        warnings.append(
            f"تركيز ملحوظ لأكبر 10 حامليْن: {top10:.2f}%"
        )

    else:

        positive.append(
            f"تركيز أكبر 10 حامليْن: {top10:.2f}%"
        )

    # Final Score
    score = clamp(round(score))

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
        "critical": critical,
        "warnings": warnings,
        "positive": positive,
      }
