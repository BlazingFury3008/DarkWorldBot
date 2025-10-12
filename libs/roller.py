import re
import ast
import discord
import logging
from random import randint
from typing import Tuple, List
from libs.macro import *

from dotenv import dotenv_values
config = dotenv_values(".env")


logger = logging.getLogger(__name__)


# ---------------------------
# Dice Roller
# ---------------------------
def roll_dice(pool: int, spec: bool, difficulty: int, return_ones: bool = False):
    """
    V20 dice roller with proper formatting and sorted results.
    - ~~strike~~: 1's and cancelled successes
    - *italic*: failures
    - normal: regular successes
    - **bold**: 10 with spec (crit)

    Order: sorted ascending, grouped STRIKE → ITALIC → NORMAL → CRIT
    """
    rolls = [randint(1, 10) for _ in range(pool)]
    indexed_rolls = list(enumerate(rolls))
    indexed_rolls.sort(key=lambda x: x[1])  # sort ascending by value

    successes_idx = []
    total_successes = 0

    # Count successes
    for i, val in indexed_rolls:
        if val == 1:
            continue
        if val == 10 and spec:
            total_successes += 2
            successes_idx.append((i, val))
        elif val >= difficulty:
            total_successes += 1
            successes_idx.append((i, val))

    # Cancel lowest successes with 1's
    ones_idx = [i for i, v in indexed_rolls if v == 1]
    successes_idx.sort(key=lambda x: x[1])  # cancel lowest successes first
    to_cancel = [idx for idx, _ in successes_idx[:len(ones_idx)]]

    final_suxx = max(0, total_successes - len(ones_idx))
    botch = total_successes == 0 and len(ones_idx) > 0

    struck, italic, normal, crit = [], [], [], []

    for i, val in indexed_rolls:
        if i in ones_idx or i in to_cancel:
            struck.append(f"~~{val}~~")
        elif val < difficulty:
            italic.append(f"*{val}*")
        elif val == 10 and spec:
            crit.append(f"**{val}**")
        else:
            normal.append(f"{val}")

    formatted = struck + italic

    # Add separator between failed/canceled vs successes if both exist
    if formatted and (normal or crit):
        formatted.append("|")

    formatted += normal + crit

    if return_ones:
        return formatted, final_suxx, botch, len(ones_idx)
    return formatted, final_suxx, botch


# ---------------------------
# Utility: Handle Willpower Token
# ---------------------------
def process_willpower(roll_str: str, char: "Character") -> Tuple[str, bool]:
    """Remove +WP from roll_str and spend Willpower if available"""
    if "+WP" not in roll_str.upper():
        return roll_str, False

    if char.curr_willpower < 1:
        raise ValueError(f"{char.name} does not have enough Willpower to spend!")

    cleaned = (
        roll_str.replace("+WP", "")
        .replace("+wp", "")
        .replace("+Wp", "")
        .replace("+wP", "")
        .strip()
    )

    char.curr_willpower -= 1
    char.save_parsed()
    logger.debug(
        f"[ROLL] Willpower spent for {char.name}. Remaining: {char.curr_willpower}"
    )
    return cleaned, True


# ---------------------------
# Utility: Resolve Dice Pool
# ---------------------------
def resolve_dice_pool(roll_str: str, char: Character) -> Tuple[int, bool, List[str]]:
    """Determine dice pool from either macro name or raw expression.

    If roll_str matches a macro name, resolve using that macro expression.
    Otherwise, treat roll_str as a direct dice expression.
    """
    macros = get_character_macros(char.uuid)
    if roll_str in macros:
        return sum_macro(macros[roll_str], char=char)

    return sum_macro(roll_str, char=char)


# ---------------------------
# Utility: Format String
# ---------------------------
def format_roll_expression(expr: str) -> str:
    """
    Convert a raw roll expression into a more human-readable string.
    Example:
        Dexterity+Melee[Swords]+4 → "Rolling Dexterity, Melee (Swords) + 4 dice"
        Strength-2               → "Rolling Strength - 2 dice"
    """
    if not expr or not isinstance(expr, str):
        return "Rolling (invalid expression)"

    # Split tokens by + or - but keep the sign
    tokens = re.findall(r"[+-]?\s*[^+-]+", expr)
    trait_parts = []
    dice_mods = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # Extract sign
        sign = "+"
        if token[0] in "+-":
            sign = token[0]
            token = token[1:].strip()

        # Numbers → dice modifiers
        if re.fullmatch(r"\d+", token):
            mod = f"{sign} {token} dice"
            dice_mods.append(mod)
            continue

        # Traits with optional spec
        m = re.match(r"([A-Za-z\s]+)(?:\[([^\]]+)\])?", token)
        if m:
            name = m.group(1).strip()
            spec = m.group(2)
            if spec:
                trait_parts.append(f"{name} ({spec})")
            else:
                trait_parts.append(name)
            continue

    trait_str = ", ".join(trait_parts) if trait_parts else ""
    mods_str = " ".join(dice_mods)

    if trait_str and mods_str:
        return f"Rolling {trait_str} {mods_str}"
    elif trait_str:
        return f"Rolling {trait_str}"
    elif mods_str:
        return f"Rolling {mods_str}"
    else:
        return "Rolling (empty expression)"


# ---------------------------
# Utility: Build Result Embed
# ---------------------------
def build_roll_embed(
    
    interaction: discord.Interaction,
    total_pool: int,
    difficulty: int,
    successes: int,
    botch: bool,
    formatted: List[str],
    specs_applied: List[str],
    original_str: str,
    comment: str,
    willpower_used: bool,
) -> discord.Embed:
    """Create the nicely formatted roll result embed"""
    color = discord.Color.dark_red() if successes == 0 else discord.Color.green()
    embed = discord.Embed(
        title=f"{interaction.user.display_name or interaction.user.name}: Pool {total_pool}, Diff {difficulty}",
        color=color,
    )

    result_title = f"{successes} Success{'es' if successes != 1 else ''}" if not botch else "BOTCH"
    embed.add_field(name=result_title, value=" ", inline=False)

    embed.add_field(name="Dice", value=" ".join(formatted), inline=True)
    embed.add_field(
        name="Specialties Applied",
        value=", ".join(specs_applied) if specs_applied else "None",
        inline=True,
    )

    footer_string = format_roll_expression(original_str)
    footer_value = f"-# {footer_string.strip()}"

    if willpower_used:
        footer_value += "; Willpower Used"
    if comment:
        footer_value += f"\n\n-# {comment}"

    embed.add_field(name="", value=footer_value, inline=False)
    return embed


# ---------------------------
# Utility: Botch Role Mention
# ---------------------------
async def handle_botch_mention(
    interaction: discord.Interaction, char_name: str
):
    """Mention storyteller roles on botch if configured"""
    try:
        roles_env = config.get("ROLES", "[]")
        try:
            role_names = ast.literal_eval(roles_env)
        except Exception:
            logger.warning("[ROLL] ROLES env variable invalid. Using empty list.")
            role_names = []

        if not role_names:
            return

        guild_roles = interaction.guild.roles
        mentionable_roles = [
            next((r for r in guild_roles if r.name.lower() == role_name.lower()), None)
            for role_name in role_names
        ]
        mentionable_roles = [r for r in mentionable_roles if r is not None]

        if mentionable_roles:
            mentions = " ".join([r.mention for r in mentionable_roles])
            await interaction.channel.send(f"BOTCH by {char_name} — {mentions}")

    except Exception as e:
        logger.exception(f"[ROLL] Error during botch mention: {e}")
