import discord
from discord.ext import commands
from dotenv import dotenv_values
import asyncio

from cogs import helper, character, tupper, diceroller, st_commands
from libs.database_loader import init_db

# ---------------------------
# Logging Configuration
# ---------------------------
import logging
import sys

# Configure root logger
logging.basicConfig(
    level=logging.INFO,  # Use INFO in production to reduce debug noise
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),  # Ensure logs go to stdout for Docker/Heroku
    ],
)

# Reduce noise from discord internals
#logging.getLogger("discord").setLevel(logging.WARNING)
#logging.getLogger("discord.http").setLevel(logging.WARNING)
#logging.getLogger("asyncio").setLevel(logging.WARNING)
#logging.getLogger("urllib3").setLevel(logging.WARNING)

# App-level logger
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

# Async function to register cogs
async def register_bot():
    await bot.add_cog(diceroller.Diceroller(bot))
    #await bot.add_cog(dta.DTA(bot))
    #await bot.add_cog(scenetracker.SceneTracker(bot))
    await bot.add_cog(helper.Helper(bot))
    await bot.add_cog(character.CharacterCog(bot))
    await bot.add_cog(st_commands.ST(bot))

    #await bot.add_cog(tupper.Tupper(bot))

# Entrypoint
if __name__ == "__main__":
    async def main():
        init_db()
        await register_bot()
        await bot.start(config['DISCORD_KEY'])

    asyncio.run(main())
