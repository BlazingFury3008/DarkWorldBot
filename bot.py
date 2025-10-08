import discord
from discord.ext import commands  # Use 'commands' directly instead of importing Bot alone
from dotenv import dotenv_values
import asyncio

from cogs import helper, character, tupper, diceroller
from libs.database_loader import init_db

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
    #await bot.add_cog(dta.DTA(bot))
    #await bot.add_cog(scenetracker.SceneTracker(bot))
    await bot.add_cog(helper.Helper(bot))
    await bot.add_cog(character.CharacterCog(bot))
    #await bot.add_cog(tupper.Tupper(bot))

# Entrypoint
if __name__ == "__main__":
    async def main():
        init_db()
        await register_bot()
        await bot.start(config['DISCORD_KEY'])

    asyncio.run(main())
