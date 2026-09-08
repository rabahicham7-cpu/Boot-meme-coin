import os

import discord
from discord import app_commands
from dotenv import load_dotenv


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


bot.run(TOKEN)
