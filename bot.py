import discord
from discord.ext import commands  # Use 'commands' directly instead of importing Bot alone
from dotenv import dotenv_values
import asyncio

from cogs import diceroller, dta, scenetracker, helper

# Load configuration from .env
config = dotenv_values(".env")

# Setup Discord Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Create the bot instance
bot = commands.Bot(command_prefix="~", intents=intents)

# Register event
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

# Async function to register cogs
async def register_bot():
    await bot.add_cog(diceroller.Diceroller(bot))
    await bot.add_cog(dta.DTA(bot))
    await bot.add_cog(scenetracker.SceneTracker(bot))
    await bot.add_cog(helper.Helper(bot))

# Entrypoint
if __name__ == "__main__":
    async def main():
        await register_bot()
        await bot.start(config['DISCORD_KEY'])

    asyncio.run(main())
