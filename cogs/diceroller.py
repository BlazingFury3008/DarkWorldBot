from discord.ext import commands

class Diceroller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered Diceroller")