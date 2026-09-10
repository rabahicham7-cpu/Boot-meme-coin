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


def get_security_result(data, mint):
    """
    استخراج بيانات التوكن من GoPlus.
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


def get_score(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_intelligence_message(
    intelligence,
):
    """
    بناء الجزء الخاص بالذكاء التحليلي.
    """

    message = ""

    traders = intelligence.get("traders")

    smart_money = intelligence.get(
        "smart_money"
    )

    funding = intelligence.get(
        "funding"
    )

    composite = intelligence.get(
        "composite"
    )

    trader_count = intelligence.get(
        "trader_count",
        0,
    )

    warnings = intelligence.get(
        "warnings",
        [],
    )

    # ==========================================
    # Trader Intelligence
    # ==========================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "👨‍💻 **Trader Intelligence**\n\n"
    )

    message += (
        f"👥 **المتداولون المحللون:** "
        f"`{trader_count}`\n"
    )

    if isinstance(traders, dict):

        message += (
            f"📊 **متوسط درجة المتداولين:** "
            f"`{get_score(traders.get('average_score')):.2f}/100`\n"
        )

        message += (
            f"🟢 **متداولون رابحون:** "
            f"`{traders.get('profitable', 0)}`\n"
        )

        message += (
            f"🔴 **متداولون خاسرون:** "
            f"`{traders.get('losing', 0)}`\n"
        )

        message += (
            f"🧠 **Smart/Pro Traders:** "
            f"`{traders.get('smart_traders', 0)}`\n"
        )

        message += (
            f"⚠️ **Risk Traders:** "
            f"`{traders.get('risk_traders', 0)}`\n"
        )

        message += (
            f"📊 **ثقة البيانات:** "
            f"`{get_score(traders.get('confidence')):.2f}%`\n\n"
        )

    else:

        message += (
            "⚠️ بيانات المتداولين غير متوفرة.\n\n"
        )

    # ==========================================
    # Smart Money
    # ==========================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🐋 **Smart Money**\n\n"
    )

    if isinstance(smart_money, dict):

        smart_score = get_score(
            smart_money.get(
                "smart_money_score"
            )
        )

        smart_flow = smart_money.get(
            "flow",
            "غير معروف",
        )

        smart_traders = smart_money.get(
            "smart_traders",
            0,
        )

        risk_smart = smart_money.get(
            "risk_smart_traders",
            0,
        )

        message += (
            f"🎯 **الدرجة:** "
            f"`{smart_score:.2f}/100`\n"
        )

        message += (
            f"🔄 **التدفق:** "
            f"`{smart_flow}`\n"
        )

        message += (
            f"🧠 **Smart/Pro:** "
            f"`{smart_traders}`\n"
        )

        message += (
            f"⚠️ **Smart Traders عالية المخاطر:** "
            f"`{risk_smart}`\n"
        )

        message += (
            f"📊 **ثقة البيانات:** "
            f"`{get_score(smart_money.get('confidence')):.2f}%`\n\n"
        )

    else:

        message += (
            "⚠️ بيانات Smart Money غير متوفرة.\n\n"
        )

    # ==========================================
    # Funding Intelligence
    # ==========================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🔗 **Funding Intelligence**\n\n"
    )

    if isinstance(funding, dict):

        funding_risk = get_score(
            funding.get(
                "risk_score"
            )
        )

        shared_funders = funding.get(
            "shared_funders",
            0,
        )

        largest_cluster = funding.get(
            "largest_cluster",
            0,
        )

        suspicious_clusters = funding.get(
            "suspicious_clusters",
            0,
        )

        message += (
            f"⚠️ **Funding Risk:** "
            f"`{funding_risk:.2f}/100`\n"
        )

        message += (
            f"🔗 **الممولون المشتركون:** "
            f"`{shared_funders}`\n"
        )

        message += (
            f"👥 **أكبر مجموعة:** "
            f"`{largest_cluster}`\n"
        )

        message += (
            f"🚨 **مجموعات مشبوهة:** "
            f"`{suspicious_clusters}`\n"
        )

        message += (
            f"📊 **ثقة البيانات:** "
            f"`{get_score(funding.get('confidence')):.2f}%`\n\n"
        )

    else:

        message += (
            "⚠️ بيانات التمويل غير متوفرة.\n\n"
        )

    # ==========================================
    # Composite
    # ==========================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🧠 **Composite Intelligence Score**\n\n"
    )

    if isinstance(composite, dict):

        opportunity = get_score(
            composite.get(
                "opportunity_score"
            )
        )

        risk = get_score(
            composite.get(
                "risk_score"
            )
        )

        confidence = get_score(
            composite.get(
                "confidence"
            )
        )

        grade = composite.get(
            "grade",
            "N/A",
        )

        decision_ar = composite.get(
            "decision_ar",
            "غير محدد",
        )

        message += (
            f"🎯 **Opportunity Score:** "
            f"`{opportunity:.2f}/100`\n"
        )

        message += (
            f"⚠️ **Risk Score:** "
            f"`{risk:.2f}/100`\n"
        )

        message += (
            f"📊 **Confidence:** "
            f"`{confidence:.2f}%`\n"
        )

        message += (
            f"🏷️ **Grade:** "
            f"`{grade}`\n"
        )

        message += (
            f"🧭 **القرار التحليلي:** "
            f"**{decision_ar}**\n\n"
        )

        components = composite.get(
            "components"
        )

        if isinstance(components, dict):

            message += (
                "**مكونات الدرجة:**\n"
            )

            message += (
                f"• الأمان: "
                f"`{get_score(components.get('security')):.2f}`\n"
            )

            message += (
                f"• السيولة: "
                f"`{get_score(components.get('liquidity')):.2f}`\n"
            )

            message += (
                f"• الحاملون: "
                f"`{get_score(components.get('holders')):.2f}`\n"
            )

            message += (
                f"• المتداولون: "
                f"`{get_score(components.get('traders')):.2f}`\n"
            )

            message += (
                f"• Smart Money: "
                f"`{get_score(components.get('smart_money')):.2f}`\n"
            )

            message += (
                f"• Funding Risk: "
                f"`{get_score(components.get('funding_risk')):.2f}`\n\n"
            )

    else:

        message += (
            "⚠️ لم يتم حساب Composite Score.\n\n"
        )

    # ==========================================
    # Warnings
    # ==========================================

    if warnings:

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ **ملاحظات المحرك**\n\n"
        )

        for warning in warnings[:5]:

            message += (
                f"• {warning}\n"
            )

        message += "\n"

    return message


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


@bot.tree.command(
    name="ping",
    description="اختبار اتصال البوت"
)
async def ping(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "🟢 البوت يعمل بشكل صحيح."
    )


@bot.tree.command(
    name="token",
    description=(
        "تحليل شامل لعملة Solana "
        "والأمان والسيولة والمتداولين"
    )
)
@app_commands.describe(
    mint="عنوان Mint الخاص بالعملة"
)
async def token(
    interaction: discord.Interaction,
    mint: str
):

    await interaction.response.defer()

    try:

        # ==========================================
        # 1. Market Data
        # ==========================================

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
            {}
        )

        name = base_token.get(
            "name",
            "غير معروف"
        )

        symbol = base_token.get(
            "symbol",
            "غير معروف"
        )

        price_usd = pair.get(
            "priceUsd",
            "غير متوفر"
        )

        liquidity = pair.get(
            "liquidity",
            {}
        )

        volume = pair.get(
            "volume",
            {}
        )

        price_change = pair.get(
            "priceChange",
            {}
        )

        txns = pair.get(
            "txns",
            {}
        )

        liquidity_usd = (
            liquidity.get("usd", 0)
            if isinstance(liquidity, dict)
            else 0
        )

        volume_24h = (
            volume.get("h24", 0)
            if isinstance(volume, dict)
            else 0
        )

        change_24h = (
            price_change.get("h24", 0)
            if isinstance(price_change, dict)
            else 0
        )

        txns_24h = (
            txns.get("h24", {})
            if isinstance(txns, dict)
            else {}
        )

        buys = (
            txns_24h.get("buys", 0)
            if isinstance(txns_24h, dict)
            else 0
        )

        sells = (
            txns_24h.get("sells", 0)
            if isinstance(txns_24h, dict)
            else 0
        )

        # ==========================================
        # 2. Security Data
        # ==========================================

        security_response = (
            await get_token_security(
                mint
            )
        )

        security = get_security_result(
            security_response,
            mint
        )

        # ==========================================
        # 3. Security Score
        # ==========================================

        security_analysis = None

        if security is not None:

            security_analysis = (
                calculate_security_score(
                    security
                )
            )

        security_score = (
            security_analysis["score"]
            if security_analysis
            else 0
        )

        # ==========================================
        # 4. Liquidity Score
        # ==========================================

        liquidity_analysis = (
            calculate_liquidity_score(
                pair
            )
        )

        liquidity_score = (
            liquidity_analysis["score"]
        )

        # ==========================================
        # 5. Holder Score
        # ==========================================

        holder_analysis = None

        if security is not None:

            holder_analysis = (
                calculate_holder_score(
                    security
                )
            )

        holder_score = (
            holder_analysis["score"]
            if holder_analysis
            else 0
        )

        # ==========================================
        # 6. Intelligence Engine
        # ==========================================

        intelligence = (
            await analyze_intelligence_layers(

                mint=mint,

                security_score=security_score,

                liquidity_score=liquidity_score,

                holder_score=holder_score,
            )
        )

        # ==========================================
        # 7. Base Message
        # ==========================================

        message = (
            "🧠 **Meme Intelligence — تحليل شامل**\n\n"

            f"🪙 **العملة:** `{name}`\n"

            f"🏷️ **الرمز:** `${symbol}`\n"

            f"💵 **السعر:** "
            f"`${price_usd}`\n\n"

            "━━━━━━━━━━━━━━━━━━\n"

            "📊 **بيانات السوق**\n\n"

            f"💧 **السيولة:** "
            f"`{format_money(liquidity_usd)}`\n"

            f"📈 **حجم 24س:** "
            f"`{format_money(volume_24h)}`\n"

            f"📉 **تغير 24س:** "
            f"`{change_24h}%`\n"

            f"🟢 **شراء 24س:** "
            f"`{buys}`\n"

            f"🔴 **بيع 24س:** "
            f"`{sells}`\n\n"
        )

        # ==========================================
        # 8. Security
        # ==========================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "🛡️ **Security Score**\n\n"
        )

        if security_analysis is None:

            message += (
                "⚠️ البيانات الأمنية غير كافية.\n\n"
            )

        else:

            message += (
                f"🎯 **الدرجة:** "
                f"`{security_analysis['score']}/100`\n"

                f"📋 **التقييم:** "
                f"`{security_analysis['grade']}`\n"

                f"👤 **أكبر حامل:** "
                f"`{security_analysis['top1']:.2f}%`\n"

                f"👥 **أكبر 10 حامليْن:** "
                f"`{security_analysis['top10']:.2f}%`\n\n"
            )

            if security_analysis["critical"]:

                message += (
                    "🚨 **مؤشرات حرجة:**\n"
                )

                for item in security_analysis[
                    "critical"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

            if security_analysis["warnings"]:

                message += (
                    "⚠️ **تحذيرات:**\n"
                )

                for item in security_analysis[
                    "warnings"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # ==========================================
        # 9. Liquidity
        # ==========================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "💧 **Liquidity Score**\n\n"

            f"🎯 **الدرجة:** "
            f"`{liquidity_analysis['score']}/100`\n"

            f"📋 **التقييم:** "
            f"`{liquidity_analysis['grade']}`\n"

            f"💧 **السيولة:** "
            f"`{format_money(liquidity_analysis['liquidity_usd'])}`\n"

            f"📈 **حجم 24س:** "
            f"`{format_money(liquidity_analysis['volume_24h'])}`\n"

            f"🔄 **الحجم/السيولة:** "
            f"`{liquidity_analysis['volume_liquidity_ratio']:.3f}x`\n\n"
        )

        if liquidity_analysis["warnings"]:

            message += (
                "⚠️ **ملاحظات:**\n"
            )

            for item in liquidity_analysis[
                "warnings"
            ][:5]:

                message += (
                    f"• {item}\n"
                )

            message += "\n"

        # ==========================================
        # 10. Holder Score
        # ==========================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "👥 **Holder Score**\n\n"
        )

        if holder_analysis is None:

            message += (
                "⚠️ البيانات غير كافية.\n\n"
            )

        else:

            message += (
                f"🎯 **الدرجة:** "
                f"`{holder_analysis['score']}/100`\n"

                f"📋 **التقييم:** "
                f"`{holder_analysis['grade']}`\n"

                f"👤 **أكبر حامل:** "
                f"`{holder_analysis['top1']:.2f}%`\n"

                f"👥 **أكبر 10 حامليْن:** "
                f"`{holder_analysis['top10']:.2f}%`\n"

                f"📊 **البيانات المحللة:** "
                f"`{holder_analysis['holder_count']}`\n"

                f"🔒 **حاملون مقفلون:** "
                f"`{holder_analysis['locked_count']}`\n"

                f"🚨 **عناوين مشبوهة:** "
                f"`{holder_analysis['malicious_count']}`\n\n"
            )

            if holder_analysis["warnings"]:

                message += (
                    "⚠️ **مخاطر التوزيع:**\n"
                )

                for item in holder_analysis[
                    "warnings"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # ==========================================
        # 11. Intelligence
        # ==========================================

        message += build_intelligence_message(
            intelligence
        )

        # ==========================================
        # 12. Final Disclaimer + Link
        # ==========================================

        pair_url = pair.get(
            "url",
            "غير متوفر"
        )

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ **ملاحظة مهمة**\n\n"

            "هذا نظام تحليل احتمالي يعتمد "
            "على البيانات المتاحة وقت الفحص.\n"

            "النتائج ليست ضمانًا للربح "
            "وليست توصية مالية.\n\n"

            f"🔗 **السوق:** {pair_url}"
        )

        # ==========================================
        # 13. Discord message safety
        # ==========================================

        if len(message) > 1950:

            message = (
                message[:1900]
                + "\n\n"
                "… تم اختصار التقرير "
                "لحدود Discord."
            )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        print(
            "خطأ في تحليل العملة:",
            repr(error)
        )

        await interaction.followup.send(
            "⚠️ حدث خطأ أثناء تحليل العملة.\n"
            "تحقق من سجلات Railway."
        )


bot.run(TOKEN)
