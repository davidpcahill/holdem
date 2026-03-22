"""
Shared constants used across the engine modules.
"""

# Position bonuses for AI decisions (aggressive scale, ±8 range).
# Later position = more aggressive play.
AI_POSITION_BONUS = {
    "BTN": 8, "CO": 5, "HJ": 2, "BTN/SB": 3,
    "SB": -2, "BB": 0, "UTG": -5, "UTG+1": -3,
    "MP": 0, "MP+1": 1, "MP+2": 2,
}

# Position modifiers for advisor display (moderate scale, ±5 range).
# Used to show positional advantage to the human player.
ADVISOR_POSITION_MODIFIER = {
    "BTN": 5, "CO": 3, "HJ": 1, "BTN/SB": 2,
    "SB": -2, "BB": 0, "UTG": -4, "UTG+1": -3,
    "MP": 0, "MP+1": 1,
}
