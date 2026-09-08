import os

import discord
from discord import app_commands
from dotenv import load_dotenv

from data.dexscreener import get_token_data
from security.goplus import get_token_security


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN غير موجود")


def is_enabled(value):
    return value in ("1", 1, True)


def format_money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "غير متوفر"


def format_percent(value):
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "غير متوفر"


def get_security_result(data, mint):
    """
    استخراج نتيجة العملة من استجابة GoPlus.
    """
    if not data:
        return None

    result = data.get("result")

    if not isinstance(result, dict):
        return None

    # بعض استجابات GoPlus تستخدم عنوان الـ mint كمفتاح.
    token_data = result.get(mint)

    if isinstance(token_data, dict):
        return token_data

    # حماية إضافية إذا تغير شكل الاستجابة.
    if len(result) == 1:
        first_value = next(iter(result.values()))

        if isinstance(first_value, dict):
            return first_value

    return None


def analyze_security(security):
    """
    تحليل أمني أولي deterministic.
    لا يعتبر البيانات المفقودة آمنة.
    """

    critical = []
    warnings = []

    # صلاحية إنشاء Tokens جديدة
    mintable = security.get("mintable", {})
    if isinstance(mintable, dict) and is_enabled(mintable.get("status")):
        critical.append("صلاحية Mint ما زالت مفعلة")

    # صلاحية تجميد الحسابات
    freezable = security.get("freezable", {})
    if isinstance(freezable, dict) and is_enabled(freezable.get("status")):
        critical.append("صلاحية Freeze ما زالت مفعلة")

    # إمكانية إغلاق البرنامج
    closable = security.get("closable", {})
    if isinstance(closable, dict) and is_enabled(closable.get("status")):
        warnings.append("إمكانية إغلاق برنامج التوكن موجودة")

    # إمكانية تعديل أرصدة المستخدمين
    balance_mutable = security.get(
        "balance_mutable_authority"
    )

    if isinstance(balance_mutable, dict):
        if is_enabled(balance_mutable.get("status")):
            critical.append(
                "هناك صلاحية محتملة لتعديل أرصدة المستخدمين"
            )

    # Metadata قابلة للتعديل
    metadata_mutable = security.get("metadata_mutable", {})

    if isinstance(metadata_mutable, dict):
        if is_enabled(metadata_mutable.get("status")):
            warnings.append(
                "بيانات التوكن Metadata قابلة للتعديل"
            )

    # Token غير قابل للتحويل
    if is_enabled(security.get("non_transferable")):
        critical.append(
            "التوكن غير قابل للتحويل"
        )

    # Transfer Hook
    transfer_hook = security.get("transfer_hook")

    if isinstance(transfer_hook, dict):
        if is_enabled(transfer_hook.get("malicious_address")):
            critical.append(
                "Transfer Hook مرتبط بعنوان مصنف ضار"
            )

    # رسوم التحويل
    transfer_fee = security.get("transfer_fee")

    if isinstance(transfer_fee, dict):
        current_fee = transfer_fee.get("current_fee_rate")

        try:
            if current_fee is not None:
                fee = float(current_fee)

                if fee > 100:
                    warnings.append(
                        f"رسوم تحويل مرتفعة: {fee / 100:.2f}%"
                    )
        except (TypeError, ValueError):
            pass

    # تحليل Top Holders
    holders = security.get("holders", [])

    top1_percent = 0.0
    top10_percent = 0.0

    if isinstance(holders, list):
        percentages = []

        for holder in holders[:10]:
            try:
                percent = float(
                    holder.get("percent", 0)
                )
            except (TypeError, ValueError):
                percent = 0

            # GoPlus قد يعرض النسبة كـ 0.1 = 10%
            if percent <= 1:
                percent *= 100

            percentages.append(percent)

        if percentages:
            top1_percent = percentages[0]
            top10_percent = sum(percentages)

    if top1_percent >= 50:
        critical.append(
            f"تركيز مرتفع جدًا: أكبر حامل يملك {top1_percent:.2f}%"
        )
    elif top1_percent >= 20:
        warnings.append(
            f"تركيز مرتفع: أكبر حامل يملك {top1_percent:.2f}%"
        )

    if top10_percent >= 80:
        critical.append(
            f"تركيز شديد: أكبر 10 حامليْن يملكون {top10_percent:.2f}%"
        )
    elif top10_percent >= 50:
        warnings.append(
            f"تركيز ملحوظ: أكبر 10 حامليْن يملكون {top10_percent:.2f}%"
        )

    # تحديد الحالة
    if critical:
        status = "🔴 خطر مرتفع"
    elif warnings:
        status = "🟠 تحذير"
    else:
        status = "🟢 لا توجد مؤشرات حرجة في الفحص الأولي"

    return {
        "status": status,
        "critical": critical,
        "warnings": warnings,
        "top1": top1_percent,
        "top10": top10_percent,
    }


class MemeIntelligenceBot(discord.Client):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        print(f"تم تشغيل البوت: {self.user}")


bot = MemeIntelligenceBot()


@bot.tree.command(
    name="ping",
    description="اختبار اتصال البوت"
)
async def ping(interaction: discord.Interaction):

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
                "❌ لم يتم العثور على بيانات سوق لهذه العملة على Solana."
            )
            return

        base_token = pair.get("baseToken", {})

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
        # 2. فحص GoPlus
        # ==========================================

        security_response = await get_token_security(mint)

        security = get_security_result(
            security_response,
            mint
        )

        # ==========================================
        # 3. الرسالة
        # ==========================================

        message = (
            "🧠 **Meme Intelligence — تحليل أولي**\n\n"

            f"🪙 **العملة:** `{name}`\n"
            f"**الرمز:** `${symbol}`\n"
            f"**السعر:** `{price_usd}$`\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "📊 **بيانات السوق**\n\n"

            f"💧 **السيولة:** `{format_money(liquidity_usd)}`\n"
            f"📈 **حجم 24س:** `{format_money(volume_24h)}`\n"
            f"📉 **تغير 24س:** `{change_24h}%`\n"
            f"🟢 **شراء 24س:** `{buys}`\n"
            f"🔴 **بيع 24س:** `{sells}`\n\n"
        )

        if security is None:

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **الفحص الأمني**\n\n"
                "⚠️ لم يتم الحصول على بيانات أمنية كافية.\n"
                "لا يتم اعتبار غياب البيانات دليلًا على الأمان.\n"
            )

        else:

            analysis = analyze_security(
                security
            )

            message += (
                "━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **الفحص الأمني الأولي**\n\n"

                f"**الحالة:** {analysis['status']}\n"
                f"👤 **أكبر حامل:** `{analysis['top1']:.2f}%`\n"
                f"👥 **أكبر 10 حامليْن:** `{analysis['top10']:.2f}%`\n\n"
            )

            if analysis["critical"]:

                message += (
                    "🚨 **مؤشرات حرجة:**\n"
                )

                for item in analysis["critical"][:5]:
                    message += f"• {item}\n"

                message += "\n"

            if analysis["warnings"]:

                message += (
                    "⚠️ **تحذيرات:**\n"
                )

                for item in analysis["warnings"][:5]:
                    message += f"• {item}\n"

                message += "\n"

            if (
                not analysis["critical"]
                and not analysis["warnings"]
            ):

                message += (
                    "لم تظهر مؤشرات حرجة في الفحص الأولي.\n"
                )

        message += (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "⚠️ **ملاحظة:** هذا فحص أولي وليس توصية شراء أو ضمانًا للربح.\n\n"
            f"🔗 {pair.get('url', 'غير متوفر')}"
        )

        await interaction.followup.send(
            message
        )

    except Exception as error:

        print(
            f"خطأ في تحليل العملة: {error}"
        )

        await interaction.followup.send(
            "⚠️ حدث خطأ أثناء الفحص. "
            "تحقق من سجلات Railway لمعرفة التفاصيل."
        )


bot.run(TOKEN)
