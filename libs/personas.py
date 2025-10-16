import logging
import re
from types import SimpleNamespace

from libs.database_loader import execute_query
from libs.character import Character

logger = logging.getLogger(__name__)

# ============================================================
# Header Utilities
# ============================================================

def generate_default_header(char: Character) -> str:
    """Generate a default header using basic fields from the character."""
    return "{char.name} | {char.clan} | {char.sect}"


def _to_namespace(obj):
    """
    Recursively convert dicts/lists to SimpleNamespace so you can use
    `char.name` instead of char['name'] in headers.
    """
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_namespace(v) for k, v in obj.items()})
    elif isinstance(obj, list):
        return [_to_namespace(x) for x in obj]
    return obj


# Matches { ... } blocks for evaluation
_EXPR_BLOCK = re.compile(r"\{([^{}]+)\}")

def parse_header(header_str: str, char: "Character") -> str:
    """
    Parse and evaluate a dynamic header string using Character data.

    Any text inside `{ ... }` is treated as a Python expression evaluated
    with `char` in scope. Everything else remains literal text.

    Examples:
        "{char.name} | {char.clan} | {char.sect}"
        "{char.name} {next((x.value for x in char.backgrounds if x.name == 'Clan Status'), '0')} {char.clan} Status"
        "Name: {char.name}, Blood: {char.curr_blood}/{char.max_blood}"
        "{1 + 1}" -> "2"
    """
    # Convert Character to dict (if dataclass) and then to attr-namespace
    if hasattr(char, "__dict__"):
        char_dict = char.__dict__
    elif isinstance(char, dict):
        char_dict = char
    else:
        raise TypeError("Character must be a dataclass or dict-like object.")

    char_ns = _to_namespace(char_dict)

    # Restricted evaluation environment
    safe_globals = {
        "__builtins__": {
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "next": next,
            "any": any,
            "all": all,
            "sorted": sorted,
            "str": str,
            "int": int,
            "float": float,
            "round": round,
        }
    }
    safe_locals = {"char": char_ns}

    def repl(match: re.Match) -> str:
        expr = match.group(1).strip()
        try:
            value = eval(expr, safe_globals, safe_locals)
            return str(value)
        except Exception as e:
            logger.warning(f"Failed to evaluate header expression '{expr}': {e}")
            return f"[Error:{expr}]"

    return _EXPR_BLOCK.sub(repl, header_str)


# ============================================================
# Template Rendering / Validation (Fallback for {name}, {clan}, etc.)
# ============================================================

def render_custom_header(template: str, data: dict) -> str:
    """
    Render a simple header using .format() placeholder substitution.
    This is a simpler fallback for users who just want {name}, {clan}, etc.
    """
    safe_data = {k: str(v) for k, v in data.items()}
    try:
        return template.format(**safe_data)
    except KeyError as e:
        missing = str(e).strip("'")
        logger.warning(f"Missing placeholder {missing} in header template.")
        return template.replace(f"{{{missing}}}", "")


def validate_header_template(template: str, character_data: dict) -> tuple[bool, str]:
    """
    Validate a header template by attempting to render it with the given character data.
    Returns (is_valid, rendered_or_error).
    """
    try:
        rendered = render_custom_header(template, character_data)
        return True, rendered
    except KeyError as e:
        missing = str(e).strip("'")
        return False, f"Missing field: {missing}"
    except Exception as e:
        logger.error(f"Header validation error: {type(e).__name__} - {e}")
        return False, str(e)


# ============================================================
# Persona Image
# ============================================================

def get_persona_image(uuid: str) -> bytes | None:
    """Fetch stored image blob for a persona."""
    row = execute_query(
        "SELECT image FROM persona WHERE uuid = ?",
        (uuid,),
        fetchone=True,
    )
    return row[0] if row and row[0] else None
