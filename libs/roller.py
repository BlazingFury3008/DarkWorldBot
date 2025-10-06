from random import randint

def roll_dice(pool: int, spec: bool, difficulty: int):
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
    indexed_rolls.sort(key=lambda x: x[1])  # sort by roll value ascending

    successes_idx = []
    total_successes = 0

    # Count successes (10 with spec counts as 2)
    for i, val in indexed_rolls:
        if val == 1:
            continue
        if val == 10 and spec:
            total_successes += 2
            successes_idx.append(i)
        elif val >= difficulty:
            total_successes += 1
            successes_idx.append(i)

    # Cancel successes with 1's
    ones_idx = [i for i, v in indexed_rolls if v == 1]
    to_cancel = successes_idx[:len(ones_idx)]
    final_suxx = max(0, total_successes - len(ones_idx))
    botch = total_successes == 0 and len(ones_idx) > 0

    struck = []
    italic = []
    normal = []
    crit = []

    for i, val in indexed_rolls:
        if i in ones_idx or i in to_cancel:
            struck.append(f"~~{val}~~")
        elif val < difficulty:
            italic.append(f"*{val}*")
        elif val == 10 and spec:
            crit.append(f"**{val}**")
        else:
            normal.append(f"{val}")

    formatted = struck + italic + normal + crit

    return formatted, final_suxx, botch
