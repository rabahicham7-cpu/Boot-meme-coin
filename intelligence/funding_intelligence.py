from __future__ import annotations

from collections import defaultdict
from typing import Any


RISK_LABELS = {
    "bundler",
    "sniper",
    "insider",
}


POSITIVE_LABELS = {
    "proTrader",
    "smartTrader",
}


def _normalize_labels(value: Any) -> set[str]:
    """
    تحويل Labels القادمة من Mobula إلى set موحد.
    """

    if not value:
        return set()

    if isinstance(value, str):
        return {value}

    if isinstance(value, (list, tuple, set)):
        return {
            str(label)
            for label in value
            if label
        }

    return set()


def _get_funder(trader: dict[str, Any]) -> str | None:
    """
    استخراج عنوان الممول من fundingInfo.
    """

    funding = trader.get("fundingInfo")

    if not isinstance(funding, dict):
        return None

    funder = funding.get("from")

    if not funder:
        return None

    return str(funder)


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0

        return float(value)

    except (TypeError, ValueError):
        return 0.0


def analyze_funding_relationships(
    traders: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    تحليل علاقات التمويل بين المتداولين.

    لا يعتبر التمويل المشترك دليل تلاعب بحد ذاته.
    يتم دمج:
    - عدد المحافظ لكل ممول
    - Labels
    - نسبة Labels الخطرة
    - حجم المجموعة
    - جودة البيانات
    """

    if not traders:
        return {
            "status": "insufficient_data",
            "confidence": 0,
            "total_traders": 0,
            "unique_funders": 0,
            "shared_funders": 0,
            "largest_cluster": 0,
            "risk_score": 0,
            "warnings": [
                "لا توجد بيانات متداولين كافية لتحليل التمويل."
            ],
        }

    funder_groups: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )

    missing_funding = 0

    for trader in traders:

        funder = _get_funder(trader)

        if not funder:
            missing_funding += 1
            continue

        funder_groups[funder].append(trader)

    shared_groups = {
        funder: members
        for funder, members in funder_groups.items()
        if len(members) >= 2
    }

    largest_cluster = 0
    largest_funder = None

    if shared_groups:

        largest_funder, largest_members = max(
            shared_groups.items(),
            key=lambda item: len(item[1]),
        )

        largest_cluster = len(largest_members)

    suspicious_clusters = []

    for funder, members in shared_groups.items():

        labels = set()

        risk_label_count = 0
        positive_label_count = 0

        for trader in members:

            trader_labels = _normalize_labels(
                trader.get("labels")
            )

            labels.update(trader_labels)

            if trader_labels & RISK_LABELS:
                risk_label_count += 1

            if trader_labels & POSITIVE_LABELS:
                positive_label_count += 1

        cluster_size = len(members)

        risk_ratio = (
            risk_label_count / cluster_size
            if cluster_size
            else 0
        )

        positive_ratio = (
            positive_label_count / cluster_size
            if cluster_size
            else 0
        )

        # لا نعتبر المجموعة مشبوهة من الحجم فقط.
        suspicion = 0

        if cluster_size >= 3:
            suspicion += 20

        if cluster_size >= 5:
            suspicion += 15

        if risk_ratio >= 0.50:
            suspicion += 30

        elif risk_ratio >= 0.30:
            suspicion += 15

        if positive_ratio >= 0.50:
            suspicion -= 10

        suspicion = max(0, min(100, suspicion))

        if suspicion >= 40:

            suspicious_clusters.append(
                {
                    "funder": funder,
                    "wallet_count": cluster_size,
                    "risk_label_wallets": risk_label_count,
                    "positive_label_wallets": positive_label_count,
                    "risk_ratio": round(
                        risk_ratio,
                        3,
                    ),
                    "positive_ratio": round(
                        positive_ratio,
                        3,
                    ),
                    "labels": sorted(labels),
                    "suspicion_score": suspicion,
                }
            )

    suspicious_clusters.sort(
        key=lambda x: x["suspicion_score"],
        reverse=True,
    )

    # درجة المخاطر العامة.
    risk_score = 0

    if largest_cluster >= 3:
        risk_score += 15

    if largest_cluster >= 5:
        risk_score += 15

    if largest_cluster >= 10:
        risk_score += 15

    if suspicious_clusters:
        risk_score += min(
            40,
            len(suspicious_clusters) * 10,
        )

    risk_score = max(
        0,
        min(100, risk_score),
    )

    # جودة البيانات.
    total_with_funding = sum(
        len(members)
        for members in funder_groups.values()
    )

    coverage = (
        total_with_funding / len(traders)
        if traders
        else 0
    )

    confidence = round(
        coverage * 100
    )

    warnings = []

    if coverage < 0.70:
        warnings.append(
            "تغطية بيانات التمويل منخفضة."
        )

    if not shared_groups:
        warnings.append(
            "لم يتم العثور على ممولين مشتركين."
        )

    if shared_groups and not suspicious_clusters:
        warnings.append(
            "تم العثور على تمويل مشترك، "
            "لكن لا توجد أدلة كافية لاعتباره مشبوهًا."
        )

    return {
        "status": "ok",
        "confidence": confidence,
        "total_traders": len(traders),
        "traders_with_funding": total_with_funding,
        "unique_funders": len(funder_groups),
        "shared_funders": len(shared_groups),
        "largest_cluster": largest_cluster,
        "largest_funder": largest_funder,
        "suspicious_clusters": suspicious_clusters,
        "risk_score": risk_score,
        "warnings": warnings,
                  }
