from discord.ext import commands

class DTA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered DTA")