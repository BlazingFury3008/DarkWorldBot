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

    @scene_group.command(name="create", description="Create a new scene")
    async def create(self, interaction: discord.Interaction, name: str, players: str):
        await interaction.response.defer()

        player_mentions = players.split()
        try:
            player_ids = [int(re.findall(r'\d+', mention)[0]) for mention in player_mentions]
        except IndexError:
            await interaction.followup.send("Invalid player mention format.", ephemeral=True)
            return

        guild_member_ids = {member.id for member in interaction.guild.members}
        for pid in player_ids:
            if pid not in guild_member_ids:
                await interaction.followup.send(f"Player ID {pid} is not a valid guild member.", ephemeral=True)
                return

        mentions = " ".join([f"<@{pid}>" for pid in player_ids])
        initial_message = await interaction.followup.send(
            f"**Scene Created:** `{name}`\n**Players:** {mentions}"
        )

        start_link = f"https://discord.com/channels/{interaction.guild.id}/{interaction.channel.id}/{initial_message.id}"

        db = next(get_db())
        try:
            scene = Scene(
                sceneName=name,
                start=start_link,
                users=player_ids
            )
            db.add(scene)
            db.commit()
            db.refresh(scene)

            await initial_message.edit(
                content=f"```Scene #{scene.sceneID}\n{name}```\n**Players:** {mentions}"
            )
            await interaction.followup.send(f"Scene #{scene.sceneID} created.", ephemeral=True)
        except Exception as e:
            db.rollback()
            await interaction.followup.send(f"Failed to create scene: {e}", ephemeral=True)
            print(f"Error: {e}")
        finally:
            db.close()

    @scene_group.command(name="list", description="List all active scenes")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = next(get_db())
        try:
            scenes = db.query(Scene).all()
            if not scenes:
                await interaction.followup.send("There are no scenes.", ephemeral=True)
                return

            lines = []
            for s in scenes:
                user_mentions = " ".join([f"<@{uid}>" for uid in s.users])
                line = f"**#{s.sceneID}:** [`{s.sceneName}`]({s.start}) — {user_mentions}"
                if s.end:
                    line += f"\nEnded: [View End Message]({s.end})"
                lines.append(line)

            await interaction.followup.send("\n\n".join(lines), ephemeral=True)
        except Exception as e:
            print(f"Error listing scenes: {e}")
            await interaction.followup.send("Could not list scenes.", ephemeral=True)
        finally:
            db.close()

    @scene_group.command(name="end", description="End a scene by its ID")
    async def end(self, interaction: discord.Interaction, scene_id: int):
        await interaction.response.defer(ephemeral=True)
        db = next(get_db())
        try:
            scene = db.query(Scene).filter(Scene.sceneID == scene_id).first()

            if not scene:
                await interaction.followup.send(f"No scene found with ID #{scene_id}.", ephemeral=True)
                return

            if scene.end:
                await interaction.followup.send(f"Scene #{scene_id} has already ended.", ephemeral=True)
                return

            if interaction.user.id not in scene.users:
                await interaction.followup.send("You are not a participant in this scene.", ephemeral=True)
                return

            end_message = await interaction.followup.send(f"Scene #{scene.sceneID} has been ended.")
            end_link = f"https://discord.com/channels/{interaction.guild.id}/{interaction.channel.id}/{end_message.id}"
            scene.end = end_link
            db.commit()

        except Exception as e:
            db.rollback()
            await interaction.followup.send("Failed to end the scene.", ephemeral=True)
            print(f"Error ending scene: {e}")
        finally:
            db.close()

    @scene_group.command(name="add", description="Add someone to a scene by ID")
    async def add(self, interaction: discord.Interaction, scene_id: int, new_player: discord.Member):
        await interaction.response.defer(ephemeral=True)
        db = next(get_db())
        try:
            scene = db.query(Scene).filter(Scene.sceneID == scene_id).first()

            if not scene:
                await interaction.followup.send(f"Scene #{scene_id} not found.", ephemeral=True)
                return

            if interaction.user.id not in scene.users:
                await interaction.followup.send("You are not a participant in this scene.", ephemeral=True)
                return

            if new_player.id in scene.users:
                await interaction.followup.send(f"{new_player.mention} is already in the scene.", ephemeral=True)
                return

            scene.users.append(new_player.id)
            db.commit()

            await interaction.followup.send(f"{new_player.mention} added to Scene #{scene.sceneID}.", ephemeral=True)
        except Exception as e:
            db.rollback()
            await interaction.followup.send("Failed to add user to scene.", ephemeral=True)
            print(f"Error: {e}")
        finally:
            db.close()
