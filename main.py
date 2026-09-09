import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from data.dexscreener import get_token_data
from security.goplus import get_token_security

from scoring.security_score import calculate_security_score
from scoring.liquidity_score import calculate_liquidity_score
from scoring.holder_score import calculate_holder_score


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
    description="فحص السوق والأمان والسيولة والحاملين لعملة Solana"
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
        # 2. Security / Holder Data
        # ==========================================

        security_response = await get_token_security(
            mint
        )


        security = get_security_result(
            security_response,
            mint
        )


        # ==========================================
        # 3. Security Analysis
        # ==========================================

        security_analysis = None


        if security is not None:

            security_analysis = (
                calculate_security_score(
                    security
                )
            )


        # ==========================================
        # 4. Liquidity Analysis
        # ==========================================

        liquidity_analysis = (
            calculate_liquidity_score(
                pair
            )
        )


        # ==========================================
        # 5. Holder Analysis
        # ==========================================

        holder_analysis = None


        if security is not None:

            holder_analysis = (
                calculate_holder_score(
                    security
                )
            )


        # ==========================================
        # 6. بداية الرسالة
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
        # 7. Security Score
        # ==========================================

        if security_analysis is None:

            message += (

                "━━━━━━━━━━━━━━━━━━\n"

                "🛡️ **Security Score**\n\n"

                "⚠️ لم يتم الحصول على بيانات "
                "أمنية كافية.\n"

                "لا يتم اعتبار غياب البيانات "
                "دليلًا على الأمان.\n\n"

            )

        else:

            score = security_analysis["score"]

            grade = security_analysis["grade"]


            message += (

                "━━━━━━━━━━━━━━━━━━\n"

                "🛡️ **Security Score**\n\n"

                f"🎯 **درجة الأمان:** "
                f"`{score}/100`\n"

                f"📋 **التقييم:** {grade}\n\n"

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
        # 8. Liquidity Score
        # ==========================================

        message += (

            "━━━━━━━━━━━━━━━━━━\n"

            "💧 **Liquidity Score**\n\n"

            f"🎯 **درجة السيولة:** "
            f"`{liquidity_analysis['score']}/100`\n"

            f"📋 **التقييم:** "
            f"{liquidity_analysis['grade']}\n\n"

            f"💧 **السيولة:** "
            f"`{format_money(liquidity_analysis['liquidity_usd'])}`\n"

            f"📈 **حجم 24س:** "
            f"`{format_money(liquidity_analysis['volume_24h'])}`\n"

            f"🔄 **الحجم/السيولة:** "
            f"`{liquidity_analysis['volume_liquidity_ratio']:.3f}x`\n\n"

        )


        # ==========================================
        # Liquidity Warnings
        # ==========================================

        if liquidity_analysis["warnings"]:

            message += (
                "⚠️ **ملاحظات السيولة:**\n"
            )


            for item in liquidity_analysis[
                "warnings"
            ][:5]:

                message += (
                    f"• {item}\n"
                )


            message += "\n"


        # ==========================================
        # Liquidity Positive Points
        # ==========================================

        if liquidity_analysis["positive"]:

            message += (
                "✅ **نقاط السيولة الإيجابية:**\n"
            )


            for item in liquidity_analysis[
                "positive"
            ][:5]:

                message += (
                    f"• {item}\n"
                )


            message += "\n"


        # ==========================================
        # 9. Holder Score
        # ==========================================

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

            holder_score = (
                holder_analysis["score"]
            )


            holder_grade = (
                holder_analysis["grade"]
            )


            message += (

                f"🎯 **درجة الحاملين:** "
                f"`{holder_score}/100`\n"

                f"📋 **التقييم:** "
                f"{holder_grade}\n\n"

                f"👤 **أكبر حامل:** "
                f"`{holder_analysis['top1']:.2f}%`\n"

                f"👥 **أكبر 10 حامليْن:** "
                f"`{holder_analysis['top10']:.2f}%`\n"

                f"📊 **عدد البيانات المحللة:** "
                f"`{holder_analysis['holder_count']}`\n"

                f"🔒 **حاملون مقفلون:** "
                f"`{holder_analysis['locked_count']}`\n"

                f"🚨 **عناوين مشبوهة:** "
                f"`{holder_analysis['malicious_count']}`\n\n"

            )


            if holder_analysis["warnings"]:

                message += (
                    "⚠️ **مخاطر توزيع الحيازة:**\n"
                )


                for item in holder_analysis[
                    "warnings"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )


                message += "\n"


            if holder_analysis["positive"]:

                message += (
                    "✅ **نقاط إيجابية للحاملين:**\n"
                )


                for item in holder_analysis[
                    "positive"
                ][:5]:

                    message += (
                        f"• {item}\n"
                    )


                message += "\n"


        # ==========================================
        # 10. الرابط والملاحظة
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
