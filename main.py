import discord
from discord import app_commands
from dotenv import load_dotenv
from data.dexscreener import get_token_data
import os


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN غير موجود")


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
    description="تحليل بيانات عملة Solana"
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
        pair = await get_token_data(mint)

        if not pair:
            await interaction.followup.send(
                "❌ لم يتم العثور على بيانات لهذه العملة على شبكة Solana."
            )
            return

        base_token = pair.get("baseToken", {})
        quote_token = pair.get("quoteToken", {})
        liquidity = pair.get("liquidity", {})
        volume = pair.get("volume", {})
        price_change = pair.get("priceChange", {})
        txns = pair.get("txns", {})

        name = base_token.get("name", "غير معروف")
        symbol = base_token.get("symbol", "غير معروف")
        price_usd = pair.get("priceUsd", "غير متوفر")

        liquidity_usd = liquidity.get("usd", 0)
        volume_24h = volume.get("h24", 0)
        change_24h = price_change.get("h24", 0)

        buys = txns.get("h24", {}).get("buys", 0)
        sells = txns.get("h24", {}).get("sells", 0)

        message = (
            f"🪙 **بيانات العملة**\n\n"
            f"**الاسم:** {name}\n"
            f"**الرمز:** `${symbol}`\n"
            f"**السعر:** `${price_usd}`\n\n"
            f"💧 **السيولة:** `${liquidity_usd:,.2f}`\n"
            f"📊 **حجم التداول 24س:** `${volume_24h:,.2f}`\n"
            f"📈 **التغير 24س:** `{change_24h}%`\n"
            f"🟢 **عمليات الشراء:** `{buys}`\n"
            f"🔴 **عمليات البيع:** `{sells}`\n\n"
            f"🔗 **الرابط:** {pair.get('url', 'غير متوفر')}"
        )

        await interaction.followup.send(message)

    except Exception as error:
        print(f"خطأ في تحليل العملة: {error}")

        await interaction.followup.send(
            "⚠️ حدث خطأ أثناء جلب بيانات العملة."
        )


bot.run(TOKEN)
