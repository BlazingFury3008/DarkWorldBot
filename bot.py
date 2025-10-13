import discord
from discord.ext import commands
from dotenv import dotenv_values
import asyncio

from cogs import character, tupper, diceroller, st_commands, dta, macro, utils, show_help
from libs.database_loader import init_db

# ---------------------------
# Logging Configuration
# ---------------------------
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("bot")
logger.info("Logging configured successfully.")

# ---------------------------
# Load configuration from .env
# ---------------------------
config = dotenv_values(".env")
if "DISCORD_KEY" not in config:
    logger.error("DISCORD_KEY not found in .env file.")
    raise SystemExit(1)

# ---------------------------
# Setup Discord Intents
# ---------------------------
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

    # List all servers the bot is in
    print("Connected to the following servers:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id}) | Members: {guild.member_count}")
    print('------')


# Async function to register cogs
async def register_bot():
    await bot.add_cog(diceroller.Diceroller(bot))
    await bot.add_cog(utils.Utils(bot))
    await bot.add_cog(character.CharacterCog(bot))
    await bot.add_cog(st_commands.ST(bot))
    await bot.add_cog(dta.DTA(bot))
    await bot.add_cog(macro.Macro(bot))
    await bot.add_cog(show_help.Help(bot))


# Entrypoint
if __name__ == "__main__":
    async def main():
        init_db()
        await register_bot()
        await bot.start(config['DISCORD_KEY'])

    asyncio.run(main())
