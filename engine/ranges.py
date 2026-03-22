"""
Preflop range charts for Texas Hold'em.

Provides a 13×13 grid of canonical starting hands with equity values
and position-based action recommendations (raise/call/fold).
"""

from .equity import PREFLOP_EQUITY

RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

# Position-based minimum equity thresholds for opening ranges.
# Format: {position: (raise_threshold, call_threshold)}
# Hands above raise_threshold → raise. Above call_threshold → call. Below → fold.
POSITION_THRESHOLDS = {
    "UTG":    (62, 55),
    "UTG+1":  (60, 53),
    "MP":     (58, 51),
    "MP+1":   (56, 50),
    "MP+2":   (55, 49),
    "HJ":     (53, 47),
    "CO":     (50, 44),
    "BTN":    (46, 40),
    "BTN/SB": (50, 44),
    "SB":     (52, 46),
    "BB":     (40, 35),  # BB gets to see flop cheap
}


def hand_key(row: int, col: int) -> str:
    """
    Convert grid position to canonical hand name.
    Diagonal = pair. Above diagonal (col > row) = suited. Below = offsuit.
    """
    r1 = RANKS[row]
    r2 = RANKS[col]
    if row == col:
        return f"{r1}{r2}"         # Pair: AA, KK, etc.
    elif col > row:
        return f"{r1}{r2}s"        # Suited: AKs, AQs, etc.
    else:
        return f"{r2}{r1}o"        # Offsuit: AKo, AQo, etc.


def get_range_grid(position: str = "BTN") -> list:
    """
    Build a 13×13 grid for the given position.

    Returns list of 13 rows, each row is a list of 13 cells:
    {hand, equity, action, row, col}

    action is "raise", "call", or "fold" based on position thresholds.
    """
    thresholds = POSITION_THRESHOLDS.get(position, (50, 44))
    raise_thresh, call_thresh = thresholds

    grid = []
    for row in range(13):
        cells = []
        for col in range(13):
            hand = hand_key(row, col)
            equity = PREFLOP_EQUITY.get(hand, 35.0)

            if equity >= raise_thresh:
                action = "raise"
            elif equity >= call_thresh:
                action = "call"
            else:
                action = "fold"

            cells.append({
                "hand": hand,
                "equity": equity,
                "action": action,
                "row": row,
                "col": col,
            })
        grid.append(cells)
    return grid


def get_all_positions() -> list:
    """Return list of all position names in order."""
    return list(POSITION_THRESHOLDS.keys())


def hand_to_grid_pos(rank1: str, rank2: str, suited: bool) -> tuple:
    """
    Convert two rank characters and suited flag to (row, col) grid position.
    Returns (row, col) or None if invalid.
    """
    if rank1 not in RANKS or rank2 not in RANKS:
        return None
    r1 = RANKS.index(rank1)
    r2 = RANKS.index(rank2)

    if r1 == r2:
        return (r1, r2)  # Pair
    elif suited:
        # Suited goes above diagonal: higher rank = row, lower = col
        return (min(r1, r2), max(r1, r2))
    else:
        # Offsuit goes below diagonal: higher rank = col, lower = row
        return (max(r1, r2), min(r1, r2))
