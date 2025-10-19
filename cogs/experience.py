import logging
from datetime import datetime
from typing import List, Dict, Optional

import discord
from discord.ext import commands
from discord import app_commands

from libs.character import Character
from libs.help import requires_st_role  # ST/Admin checker

logger = logging.getLogger(__name__)


# -----------------------------
# Helpers
# -----------------------------

def _fmt_ddmmyyyy(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")


def _page_color_for(entries: List[Dict]) -> discord.Color:
    net = 0.0
    for e in entries:
        try:
            net += float(e.get("delta", 0) or 0)
        except Exception:
            pass
    if net > 0:
        return discord.Color.green()
    if net < 0:
        return discord.Color.red()
    return discord.Color.light_grey()


# -----------------------------
# Pagination View
# -----------------------------

class XPLogView(discord.ui.View):
    def __init__(
        self,
        interaction_user: discord.User | discord.Member,
        char_name: str,
        curr_xp: str | int,
        total_xp: str | int,
        entries: List[Dict],
        per_page: int = 25,
        start_oldest_first: bool = True,
        timeout: int = 180,
        allow_delete: bool = False
    ):
        super().__init__(timeout=timeout)
        self.owner = interaction_user
        self.char_name = char_name
        self.curr_xp = curr_xp
        self.total_xp = total_xp
        self.entries_all = entries[:]  # keep original order from sheet
        self.per_page = per_page
        self.oldest_first = start_oldest_first
        self.allow_delete = allow_delete

        self.page_index = 0
        self._rebuild_pages()

        self.prev_button.disabled = (self.page_index == 0)
        self.next_button.disabled = (self.page_index >= len(self.pages) - 1)

        self._rebuild_jump_options()
        self._set_sort_label()

        if not allow_delete:
            self.remove_item(self.delete_button)

    def _sorted_entries(self) -> List[Dict]:
        # Do NOT sort by date; oldest->newest = original order; newest->oldest = reversed
        return self.entries_all if self.oldest_first else list(reversed(self.entries_all))

    def _chunks(self, data, size): return [data[i:i + size] for i in range(0, len(data), size)]

    def _build_embed_for_page(self, page_entries, page_number, total_pages):
        color = _page_color_for(page_entries)
        embed = discord.Embed(
            title=f"Experience Log — {self.char_name}",
            description=f"**Current XP:** {self.curr_xp}\n**Total XP:** {self.total_xp}",
            color=color
        )
        embed.set_footer(text=f"Page {page_number}/{total_pages} • {'Oldest→Newest' if self.oldest_first else 'Newest→Oldest'}")

        header = "Date        | Δ     | Reason"
        sep = "-" * len(header)
        lines = [header, sep]

        for e in page_entries:
            date = e.get("date") or "---"
            delta = e.get("delta", 0)
            try:
                delta_str = f"{float(delta):+g}"
            except:
                delta_str = str(delta)
            reason = (e.get("comment") or "").replace("\n", " ")
            if len(reason) > 50:
                reason = reason[:47] + "..."
            lines.append(f"{date:<11} | {delta_str:<5} | {reason}")

        if not page_entries:
            lines.append("(no entries on this page)")

        embed.add_field(name="Log Entries", value="```" + "\n".join(lines) + "```", inline=False)
        return embed

    def _rebuild_pages(self):
        chunks = self._chunks(self._sorted_entries(), self.per_page)
        total_pages = max(1, len(chunks))
        self.pages = [
            self._build_embed_for_page(chunks[i] if chunks else [], i + 1, total_pages)
            for i in range(total_pages)
        ]
        if self.page_index >= len(self.pages):
            self.page_index = max(0, len(self.pages) - 1)

    def _rebuild_jump_options(self):
        total = len(self.pages) if self.pages else 1
        start = max(1, self.page_index + 1 - 12)
        end = min(total, start + 24)
        start = max(1, end - 24)

        self.page_select.options.clear()
        for i in range(start, end + 1):
            self.page_select.add_option(
                label=f"Page {i}/{total}",
                value=str(i - 1),
                default=(i - 1 == self.page_index)
            )
        self.page_select.disabled = (total <= 1)

    def _set_sort_label(self):
        self.sort_button.label = "Sort: Oldest→Newest" if self.oldest_first else "Sort: Newest→Oldest"

    async def _refresh_message(self, interaction):
        embed = self.pages[self.page_index]
        self.prev_button.disabled = (self.page_index == 0)
        self.next_button.disabled = (self.page_index >= len(self.pages) - 1)
        self._rebuild_jump_options()
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("This is not your menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction, button):
        if self.page_index > 0:
            self.page_index -= 1
        await self._refresh_message(interaction)

    @discord.ui.button(label="Sort: Oldest→Newest", style=discord.ButtonStyle.primary)
    async def sort_button(self, interaction, button):
        self.oldest_first = not self.oldest_first
        mirrored = (len(self.pages) - 1 - self.page_index) if self.pages else 0
        self._rebuild_pages()
        self.page_index = mirrored if 0 <= mirrored < len(self.pages) else 0
        self._set_sort_label()
        await self._refresh_message(interaction)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction, button):
        if self.page_index < len(self.pages) - 1:
            self.page_index += 1
        await self._refresh_message(interaction)

    @discord.ui.select(placeholder="Jump to page…", options=[])
    async def page_select(self, interaction, select):
        try:
            idx = int(select.values[0])
        except:
            idx = self.page_index
        self.page_index = max(0, min(idx, len(self.pages) - 1))
        await self._refresh_message(interaction)

    @discord.ui.button(label="🗑 Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            check = requires_st_role().predicate
            if not await check(interaction):
                return await interaction.response.send_message("Only the original user or a Storyteller can delete this.", ephemeral=True)
        try:
            await interaction.message.delete()
        except Exception as e:
            await interaction.response.send_message(f"Failed to delete: {e}", ephemeral=True)


# -----------------------------
# Cog: Experience Commands
# -----------------------------

class EXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered EXP Commands")

    xp = app_commands.Group(name="experience", description="All Experience related commands")

    # ---------- LOG VIEWER ----------

    @xp.command(name="log", description="View your or another player's XP log.")
    @app_commands.describe(
        user="(Optional) View another player's log (ST only)",
        share="Post publicly instead of privately"
    )
    async def xp_log(self, interaction: discord.Interaction, user: Optional[discord.User] = None, share: bool = False):
        await interaction.response.defer(ephemeral=not share)

        viewer = interaction.user
        target = user or viewer

        try:
            if target != viewer:
                st_check = requires_st_role().predicate
                if not await st_check(interaction):
                    return

            char = Character.load_for_user(str(target.id))
            if not char:
                msg = f"{target.display_name} has no character." if target != viewer else "You have no character."
                return await interaction.followup.send(msg, ephemeral=not share)

            entries = char.xp_log or []
            if not entries:
                embed = discord.Embed(
                    title=f"Experience Log — {char.name}",
                    description="No XP log entries found.",
                    color=discord.Color.light_grey()
                )
                embed.set_footer(text="Page 1/1 • Oldest→Newest")
                return await interaction.followup.send(embed=embed, ephemeral=not share)

            view = XPLogView(
                interaction_user=viewer,
                char_name=char.name,
                curr_xp=char.curr_xp,
                total_xp=char.total_xp,
                entries=entries,
                per_page=25,
                allow_delete=share
            )

            await interaction.followup.send(embed=view.pages[0], view=view, ephemeral=not share)

        except Exception as e:
            logger.exception(f"[XP LOG] Error: {e}")
            await interaction.followup.send("An error occurred while retrieving XP logs.", ephemeral=not share)

    # ---------- XP COLLECT: +1 per day with block grouping ----------

    @xp.command(name="collect", description="Collect your daily +1 XP.")
    @app_commands.describe(override_cooldown="ST only: bypass daily cooldown.")
    async def xp_collect(self, interaction: discord.Interaction, override_cooldown: bool = False):
        # ephemeral; it's a personal action
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        username = user.name

        try:
            char = Character.load_for_user(str(user.id))
            if not char:
                return await interaction.followup.send("You don't have a character yet. Use `/character init` first.", ephemeral=True)

            # ST bypass check
            can_bypass = False
            if override_cooldown:
                st_check = requires_st_role().predicate
                can_bypass = await st_check(interaction)

            today = _fmt_ddmmyyyy(datetime.utcnow())

            # Find last positive entry by this user to enforce daily cooldown
            last_user_gain_date = None
            if char.xp_log:
                for e in reversed(char.xp_log):
                    try:
                        d = float(e.get("delta", 0) or 0)
                    except Exception:
                        d = 0.0
                    if d > 0 and (e.get("storyteller") or "") == username:
                        # date in comment is our authoritative range
                        comment = (e.get("comment") or "").strip()
                        if " - " in comment:
                            last_user_gain_date = comment.split(" - ", 1)[1].strip()
                        else:
                            last_user_gain_date = comment or e.get("date") or today
                        break

            if (not can_bypass) and last_user_gain_date == today:
                return await interaction.followup.send("You've already collected XP today. Come back tomorrow!", ephemeral=True)

            # Determine whether to start a new block or extend the last one
            new_entry_needed = True
            if char.xp_log:
                last = char.xp_log[-1]
                try:
                    last_delta = float(last.get("delta", 0) or 0)
                except Exception:
                    last_delta = 0.0

                # If last entry was a gain (>=0), extend block; if a spend (<0), create new block
                if last_delta >= 0:
                    # Extend last block if it's a user collection line (storyteller=username) OR any positive gain block
                    new_entry_needed = False

            if new_entry_needed or not char.xp_log:
                # new block starting today
                entry = {
                    "date": today,
                    "delta": 1.0,
                    "comment": today,
                    "storyteller": username,
                }
                char.xp_log.append(entry)
            else:
                # extend last block
                last = char.xp_log[-1]
                # Update delta +1
                try:
                    last["delta"] = float(last.get("delta", 0) or 0) + 1.0
                except Exception:
                    last["delta"] = 1.0

                # Update comment range "first - today"
                prev_comment = (last.get("comment") or "").strip()
                if " - " in prev_comment:
                    first_day = prev_comment.split(" - ", 1)[0].strip()
                else:
                    first_day = prev_comment if prev_comment else today
                last["comment"] = f"{first_day} - {today}"
                # Ensure storyteller is set (username)
                last["storyteller"] = username

            # Sync to Google Sheets & save
            char.write_xp_log(interaction)
            char.save_parsed()
            await interaction.followup.send("Daily XP collected (+1). Your log has been updated.", ephemeral=True)

        except Exception as e:
            logger.exception(f"[XP COLLECT] Error: {e}")
            await interaction.followup.send("An error occurred while collecting XP.", ephemeral=True)

    # ---------- XP GIVE: ST only, +/- amount with reason ----------

    @xp.command(name="give", description="Storyteller: give or remove XP from a player.")
    @requires_st_role()
    @app_commands.describe(
        user="Player to modify.",
        amount="Amount to add (positive) or remove (negative).",
        reason="Reason to include in the log."
    )
    async def xp_give(self, interaction: discord.Interaction, user: discord.User, amount: float, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        st_user = interaction.user
        st_name = st_user.name
        target_name = user.display_name

        try:
            char = Character.load_for_user(str(user.id))
            if not char:
                return await interaction.followup.send(f"{target_name} does not have a character.", ephemeral=True)

            today = _fmt_ddmmyyyy(datetime.utcnow())
            amt = float(amount)

            # If negative (spend), we log a new line (spend breaks blocks).
            # If positive, we create a new line (explicit ST award should be distinct from daily block).
            comment = reason or "Storyteller adjustment"

            new_entry = {
                "date": today,
                "delta": amt,
                "comment": comment if amt >= 0 else comment,  # same comment either way
                "storyteller": st_name,
            }
            char.xp_log.append(new_entry)

            # Sync to Google Sheets & save
            char.write_xp_log(interaction)
            char.save_parsed()

            sign = "+" if amt >= 0 else ""
            await interaction.followup.send(
                f"Gave **{sign}{amt:g} XP** to **{target_name}**. Log updated.",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"[XP GIVE] Error: {e}")
            await interaction.followup.send("An error occurred while adjusting XP.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(EXP(bot))
