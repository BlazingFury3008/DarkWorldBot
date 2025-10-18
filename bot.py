import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import asyncio
import logging
import sys
import os

from libs.database_loader import init_db

# ---------------------------
# Logging Configuration
# ---------------------------
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
TEST_MODE = config.get("TEST_MODE", "false").lower() == "true"
TEST_GUILD_ID = int(config.get("TEST_GUILD_ID", "0")) if TEST_MODE else None

# ---------------------------
# Setup Discord Intents
# ---------------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="~", intents=intents)

# ---------------------------
# Event: on_ready
# ---------------------------
@bot.event
async def on_ready():
    # Sync commands differently depending on test mode
    try:
        if TEST_MODE and TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            await bot.tree.sync(guild=guild)
            logger.info(f"Slash commands synced to TEST guild {TEST_GUILD_ID}")
        else:
            await bot.tree.sync()
            logger.info("Slash commands synced globally")
    except Exception as e:
        logger.exception(f"Failed to sync commands: {e}")

    print(f"\nLogged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    print("Connected to the following servers:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id}) | Members: {guild.member_count}")
    print("------")

# ---------------------------
# Function: Load all cogs dynamically
# ---------------------------
async def load_all_cogs():
    """Load all cogs from the cogs directory using load_extension."""
    loaded, failed = [], []
    for filename in os.listdir("cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                loaded.append(cog_name)
                logger.info(f"[COG] Loaded {cog_name}")
            except Exception as e:
                failed.append((cog_name, str(e)))
                logger.exception(f"[COG] Failed to load {cog_name}: {e}")

    if loaded:
        logger.info(f"[COG SUMMARY] Loaded {len(loaded)} cogs.")
    if failed:
        logger.warning(f"[COG SUMMARY] {len(failed)} failed to load:")
        for name, err in failed:
            logger.warning(f" - {name}: {err}")

# ---------------------------
# Entrypoint
# ---------------------------
if __name__ == "__main__":
    async def main():
        init_db()
        await load_all_cogs()  # ✅ Loads via extensions instead of add_cog
        await bot.start(config["DISCORD_KEY"])

    asyncio.run(main())
