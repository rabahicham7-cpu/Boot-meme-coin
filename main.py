import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from data.dexscreener import get_token_data
from security.goplus import get_token_security

from scoring.security_score import calculate_security_score
from scoring.liquidity_score import calculate_liquidity_score
from scoring.holder_score import calculate_holder_score

from analysis_engine import analyze_intelligence_layers


load_dotenv()


TOKEN = os.getenv("DISCORD_BOT_TOKEN")


if not TOKEN:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN غير موجود"
    )


# =========================================================
# Helpers
# =========================================================

def format_money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "غير متوفر"


def format_number(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "غير متوفر"


def format_percentage(value):
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "غير متوفر"


def get_security_result(data, mint):
    """
    استخراج بيانات التوكن من استجابة GoPlus.

    يدعم أكثر من شكل محتمل للاستجابة.
    """

    if not isinstance(data, dict):
        return None

    result = data.get("result")

    if not result:
        return None

    if isinstance(result, dict):

        token_data = result.get(mint)

        if isinstance(token_data, dict):
            return token_data

        for key, value in result.items():

            if str(key).lower() == mint.lower():

                if isinstance(value, dict):
                    return value

        token_fields = {
            "mintable",
            "freezable",
            "holders",
            "metadata_mutable",
            "balance_mutable_authority",
            "transfer_fee",
            "transfer_hook",
        }

        if any(
            field in result
            for field in token_fields
        ):
            return result

        if len(result) == 1:

            first_value = next(
                iter(result.values())
            )

            if isinstance(first_value, dict):
                return first_value

    if isinstance(result, list):

        for item in result:

            if not isinstance(item, dict):
                continue

            address = (
                item.get("contract_address")
                or item.get("address")
                or item.get("mint")
            )

            if address:

                if str(address).lower() == mint.lower():
                    return item

        if len(result) == 1:

            if isinstance(result[0], dict):
                return result[0]

    return None


async def send_long_message(
    interaction: discord.Interaction,
    message: str,
):
    """
    Discord يسمح بحد أقصى 2000 حرف للرسالة.
    نقسم الرسالة عند الحاجة.
    """

    max_length = 1900

    if len(message) <= max_length:
        await interaction.followup.send(message)
        return

    chunks = []

    current = ""

    for line in message.split("\n"):

        if len(current) + len(line) + 1 > max_length:

            if current:
                chunks.append(current)

            current = line

        else:

            if current:
                current += "\n"

            current += line

    if current:
        chunks.append(current)

    for chunk in chunks:
        await interaction.followup.send(chunk)


def build_intelligence_message(
    intelligence,
):
    """
    تحويل نتائج طبقات Intelligence إلى رسالة عربية.
    """

    message = ""

    if not isinstance(intelligence, dict):
        return message

    traders = intelligence.get("traders") or {}
    smart_money = intelligence.get("smart_money") or {}
    funding = intelligence.get("funding") or {}
    composite = intelligence.get("composite") or {}

    # =====================================================
    # Trader Intelligence
    # =====================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🧠 **Trader Intelligence**\n\n"
    )

    trader_count = intelligence.get(
        "trader_count",
        0,
    )

    profitable = traders.get(
        "profitable_traders",
        0,
    )

    losing = traders.get(
        "losing_traders",
        0,
    )

    smart_traders = traders.get(
        "smart_traders",
        0,
    )

    risk_traders = traders.get(
        "risk_traders",
        0,
    )

    average_score = traders.get(
        "average_score",
        0,
    )

    confidence = traders.get(
        "confidence",
        0,
    )

    message += (
        f"👥 **المتداولون المحللون:** `{trader_count}`\n"
        f"🟢 **المتداولون الرابحون تاريخيًا:** `{profitable}`\n"
        f"🔴 **المتداولون الخاسرون تاريخيًا:** `{losing}`\n"
        f"🧠 **Smart Traders:** `{smart_traders}`\n"
        f"⚠️ **Risk Traders:** `{risk_traders}`\n"
        f"📊 **متوسط درجة المتداولين:** `{average_score:.2f}/100`\n"
        f"🎯 **ثقة البيانات:** `{confidence:.0f}%`\n\n"
    )

    message += (
        "⚠️ نسبة الرابحين تاريخيًا لا تعني توقعًا "
        "للربح المستقبلي.\n\n"
    )

    # =====================================================
    # Smart Money
    # =====================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "💰 **Smart Money Intelligence**\n\n"
    )

    smart_count = smart_money.get(
        "smart_traders",
        0,
    )

    risk_smart_count = smart_money.get(
        "risk_smart_traders",
        0,
    )

    smart_buy_volume = smart_money.get(
        "smart_money_buy_volume_usd",
        0,
    )

    smart_sell_volume = smart_money.get(
        "smart_money_sell_volume_usd",
        0,
    )

    smart_buy_ratio = smart_money.get(
        "smart_money_buy_ratio",
        0,
    )

    smart_sell_ratio = smart_money.get(
        "smart_money_sell_ratio",
        0,
    )

    smart_score = smart_money.get(
        "smart_money_score",
        0,
    )

    flow = smart_money.get(
        "flow",
        "balanced",
    )

    flow_names = {
        "accumulation": "تجميع",
        "distribution": "تصريف",
        "balanced": "متوازن",
    }

    flow_ar = flow_names.get(
        flow,
        flow,
    )

    message += (
        f"🧠 **Smart Traders:** `{smart_count}`\n"
        f"⚠️ **Smart Traders عالية المخاطر:** "
        f"`{risk_smart_count}`\n"
        f"🟢 **حجم شراء Smart Money:** "
        f"`{format_money(smart_buy_volume)}`\n"
        f"🔴 **حجم بيع Smart Money:** "
        f"`{format_money(smart_sell_volume)}`\n"
        f"📈 **نسبة الشراء:** "
        f"`{format_percentage(smart_buy_ratio)}`\n"
        f"📉 **نسبة البيع:** "
        f"`{format_percentage(smart_sell_ratio)}`\n"
        f"🎯 **Smart Money Score:** "
        f"`{smart_score}/100`\n"
        f"🌊 **التدفق:** `{flow_ar}`\n\n"
    )

    # =====================================================
    # Funding Intelligence
    # =====================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🔗 **Funding Intelligence**\n\n"
    )

    total_funders = funding.get(
        "unique_funders",
        0,
    )

    shared_funders = funding.get(
        "shared_funders",
        0,
    )

    largest_cluster = funding.get(
        "largest_cluster",
        0,
    )

    risk_score = funding.get(
        "risk_score",
        0,
    )

    suspicious_clusters = funding.get(
        "suspicious_clusters",
        [],
    )

    if isinstance(suspicious_clusters, list):
        suspicious_count = len(
            suspicious_clusters
        )
    else:
        try:
            suspicious_count = int(
                suspicious_clusters
            )
        except (TypeError, ValueError):
            suspicious_count = 0

    funding_confidence = funding.get(
        "confidence",
        0,
    )

    message += (
        f"💳 **مصادر تمويل فريدة:** `{total_funders}`\n"
        f"🔄 **مصادر مشتركة:** `{shared_funders}`\n"
        f"👥 **أكبر مجموعة تمويل:** `{largest_cluster}`\n"
        f"🚨 **مجموعات تحتاج مراجعة:** "
        f"`{suspicious_count}`\n"
        f"⚠️ **Funding Risk Score:** "
        f"`{risk_score}/100`\n"
        f"🎯 **ثقة التحليل:** "
        f"`{funding_confidence:.0f}%`\n\n"
    )

    message += (
        "⚠️ تشابه مصادر التمويل ليس دليلًا بحد ذاته "
        "على التلاعب.\n\n"
    )

    # =====================================================
    # Composite Score
    # =====================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🎯 **Composite Intelligence Score**\n\n"
    )

    opportunity = composite.get(
        "opportunity_score",
        0,
    )

    composite_risk = composite.get(
        "risk_score",
        0,
    )

    composite_confidence = composite.get(
        "confidence",
        0,
    )

    grade = composite.get(
        "grade",
        "غير متوفر",
    )

    decision = composite.get(
        "decision",
        "غير متوفر",
    )

    decision_ar = {
        "WATCH": "مراقبة",
        "NEUTRAL": "محايد",
        "AVOID": "تجنب",
    }.get(
        str(decision).upper(),
        decision,
    )

    message += (
        f"📈 **Opportunity Score:** "
        f"`{opportunity:.2f}/100`\n"
        f"⚠️ **Risk Score:** "
        f"`{composite_risk:.2f}/100`\n"
        f"🎯 **Confidence:** "
        f"`{composite_confidence:.2f}%`\n"
        f"🏆 **Grade:** `{grade}`\n"
        f"🧭 **القرار التحليلي:** `{decision_ar}`\n\n"
    )

    components = composite.get(
        "components",
        {},
    )

    if isinstance(components, dict):

        message += (
            "📊 **مكونات الدرجة:**\n"
        )

        component_names = {
            "security": "الأمان",
            "liquidity": "السيولة",
            "holders": "الحاملون",
            "traders": "المتداولون",
            "smart_money": "Smart Money",
            "funding_risk": "مخاطر التمويل",
        }

        for key, label in component_names.items():

            value = components.get(
                key
            )

            if value is not None:

                try:
                    value_text = (
                        f"{float(value):.2f}"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    value_text = str(value)

                message += (
                    f"• **{label}:** "
                    f"`{value_text}/100`\n"
                )

        message += "\n"

    # =====================================================
    # Warnings
    # =====================================================

    warnings = intelligence.get(
        "warnings",
        [],
    )

    if warnings:

        message += (
            "⚠️ **تحذيرات Intelligence:**\n"
        )

        for warning in warnings[:5]:

            message += (
                f"• {warning}\n"
            )

        message += "\n"

    return message


# =========================================================
# Discord Bot
# =========================================================

class MemeIntelligenceBot(
    discord.Client
):

    def __init__(self):

        intents = discord.Intents.default()

        intents.message_content = True

        super().__init__(
            intents=intents
        )

        self.tree = app_commands.CommandTree(
            self
        )

    async def setup_hook(self):

        await self.tree.sync()

    async def on_ready(self):

        print(
            f"تم تشغيل البوت: {self.user}"
        )


bot = MemeIntelligenceBot()


# =========================================================
# /ping
# =========================================================

@bot.tree.command(
    name="ping",
    description="اختبار اتصال البوت",
)
async def ping(
    interaction: discord.Interaction,
):

    await interaction.response.send_message(
        "🟢 البوت يعمل بشكل صحيح."
    )


# =========================================================
# /token
# =========================================================

@bot.tree.command(
    name="token",
    description="تحليل شامل لعملة Solana",
)
@app_commands.describe(
    mint="عنوان Mint الخاص بالعملة"
)
async def token(
    interaction: discord.Interaction,
    mint: str,
):

    await interaction.response.defer()

    try:

        # =================================================
        # 1. Market Data
        # =================================================

        pair = await get_token_data(
            mint
        )

        if not pair:

            await interaction.followup.send(
                "❌ لم يتم العثور على بيانات سوق "
                "لهذه العملة على Solana."
            )

            return

        base_token = pair.get(
            "baseToken",
            {},
        )

        name = base_token.get(
            "name",
            "غير معروف",
        )

        symbol = base_token.get(
            "symbol",
            "غير معروف",
        )

        price_usd = pair.get(
            "priceUsd",
            "غير متوفر",
        )

        liquidity = pair.get(
            "liquidity",
            {},
        )

        volume = pair.get(
            "volume",
            {},
        )

        price_change = pair.get(
            "priceChange",
            {},
        )

        txns = pair.get(
            "txns",
            {},
        )

        liquidity_usd = (
            liquidity.get(
                "usd",
                0,
            )
            if isinstance(
                liquidity,
                dict,
            )
            else 0
        )

        volume_24h = (
            volume.get(
                "h24",
                0,
            )
            if isinstance(
                volume,
                dict,
            )
            else 0
        )

        change_24h = (
            price_change.get(
                "h24",
                0,
            )
            if isinstance(
                price_change,
                dict,
            )
            else 0
        )

        txns_24h = (
            txns.get(
                "h24",
                {},
            )
            if isinstance(
                txns,
                dict,
            )
            else {}
        )

        buys = (
            txns_24h.get(
                "buys",
                0,
            )
            if isinstance(
                txns_24h,
                dict,
            )
            else 0
        )

        sells = (
            txns_24h.get(
                "sells",
                0,
            )
            if isinstance(
                txns_24h,
                dict,
            )
            else 0
        )

        # =================================================
        # 2. Security
        # =================================================

        security_response = (
            await get_token_security(
                mint
            )
        )

        security = get_security_result(
            security_response,
            mint,
        )

        # =================================================
        # 3. Security Score
        # =================================================

        security_analysis = None

        if security is not None:

            security_analysis = (
                calculate_security_score(
                    security
                )
            )

        # =================================================
        # 4. Liquidity Score
        # =================================================

        liquidity_analysis = (
            calculate_liquidity_score(
                pair
            )
        )

        # =================================================
        # 5. Holder Score
        # =================================================

        holder_analysis = None

        if security is not None:

            holder_analysis = (
                calculate_holder_score(
                    security
                )
            )

        # =================================================
        # 6. Scores for Intelligence Engine
        # =================================================

        security_score = 0

        if security_analysis is not None:

            security_score = (
                security_analysis.get(
                    "score",
                    0,
                )
            )

        liquidity_score = (
            liquidity_analysis.get(
                "score",
                0,
            )
        )

        holder_score = 0

        if holder_analysis is not None:

            holder_score = (
                holder_analysis.get(
                    "score",
                    0,
                )
            )

        # =================================================
        # 7. Intelligence Engine
        # =================================================

        intelligence = (
            await analyze_intelligence_layers(
                mint=mint,
                security_score=security_score,
                liquidity_score=liquidity_score,
                holder_score=holder_score,
            )
        )

        # =================================================
        # 8. Main Message
        # =================================================

        message = (
            "🧠 **Meme Intelligence — تحليل شامل**\n\n"
            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
            f"💵 **السعر:** `${price_usd}`\n\n"
        )

        # =================================================
        # Market
        # =================================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 **بيانات السوق**\n\n"
            f"💧 **السيولة:** "
            f"`{format_money(liquidity_usd)}`\n"
            f"📈 **حجم 24س:** "
            f"`{format_money(volume_24h)}`\n"
            f"📉 **تغير 24س:** "
            f"`{change_24h}%`\n"
            f"🟢 **شراء 24س:** `{buys}`\n"
            f"🔴 **بيع 24س:** `{sells}`\n\n"
        )

        # =================================================
        # Security
        # =================================================

        if security_analysis is None:

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **Security Score**\n\n"
                "⚠️ لم يتم الحصول على بيانات "
                "أمنية كافية.\n\n"
                "غياب البيانات لا يعني أن العملة آمنة.\n\n"
            )

        else:

            score = security_analysis.get(
                "score",
                0,
            )

            grade = security_analysis.get(
                "grade",
                "غير متوفر",
            )

            top1 = security_analysis.get(
                "top1",
                0,
            )

            top10 = security_analysis.get(
                "top10",
                0,
            )

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **Security Score**\n\n"
                f"🎯 **درجة الأمان:** "
                f"`{score}/100`\n"
                f"📋 **التقييم:** `{grade}`\n"
                f"👤 **أكبر حامل:** "
                f"`{top1:.2f}%`\n"
                f"👥 **أكبر 10 حامليْن:** "
                f"`{top10:.2f}%`\n\n"
            )

            critical = (
                security_analysis.get(
                    "critical",
                    [],
                )
            )

            if critical:

                message += (
                    "🚨 **مؤشرات حرجة:**\n"
                )

                for item in critical[:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

            security_warnings = (
                security_analysis.get(
                    "warnings",
                    [],
                )
            )

            if security_warnings:

                message += (
                    "⚠️ **تحذيرات الأمان:**\n"
                )

                for item in security_warnings[:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # =================================================
        # Liquidity
        # =================================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "💧 **Liquidity Score**\n\n"
            f"🎯 **درجة السيولة:** "
            f"`{liquidity_analysis.get('score', 0)}/100`\n"
            f"📋 **التقييم:** "
            f"`{liquidity_analysis.get('grade', 'غير متوفر')}`\n"
            f"💧 **السيولة:** "
            f"`{format_money(liquidity_analysis.get('liquidity_usd', 0))}`\n"
            f"📈 **حجم 24س:** "
            f"`{format_money(liquidity_analysis.get('volume_24h', 0))}`\n"
            f"🔄 **الحجم/السيولة:** "
            f"`{liquidity_analysis.get('volume_liquidity_ratio', 0):.3f}x`\n\n"
        )

        liquidity_warnings = (
            liquidity_analysis.get(
                "warnings",
                [],
            )
        )

        if liquidity_warnings:

            message += (
                "⚠️ **ملاحظات السيولة:**\n"
            )

            for item in liquidity_warnings[:5]:

                message += (
                    f"• {item}\n"
                )

            message += "\n"

        liquidity_positive = (
            liquidity_analysis.get(
                "positive",
                [],
            )
        )

        if liquidity_positive:

            message += (
                "✅ **نقاط السيولة الإيجابية:**\n"
            )

            for item in liquidity_positive[:5]:

                message += (
                    f"• {item}\n"
                )

            message += "\n"

        # =================================================
        # Holders
        # =================================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "👥 **Holder Score**\n\n"
        )

        if holder_analysis is None:

            message += (
                "⚠️ **درجة الحاملين:** "
                "غير متوفرة\n\n"
                "لا توجد بيانات كافية لتحليل "
                "توزيع الحيازة.\n\n"
            )

        else:

            holder_score_value = (
                holder_analysis.get(
                    "score",
                    0,
                )
            )

            holder_grade = (
                holder_analysis.get(
                    "grade",
                    "غير متوفر",
                )
            )

            message += (
                f"🎯 **درجة الحاملين:** "
                f"`{holder_score_value}/100`\n"
                f"📋 **التقييم:** "
                f"`{holder_grade}`\n"
                f"👤 **أكبر حامل:** "
                f"`{holder_analysis.get('top1', 0):.2f}%`\n"
                f"👥 **أكبر 10 حامليْن:** "
                f"`{holder_analysis.get('top10', 0):.2f}%`\n"
                f"📊 **عدد البيانات المحللة:** "
                f"`{holder_analysis.get('holder_count', 0)}`\n"
                f"🔒 **حاملون مقفلون:** "
                f"`{holder_analysis.get('locked_count', 0)}`\n"
                f"🚨 **عناوين مشبوهة:** "
                f"`{holder_analysis.get('malicious_count', 0)}`\n\n"
            )

            holder_warnings = (
                holder_analysis.get(
                    "warnings",
                    [],
                )
            )

            if holder_warnings:

                message += (
                    "⚠️ **مخاطر توزيع الحيازة:**\n"
                )

                for item in holder_warnings[:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

            holder_positive = (
                holder_analysis.get(
                    "positive",
                    [],
                )
            )

            if holder_positive:

                message += (
                    "✅ **نقاط إيجابية للحاملين:**\n"
                )

                for item in holder_positive[:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # =================================================
        # Intelligence
        # =================================================

        message += build_intelligence_message(
            intelligence
        )

        # =================================================
        # Final Disclaimer + Market Link
        # =================================================

        pair_url = pair.get(
            "url",
            "غير متوفر",
        )

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ **ملاحظة مهمة:**\n\n"
            "هذا النظام يقدم تحليلًا آليًا "
            "لبيانات السوق والسلسلة.\n"
            "الدرجات والاحتمالات ليست ضمانًا للربح "
            "ولا توصية مالية.\n"
            "يجب اعتبار النتائج أداة مساعدة "
            "للبحث واتخاذ القرار.\n\n"
            f"🔗 **السوق:** {pair_url}"
        )

        await send_long_message(
            interaction,
            message,
        )

    except Exception as error:

        print(
            "خطأ في تحليل العملة:",
            repr(error),
        )

        try:

            await interaction.followup.send(
                "⚠️ **حدث خطأ أثناء تحليل العملة.**\n\n"
                "تم تسجيل الخطأ في Railway Logs.\n"
                "تحقق من السجلات لمعرفة السبب."
            )

        except Exception as followup_error:

            print(
                "خطأ أثناء إرسال رسالة الخطأ:",
                repr(followup_error),
            )


# =========================================================
# Start Bot
# =========================================================

bot.run(TOKEN)
