import discord
from discord.utils import get
import logging
from libs.character import *

logger = logging.getLogger(__name__)

async def assign_roles_for_character(member: discord.Member, char: Character):
    """
    Assign clan, sect, and ranking roles to a Discord member based on their character.
    Clears only previously relevant roles (sect, ranking, clan), then reapplies.
    """
    guild = member.guild
    if not guild:
        logger.warning(f"[ROLES] No guild found for {member}")
        return

    # -------------------------------------
    # Helper to find a role by name (case-insensitive)
    # -------------------------------------
    def find_role(name: str):
        if not name:
            return None
        role = get(guild.roles, name=name)
        if role:
            return role
        return next((r for r in guild.roles if r.name.lower() == name.lower()), None)

    # =========================
    # RESOLVE ROLES TO ASSIGN
    # =========================
    # Ranking
    ranking_role = None
    match (char.ranking or "").strip():
        case "Mortal":
            ranking_role = find_role("Mortal")
        case "Revenant":
            ranking_role = find_role("Revenant")
        case "Ghoul":
            ranking_role = find_role("Ghoul")
        case "Fledgling":
            ranking_role = find_role("Fledgling")
        case "Neonate":
            ranking_role = find_role("Neonate")
        case "Ancilla":
            ranking_role = find_role("Ancilla")
        case "Elder":
            ranking_role = find_role("Elder")
        case _:
            ranking_role = None

    # Clan
    clan_role = None
    match (char.clan or "").strip():
        case "Banu Haqim" | "Banu Haqim Antitribu" | "Banu Haqim Sorcerers" | "Banu Haqim Viziers" | "Banu Haqim Vassal":
            clan_role = find_role("Assamite")
        case "Baali":
            clan_role = find_role("Baali")
        case "Brujah" | "Brujah Antitribu" | "Brujah Vassal":
            clan_role = find_role("Brujah")
        case "Caitiff" | "Blood Brothers" | "Panders":
            clan_role = find_role("Caitiff/Pander")
        case "Cappadocians":
            clan_role = find_role("Cappadocian")
        case "Daughters of Cacophony":
            clan_role = find_role("Daughters of Cacophony")
        case "Followers of Set" | "Serpents of the Light" | "(Followers of Set) Daitya" | "(Followers of Set) Tlacique" | "(Followers of Set) Warrior Setites" | "(Followers of Set) Warriors of Glycon" | "(Followers of Set) Witches of Echidna" | "Followers of Set Vassal":
            clan_role = find_role("Follower of Set")
        case "Gangrel" | "City Gangrel" | "Country Gangrel" | "(Gangrel) Mariners" | "Gangrel Vassal":
            clan_role = find_role("Gangrel")
        case "Gargoyles" | "(Gargoyles) Scout" | "(Gargoyles) Sentinel" | "(Gargoyles) Warriors":
            clan_role = find_role("Gargoyles")
        case "Giovanni" | "Giovanni Vassal":
            clan_role = find_role("Giovanni")
        case "Harbingers of Skulls":
            clan_role = find_role("Harbinger of Skull")
        case "Kiasyd":
            clan_role = find_role("Kiasyd")
        case "Lasombra" | "(Lasombra) Angelis Ater" | "Lasombra Antitribu" | "Lasombra Vassal":
            clan_role = find_role("Lasombra")
        case "Malkavian" | "Malkavian Antitribu" | "(Malkavians) Dominate Malkavians" | "Malkavian Vassal":
            clan_role = find_role("Malkavian")
        case "Nagaraja":
            clan_role = find_role("Nagaraja")
        case "Nosferatu" | "Nosferatu Antitribu" | "Nosferatu Vassal":
            clan_role = find_role("Nosferatu")
        case "Ravnos" | "Ravnos Antitribu" | "(Ravnos) Brahman" | "Ravnos Vassal":
            clan_role = find_role("Ravnos")
        case "Salubri" | "Salubri Antitribu" | "(Salubri) Wu Zao":
            clan_role = find_role("Salubri")
        case "Samedi":
            clan_role = find_role("Samedi")
        case "Toreador" | "Toreador Antitribu" | "(Toreador) Nephilim" | "Toreador Vassal":
            clan_role = find_role("Toreador")
        case "Tremere" | "Tremere Antitribu" | "(Tremere) Telyavelic Tremere" | "Tremere Vassal":
            clan_role = find_role("Tremere")
        case "True Brujah":
            clan_role = find_role("True Brujah")
        case "Tzimisce" | "(Tzimisce) Koldun" | "(Tzimisce) Old Clan Tzimisce" | "Tzimisce Vassal":
            clan_role = find_role("Tzimisce")
        case "Ventrue" | "Ventrue Antitribu" | "Ventrue Vassal":
            clan_role = find_role("Ventrue")
        case "Bratovich":
            clan_role = find_role("Bratovich")
        case "D'Habi":
            clan_role = find_role("D'Habi")
        case "Ducheski":
            clan_role = find_role("Ducheski")
        case "Enrathi":
            clan_role = find_role("Enrathi")
        case "Grimaldi":
            clan_role = find_role("Grimaldi")
        case "Kairouan Brotherhood":
            clan_role = find_role("Kairouan")
        case "Obertus" | "Obertus (Narov)":
            clan_role = find_role("Obertus")
        case "Oprichniki":
            clan_role = find_role("Oprichniki")
        case "Rafastio":
            clan_role = find_role("Rafastio")
        case "Rossellini":
            clan_role = find_role("Rossellini")
        case "Servants of Anushin-Rawan":
            clan_role = find_role("Serv. Anushin-Rawan")
        case "Zantosa":
            clan_role = find_role("Zantosa")
        case _:
            clan_role = find_role(char.clan)

    # Sect
    sect_role = None
    match (char.sect or "").strip():
        case "Camarilla":
            sect_role = find_role("Camarilla")
        case "Sabbat":
            sect_role = find_role("Sabbat")
        case "Anarch":
            sect_role = find_role("Anarch")
        case "Autarki":
            sect_role = find_role("Autarki")
        case _:
            sect_role = None

    # =========================
    # REMOVE OLD RELEVANT ROLES
    # =========================
    resolved_roles = {r for r in [ranking_role, clan_role, sect_role] if r}

    # Build a set of all possible relevant roles that might currently be assigned
    current_relevant_roles = [r for r in member.roles if r in resolved_roles or r.name in [rr.name for rr in resolved_roles]]
    if current_relevant_roles:
        try:
            await member.remove_roles(*current_relevant_roles, reason="Updating character roles")
            logger.info(f"[ROLES] Removed old roles {[r.name for r in current_relevant_roles]} from {member}")
        except discord.Forbidden:
            logger.warning(f"[ROLES] Missing permissions to remove roles for {member}")
        except discord.HTTPException as e:
            logger.error(f"[ROLES] Failed to remove roles for {member}: {e}")

    # =========================
    # APPLY NEW ROLES
    # =========================
    if resolved_roles:
        try:
            await member.add_roles(*resolved_roles, reason="Character role assignment")
            logger.info(f"[ROLES] Assigned {[r.name for r in resolved_roles]} to {member}")
        except discord.Forbidden:
            logger.warning(f"[ROLES] Missing permissions to update roles for {member}")
        except discord.HTTPException as e:
            logger.error(f"[ROLES] Failed to update roles for {member}: {e}")
