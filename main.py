import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from data.dexscreener import get_token_data
from security.goplus import get_token_security
from scoring.security_score import calculate_security_score


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN غير موجود")


def format_money(value):
    try:
        return f"${float(value):,.2f}"
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

    # الشكل الشائع:
    # result = {mint_address: {...}}
    if isinstance(result, dict):

        token_data = result.get(mint)

        if isinstance(token_data, dict):
            return token_data

        # البحث عن العنوان بدون حساسية لحالة الأحرف
        for key, value in result.items():

            if str(key).lower() == mint.lower():

                if isinstance(value, dict):
                    return value

        # إذا كان result نفسه يحتوي بيانات التوكن
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

        # حماية إضافية إذا كان هناك عنصر واحد
        if len(result) == 1:

            first_value = next(
                iter(result.values())
            )

            if isinstance(first_value, dict):
                return first_value

    # بعض الاستجابات قد تكون List
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


class MemeIntelligenceBot(discord.Client):

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
    description="فحص السوق والأمان لعملة Solana"
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
        # 1. بيانات السوق
        # ==========================================

        pair = await get_token_data(mint)

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

        liquidity_usd = liquidity.get(
            "usd",
            0
        )

        volume_24h = volume.get(
            "h24",
            0
        )

        change_24h = price_change.get(
            "h24",
            0
        )

        txns_24h = txns.get(
            "h24",
            {}
        )

        buys = txns_24h.get(
            "buys",
            0
        )

        sells = txns_24h.get(
            "sells",
            0
        )

        # ==========================================
        # 2. GoPlus Security
        # ==========================================

        security_response = await get_token_security(
            mint
        )

        security = get_security_result(
            security_response,
            mint
        )

        # ==========================================
        # 3. بداية الرسالة
        # ==========================================

        message = (
            "🧠 **Meme Intelligence — تحليل أولي**\n\n"

            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
            f"💵 **السعر:** `${price_usd}`\n\n"

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

        # ==========================================
        # 4. الفحص الأمني
        # ==========================================

        if security is None:

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **الفحص الأمني**\n\n"

                "⚠️ لم يتم الحصول على بيانات "
                "أمنية كافية.\n"

                "لا يتم اعتبار غياب البيانات "
                "دليلًا على الأمان.\n"
            )

        else:

            analysis = calculate_security_score(
                security
            )

            score = analysis["score"]

            grade = analysis["grade"]

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **Security Score**\n\n"

                f"🎯 **درجة الأمان:** "
                f"`{score}/100`\n"

                f"📋 **التقييم:** {grade}\n\n"

                f"👤 **أكبر حامل:** "
                f"`{analysis['top1']:.2f}%`\n"

                f"👥 **أكبر 10 حامليْن:** "
                f"`{analysis['top10']:.2f}%`\n\n"
            )

            # ======================================
            # مؤشرات حرجة
            # ======================================

            if analysis["critical"]:

                message += (
                    "🚨 **مؤشرات حرجة:**\n"
                )

                for item in analysis[
                    "critical"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

            # ======================================
            # تحذيرات
            # ======================================

            if analysis["warnings"]:

                message += (
                    "⚠️ **تحذيرات:**\n"
                )

                for item in analysis[
                    "warnings"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

            # ======================================
            # نقاط إيجابية
            # ======================================

            if analysis["positive"]:

                message += (
                    "✅ **نقاط إيجابية:**\n"
                )

                for item in analysis[
                    "positive"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )

                message += "\n"

        # ==========================================
        # 5. الرابط
        # ==========================================

        pair_url = pair.get(
            "url",
            "غير متوفر"
        )

        message += (
            "━━━━━━━━━━━━━━━━━━\n"

            "⚠️ **ملاحظة:**\n"
            "هذا تحليل آلي أولي وليس توصية "
            "شراء أو ضمانًا للربح.\n\n"

            f"🔗 **السوق:** {pair_url}"
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        print(
            f"خطأ في تحليل العملة: {error}"
        )

        await interaction.followup.send(
            "⚠️ حدث خطأ أثناء الفحص.\n"
            "تحقق من سجلات Railway لمعرفة التفاصيل."
        )


bot.run(TOKEN)
