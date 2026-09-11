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


# =========================================================
# Environment
# =========================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN غير موجود في Environment Variables"
    )


# =========================================================
# Formatting Helpers
# =========================================================

def format_money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "غير متوفر"


def format_percent(value):
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "غير متوفر"


# =========================================================
# GoPlus Result Extraction
# =========================================================

def get_security_result(data, mint):
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


# =========================================================
# Discord Message Splitting
# =========================================================

async def send_long_message(
    interaction: discord.Interaction,
    message: str,
):
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


# =========================================================
# Market Intelligence Message
# =========================================================

def build_market_message(market):
    if not isinstance(market, dict):
        return ""

    message = (
        "━━━━━━━━━━━━━━━━━━\n"
        "📊 **Market Intelligence**\n\n"
    )

    market_score = market.get(
        "market_score",
        0,
    )

    market_state = market.get(
        "market_state",
        "unknown",
    )

    market_state_names = {
        "bullish": "صاعد",
        "constructive": "إيجابي",
        "neutral": "محايد",
        "weak": "ضعيف",
        "bearish": "هابط",
    }

    market_state_ar = market_state_names.get(
        market_state,
        market_state,
    )

    market_confidence = market.get(
        "confidence",
        0,
    )

    message += (
        f"🎯 **Market Score:** "
        f"`{market_score:.2f}/100`\n"
        f"🧭 **حالة السوق:** "
        f"`{market_state_ar}`\n"
        f"🎯 **ثقة البيانات:** "
        f"`{market_confidence:.0f}%`\n\n"
    )

    # -----------------------------------------------------
    # Momentum
    # -----------------------------------------------------

    momentum = market.get(
        "momentum",
        {},
    )

    if isinstance(momentum, dict):

        momentum_score = momentum.get(
            "score",
            0,
        )

        momentum_state = momentum.get(
            "state",
            "unknown",
        )

        momentum_names = {
            "bullish": "صاعد",
            "developing_bullish": "يتطور إيجابيًا",
            "bearish": "هابط",
            "developing_bearish": "يتطور سلبيًا",
            "mixed": "مختلط",
        }

        momentum_ar = momentum_names.get(
            momentum_state,
            momentum_state,
        )

        message += (
            "📈 **Momentum Intelligence**\n"
            f"• الدرجة: `{momentum_score:.2f}/100`\n"
            f"• الحالة: `{momentum_ar}`\n"
            f"• 5m: `{momentum.get('price_change_5m', 0):.2f}%`\n"
            f"• 1h: `{momentum.get('price_change_1h', 0):.2f}%`\n"
            f"• 6h: `{momentum.get('price_change_6h', 0):.2f}%`\n"
            f"• 24h: `{momentum.get('price_change_24h', 0):.2f}%`\n\n"
        )

    # -----------------------------------------------------
    # Buy / Sell Pressure
    # -----------------------------------------------------

    pressure = market.get(
        "buy_sell_pressure",
        {},
    )

    if isinstance(pressure, dict):

        buy_ratio = pressure.get(
            "buy_ratio",
            0,
        )

        sell_ratio = pressure.get(
            "sell_ratio",
            0,
        )

        pressure_score = pressure.get(
            "pressure_score",
            0,
        )

        pressure_state = pressure.get(
            "pressure",
            "unknown",
        )

        pressure_names = {
            "strong_buy": "شراء قوي",
            "buy": "شراء",
            "balanced": "متوازن",
            "sell": "بيع",
            "strong_sell": "بيع قوي",
            "unknown": "غير معروف",
        }

        pressure_ar = pressure_names.get(
            pressure_state,
            pressure_state,
        )

        message += (
            "⚖️ **Buy / Sell Pressure**\n"
            f"• ضغط الشراء: `{buy_ratio * 100:.2f}%`\n"
            f"• ضغط البيع: `{sell_ratio * 100:.2f}%`\n"
            f"• الدرجة: `{pressure_score:.2f}/100`\n"
            f"• الحالة: `{pressure_ar}`\n\n"
        )

    # -----------------------------------------------------
    # Volume Quality
    # -----------------------------------------------------

    volume = market.get(
        "volume_quality",
        {},
    )

    if isinstance(volume, dict):

        volume_score = volume.get(
            "volume_score",
            0,
        )

        volume_ratio = volume.get(
            "volume_liquidity_ratio",
            0,
        )

        quality = volume.get(
            "quality",
            "unknown",
        )

        quality_names = {
            "very_low": "منخفض جدًا",
            "low": "منخفض",
            "healthy": "صحي",
            "strong": "قوي",
            "very_high": "مرتفع جدًا",
            "extreme": "متطرف",
            "unknown": "غير معروف",
        }

        quality_ar = quality_names.get(
            quality,
            quality,
        )

        message += (
            "📊 **Volume Quality**\n"
            f"• الدرجة: `{volume_score:.2f}/100`\n"
            f"• Volume/Liquidity: `{volume_ratio:.2f}x`\n"
            f"• الجودة: `{quality_ar}`\n\n"
        )

    # -----------------------------------------------------
    # Market Structure
    # -----------------------------------------------------

    structure = market.get(
        "market_structure",
        {},
    )

    if isinstance(structure, dict):

        structure_value = structure.get(
            "structure",
            "unknown",
        )

        structure_names = {
            "bullish_alignment": "توافق صاعد",
            "positive_alignment": "توافق إيجابي",
            "bearish_alignment": "توافق هابط",
            "negative_alignment": "توافق سلبي",
            "mixed": "مختلط",
            "unknown": "غير معروف",
        }

        structure_ar = structure_names.get(
            structure_value,
            structure_value,
        )

        positive_frames = structure.get(
            "positive_frames",
            0,
        )

        negative_frames = structure.get(
            "negative_frames",
            0,
        )

        message += (
            "🧭 **Market Structure**\n"
            f"• الهيكل: `{structure_ar}`\n"
            f"• الفترات الإيجابية: `{positive_frames}`\n"
            f"• الفترات السلبية: `{negative_frames}`\n\n"
        )

    return message


# =========================================================
# Trader / Smart Money / Funding Message
# =========================================================

def build_intelligence_message(intelligence):
    if not isinstance(intelligence, dict):
        return ""

    traders = intelligence.get(
        "traders"
    ) or {}

    smart_money = intelligence.get(
        "smart_money"
    ) or {}

    funding = intelligence.get(
        "funding"
    ) or {}

    composite = intelligence.get(
        "composite"
    ) or {}

    message = ""

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

    trader_confidence = traders.get(
        "confidence",
        0,
    )

    message += (
        f"👥 **المتداولون المحللون:** `{trader_count}`\n"
        f"🟢 **رابحون تاريخيًا:** `{profitable}`\n"
        f"🔴 **خاسرون تاريخيًا:** `{losing}`\n"
        f"🧠 **Smart Traders:** `{smart_traders}`\n"
        f"⚠️ **Risk Traders:** `{risk_traders}`\n"
        f"📊 **متوسط الدرجة:** `{average_score:.2f}/100`\n"
        f"🎯 **ثقة البيانات:** `{trader_confidence:.0f}%`\n\n"
        "⚠️ الأرباح التاريخية ليست توقعًا للأداء المستقبلي.\n\n"
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

    smart_confidence = smart_money.get(
        "confidence",
        0,
    )

    message += (
        f"🧠 **Smart Traders:** `{smart_count}`\n"
        f"⚠️ **عالية المخاطر:** `{risk_smart_count}`\n"
        f"🟢 **حجم الشراء:** `{format_money(smart_buy_volume)}`\n"
        f"🔴 **حجم البيع:** `{format_money(smart_sell_volume)}`\n"
        f"📈 **نسبة الشراء:** `{smart_buy_ratio * 100:.2f}%`\n"
        f"📉 **نسبة البيع:** `{smart_sell_ratio * 100:.2f}%`\n"
        f"🎯 **Smart Money Score:** `{smart_score}/100`\n"
        f"🌊 **التدفق:** `{flow_ar}`\n"
        f"🎯 **ثقة البيانات:** `{smart_confidence:.0f}%`\n\n"
    )

    # =====================================================
    # Funding Intelligence
    # =====================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🔗 **Funding Intelligence**\n\n"
    )

    unique_funders = funding.get(
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

    if isinstance(
        suspicious_clusters,
        list,
    ):
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
        f"💳 **مصادر تمويل فريدة:** `{unique_funders}`\n"
        f"🔄 **مصادر مشتركة:** `{shared_funders}`\n"
        f"👥 **أكبر مجموعة:** `{largest_cluster}`\n"
        f"🚨 **مجموعات تحتاج مراجعة:** `{suspicious_count}`\n"
        f"⚠️ **Funding Risk Score:** `{risk_score}/100`\n"
        f"🎯 **ثقة البيانات:** `{funding_confidence:.0f}%`\n\n"
        "⚠️ تشابه مصادر التمويل ليس دليلًا بحد ذاته على التلاعب.\n\n"
    )

    # =====================================================
    # Composite
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

    decision_names = {
        "WATCH": "مراقبة",
        "NEUTRAL": "محايد",
        "AVOID": "تجنب",
    }

    decision_ar = decision_names.get(
        str(decision).upper(),
        decision,
    )

    message += (
        f"📈 **Opportunity Score:** `{opportunity:.2f}/100`\n"
        f"⚠️ **Risk Score:** `{composite_risk:.2f}/100`\n"
        f"🎯 **ثقة البيانات:** `{composite_confidence:.2f}%`\n"
        f"🏆 **Grade:** `{grade}`\n"
        f"🧭 **القرار التحليلي:** `{decision_ar}`\n\n"
    )

    # =====================================================
    # Components
    # =====================================================

    components = composite.get(
        "components",
        {},
    )

    if isinstance(
        components,
        dict,
    ):

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

            if value is None:
                continue

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
                f"• **{label}:** `{value_text}/100`\n"
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
            f"تم تشغيل البوت {self.user}"
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
async def token_command(
    interaction: discord.Interaction,
    mint: str,
):

    await interaction.response.defer()

    try:

        # =================================================
        # 1. DEX Screener
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

        liquidity_data = pair.get(
            "liquidity",
            {},
        )

        volume_data = pair.get(
            "volume",
            {},
        )

        price_change_data = pair.get(
            "priceChange",
            {},
        )

        txns_data = pair.get(
            "txns",
            {},
        )

        if not isinstance(
            liquidity_data,
            dict,
        ):
            liquidity_data = {}

        if not isinstance(
            volume_data,
            dict,
        ):
            volume_data = {}

        if not isinstance(
            price_change_data,
            dict,
        ):
            price_change_data = {}

        if not isinstance(
            txns_data,
            dict,
        ):
            txns_data = {}

        liquidity_usd = liquidity_data.get(
            "usd",
            0,
        )

        volume_24h = volume_data.get(
            "h24",
            0,
        )

        change_24h = price_change_data.get(
            "h24",
            0,
        )

        txns_24h = txns_data.get(
            "h24",
            {},
        )

        if not isinstance(
            txns_24h,
            dict,
        ):
            txns_24h = {}

        buys = txns_24h.get(
            "buys",
            0,
        )

        sells = txns_24h.get(
            "sells",
            0,
        )

        # =================================================
        # 2. GoPlus Security
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

        security_score = 0

        if security_analysis:

            security_score = (
                security_analysis.get(
                    "score",
                    0,
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

        liquidity_score = (
            liquidity_analysis.get(
                "score",
                0,
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

        holder_score = 0

        if holder_analysis:

            holder_score = (
                holder_analysis.get(
                    "score",
                    0,
                )
            )

        # =================================================
        # 6. Full Intelligence Engine
        # =================================================

        intelligence = (
            await analyze_intelligence_layers(
                mint=mint,
                security_score=security_score,
                liquidity_score=liquidity_score,
                holder_score=holder_score,
                pair=pair,
            )
        )

        # =================================================
        # 7. Main Header
        # =================================================

        message = (
            "🧠 **Meme Intelligence — تحليل شامل**\n\n"
            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
            f"💵 **السعر:** `${price_usd}`\n\n"
        )

        # =================================================
        # 8. Market Data
        # =================================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "📊 **بيانات السوق**\n\n"
            f"💧 **السيولة:** `{format_money(liquidity_usd)}`\n"
            f"📈 **حجم 24س:** `{format_money(volume_24h)}`\n"
            f"📉 **تغير 24س:** `{change_24h}%`\n"
            f"🟢 **شراء 24س:** `{buys}`\n"
            f"🔴 **بيع 24س:** `{sells}`\n\n"
        )

        # =================================================
        # 9. Security
        # =================================================

        if security_analysis is None:

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **Security Score**\n\n"
                "⚠️ لا توجد بيانات أمنية كافية.\n\n"
                "غياب البيانات لا يعني أن العملة آمنة.\n\n"
            )

        else:

            security_score_value = (
                security_analysis.get(
                    "score",
                    0,
                )
            )

            security_grade = (
                security_analysis.get(
                    "grade",
                    "غير متوفر",
                )
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
                f"`{security_score_value}/100`\n"
                f"📋 **التقييم:** `{security_grade}`\n"
                f"👤 **أكبر حامل:** `{top1:.2f}%`\n"
                f"👥 **أكبر 10 حامليْن:** `{top10:.2f}%`\n\n"
            )

            critical = security_analysis.get(
                "critical",
                [],
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

            security_warnings = security_analysis.get(
                "warnings",
                [],
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
        # 10. Liquidity
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

        liquidity_warnings = liquidity_analysis.get(
            "warnings",
            [],
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

        # =================================================
        # 11. Holders
        # =================================================

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "👥 **Holder Score**\n\n"
        )

        if holder_analysis is None:

            message += (
                "⚠️ **درجة الحاملين:** غير متوفرة\n\n"
                "لا توجد بيانات كافية لتحليل التوزيع.\n\n"
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
                f"📋 **التقييم:** `{holder_grade}`\n"
                f"👤 **أكبر حامل:** "
                f"`{holder_analysis.get('top1', 0):.2f}%`\n"
                f"👥 **أكبر 10 حامليْن:** "
                f"`{holder_analysis.get('top10', 0):.2f}%`\n"
                f"📊 **البيانات المحللة:** "
                f"`{holder_analysis.get('holder_count', 0)}`\n"
                f"🔒 **حاملون مقفلون:** "
                f"`{holder_analysis.get('locked_count', 0)}`\n"
                f"🚨 **عناوين مشبوهة:** "
                f"`{holder_analysis.get('malicious_count', 0)}`\n\n"
            )

            holder_warnings = holder_analysis.get(
                "warnings",
                [],
            )

            if holder_warnings:

                message += (
                    "⚠️ **مخاطر التوزيع:**\n"
                )

                for item in holder_warnings[:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # =================================================
        # 12. Market Intelligence
        # =================================================

        market = intelligence.get(
            "market"
        )

        message += build_market_message(
            market
        )

        # =================================================
        # 13. Trader / Smart Money / Funding
        # =================================================

        message += build_intelligence_message(
            intelligence
        )

        # =================================================
        # 14. Final Disclaimer
        # =================================================

        pair_url = pair.get(
            "url",
            "غير متوفر",
        )

        message += (
            "━━━━━━━━━━━━━━━━━━\n"
            "⚠️ **ملاحظة مهمة**\n\n"
            "هذا النظام يقدم تحليلًا آليًا "
            "لبيانات السوق والسلسلة.\n\n"
            "الدرجات ليست ضمانًا للربح "
            "ولا توصية مالية.\n\n"
            "Market Intelligence يصف حالة السوق الحالية "
            "ولا يمثل توقعًا مضمونًا للسعر.\n\n"
            "يجب اعتبار النتائج أداة مساعدة "
            "للبحث واتخاذ القرار.\n\n"
            f"🔗 **السوق:** {pair_url}"
        )

        # =================================================
        # 15. Send
        # =================================================

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
                "تم تسجيل الخطأ في Railway Logs."
            )

        except Exception as followup_error:

            print(
                "خطأ أثناء إرسال رسالة الخطأ:",
                repr(followup_error),
            )


# =========================================================
# Start
# =========================================================

if __name__ == "__main__":
    bot.run(TOKEN)
