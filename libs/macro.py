import re
from typing import Tuple, List, Union, Dict
from libs.character import *

# Pattern for individual tokens:
# - NAME or NAME[Spec]
# - number (e.g., 4)
TOKEN_PATTERN = re.compile(
    r"""^(
        [A-Za-z_][A-Za-z0-9_]*      # Base name
        (\[[^\[\]]+\])?            # Optional [Specialization]
        |
        \d+                        # or pure number
    )$""",
    re.VERBOSE,
)


# ------------------------------
# Validate Expression Only
# ------------------------------
def validate_expr(expr: str) -> Tuple[bool, str]:
    """
    Validate the right-hand side of a macro expression.
    Supports tokens like STR, STR[Melee], numbers, and '+' or '-' operators.
    """
    if not isinstance(expr, str):
        return False, "Expression must be a string."

    expr = expr.strip()
    if not expr:
        return False, "Expression cannot be empty."

    # Split while keeping operators
    parts = re.split(r"([+-])", expr)
    tokens = [p.strip() for p in parts if p.strip()]

    if not tokens:
        return False, "Expression must contain at least one token."

    # Expression must alternate between token and operator
    # i.e., token (+|-) token (+|-) token ...
    if len(tokens) % 2 == 0:
        return False, "Expression has an invalid token/operator sequence."

    # Check tokens in even positions (0,2,4...)
    for i in range(0, len(tokens), 2):
        t = tokens[i]
        if not TOKEN_PATTERN.match(t):
            return False, f"Invalid token in expression: '{t}'"

    # Check operators in odd positions (+ or -)
    for i in range(1, len(tokens), 2):
        if tokens[i] not in {"+", "-"}:
            return False, f"Invalid operator '{tokens[i]}'"

    return True, ""


# ------------------------------
# Validate Full Macro
# ------------------------------
def validate_macro(macro: str) -> Tuple[bool, str]:
    """
    Validate a macro string of the format: NAME=VAL+VAL[SPEC]-4...
    """
    if not isinstance(macro, str):
        return False, "Macro must be a string."

    if "=" not in macro:
        return False, "Macro must contain '=' separating name and expression."

    parts = macro.split("=", 1)
    if len(parts) != 2:
        return False, "Macro must contain exactly one '='."

    name, expr = parts
    name = name.strip()
    expr = expr.strip()

    if not name:
        return False, "Macro must have a name before '='."

    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return False, f"Invalid macro name: '{name}'."

    valid_expr, expr_error = validate_expr(expr)
    if not valid_expr:
        return False, expr_error

    return True, ""


# ------------------------------
# Decompile Macro
# ------------------------------
def decompile_macro(macro: str) -> Tuple[str, List[Dict[str, Union[str, int, Dict[str, str]]]]]:
    """
    Decompile a validated Macro.
    Returns (name, list of tokens), where each token is a dict:
        {
          "sign": 1 or -1,
          "value": int | str | {"name": "STR", "spec": "Melee"}
        }
    """
    is_valid, error = validate_macro(macro)
    if not is_valid:
        raise ValueError(f"Invalid macro format: {error}")

    name, expr = macro.split("=", 1)
    name = name.strip()
    expr = expr.strip()

    parts = re.split(r"([+-])", expr)
    tokens = [p.strip() for p in parts if p.strip()]

    output_tokens: List[Dict] = []
    sign = 1  # start with positive by default

    for t in tokens:
        if t in {"+", "-"}:
            sign = 1 if t == "+" else -1
            continue

        # Number
        if t.isdigit():
            output_tokens.append({"sign": sign, "value": int(t)})
            continue

        # With or without specialization
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(\[(.+)\])?$", t)
        if match:
            base = match.group(1)
            spec = match.group(3)
            if spec:
                output_tokens.append({"sign": sign, "value": {"name": base, "spec": spec}})
            else:
                output_tokens.append({"sign": sign, "value": base})
        else:
            raise ValueError(f"Failed to parse token: {t}")

    return name, output_tokens

def sum_macro(macro_str: str, char: Character) -> Tuple[int, bool]:
    """
    Sum the values in a macro string like:
      Dexterity+Melee[Swords]+Celerity-2

    Returns:
        (total_value: int, used_spec: bool)
    """
    if not macro_str or not isinstance(macro_str, str):
        return -1, False

    # Split on + and - but keep the sign in a separate group
    tokens = re.findall(r"[+-]?\s*[^+-]+", macro_str)
    total = 0
    used_spec = False

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # Extract sign
        sign = 1
        if token.startswith("+"):
            token = token[1:]
        elif token.startswith("-"):
            token = token[1:]
            sign = -1

        # Numbers
        if re.fullmatch(r"\d+", token):
            total += sign * int(token)
            continue

        # Trait names with optional spec
        match = re.match(r"([A-Za-z\s]+)(?:\[([^\]]+)\])?", token)
        if not match:
            return -1, False  # invalid token

        trait_name = match.group(1).strip()
        spec = match.group(2)

        value, found, spec_used = get_character_value(char, trait_name, spec)
        if not found:
            return -1, False

        total += sign * value
        if spec_used:
            used_spec = True

    return total, used_spec


def get_character_value(char: Character, trait_name: str, spec: str = None) -> Tuple[int, bool, bool]:
    """
    Search the character for the trait_name and optional spec.
    Returns: (value, found, used_spec)
    """
    trait_name_lower = trait_name.lower()

    def check_entry(entry):
        if entry["name"].lower() != trait_name_lower:
            return None
        if spec:
            entry_specs = entry.get("specs")
            if not entry_specs:
                return None
            specs_list = [s.strip().lower() for s in entry_specs.split(",")]
            if spec.lower() not in specs_list:
                return None
            return entry.get("value", 0), True  # used spec
        return entry.get("value", 0), False

    # 1. Attributes
    for entry in char.attributes:
        res = check_entry(entry)
        if res:
            return res[0], True, res[1]

    # 2. Abilities
    if hasattr(char, "abilities"):
        for category in char.abilities.values():
            for entry in category:
                res = check_entry(entry)
                if res:
                    return res[0], True, res[1]

    # 3. Disciplines
    for entry in char.disciplines:
        res = check_entry(entry)
        if res:
            return res[0], True, res[1]

    # 4. Backgrounds
    for entry in char.backgrounds:
        res = check_entry(entry)
        if res:
            return res[0], True, res[1]

    # 5. Virtues
    for entry in char.virtues:
        res = check_entry(entry)
        if res:
            return res[0], True, res[1]

    # 6. Magic Paths
    for entry in getattr(char, "magic_paths", []):
        res = check_entry(entry)
        if res:
            return res[0], True, res[1]

    return 0, False, False