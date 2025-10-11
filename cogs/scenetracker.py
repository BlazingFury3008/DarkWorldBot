import discord
from discord.ext import commands
from discord import app_commands
import re
from data import get_db
from sqlalchemy import Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Scene(Base):
    __tablename__ = 'scene'

    sceneID = Column(Integer, primary_key=True, autoincrement=True)
    sceneName = Column(String(255), nullable=False)
    start = Column(String(255), nullable=False)  # stores message link
    end = Column(String(255), default="")        # stores message link if ended
    users = Column(JSON)


class SceneTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered SceneTracker")

    scene_group = app_commands.Group(name="scene", description="All commands for scenes")
