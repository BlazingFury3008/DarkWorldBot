import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import asyncio

from cogs import character, personas, diceroller, st_commands, dta, macro, utils, show_help
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
# Test Mode Settings
# ---------------------------
# Set TEST_MODE=True to restrict commands to TEST_GUILD_ID
TEST_MODE = config.get("TEST_MODE", "false").lower() == "true"
TEST_GUILD_ID = int(config.get("TEST_GUILD_ID", "0")) if TEST_MODE else None

# ---------------------------
# Setup Discord Intents
# ---------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Create the bot instance
bot = commands.Bot(command_prefix="~", intents=intents)


# ---------------------------
# Event: on_ready
# ---------------------------
@bot.event
async def on_ready():
    # Sync commands differently depending on test mode
    if TEST_MODE and TEST_GUILD_ID:
        guild = discord.Object(id=TEST_GUILD_ID)
        await bot.tree.sync(guild=guild)
        logger.info(f"Synced commands to TEST guild {TEST_GUILD_ID}")
    else:
        await bot.tree.sync()
        logger.info("Synced commands globally")

    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

    print("Connected to the following servers:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id}) | Members: {guild.member_count}")
    print('------')


# ---------------------------
# Async function to register cogs
# ---------------------------
async def register_bot():
    await bot.add_cog(diceroller.Diceroller(bot))
    await bot.add_cog(utils.Utils(bot))
    await bot.add_cog(character.CharacterCog(bot))
    await bot.add_cog(st_commands.ST(bot))
    await bot.add_cog(dta.DTA(bot))
    await bot.add_cog(macro.Macro(bot))
    await bot.add_cog(show_help.Help(bot))
    await bot.add_cog(personas.Persona(bot))


# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    async def main():
        init_db()
        await register_bot()
        await bot.start(config['DISCORD_KEY'])

    asyncio.run(main())
