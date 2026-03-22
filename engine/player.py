"""
Player model for Texas Hold'em.

Each Player tracks their identity, chip stack, hole cards, and per-hand state
(folded, all-in, current bet). Players can be human or AI-controlled.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from .deck import Card


class PlayerType(Enum):
    HUMAN = "human"
    AI = "ai"


class AIStyle(Enum):
    LOOSE_PASSIVE = "loose_passive"
    TIGHT_AGGRESSIVE = "tight_aggressive"
    GTO = "gto"
    RANDOM = "random"


# Default seat colors (CSS-compatible)
DEFAULT_COLORS = [
    "#E74C3C",  # Red
    "#3498DB",  # Blue
    "#2ECC71",  # Green
    "#F39C12",  # Orange
    "#9B59B6",  # Purple
    "#1ABC9C",  # Teal
    "#E67E22",  # Dark Orange
    "#34495E",  # Navy
    "#E91E63",  # Pink
    "#00BCD4",  # Cyan
]


class Player:
    """
    A poker player at the table.
    
    Tracks persistent state (name, bankroll, type) and per-hand state
    (hole cards, current bet, folded/all-in flags).
    """

    def __init__(
        self,
        seat: int,
        name: str,
        stack: int = 1000,
        player_type: PlayerType = PlayerType.HUMAN,
        ai_style: AIStyle = AIStyle.TIGHT_AGGRESSIVE,
        color: Optional[str] = None,
    ):
        # Identity (persistent across hands)
        self.seat = seat
        self.name = name
        self.stack = stack
        self.player_type = player_type
        self.ai_style = ai_style
        self.color = color or DEFAULT_COLORS[seat % len(DEFAULT_COLORS)]

        # Per-hand state (reset between hands)
        self.hole_cards: List[Card] = []
        self.is_folded = False
        self.is_all_in = False
        self.current_bet = 0          # Amount bet in the current STREET
        self.total_bet_this_hand = 0  # Total across all streets this hand
        self.has_acted = False        # Has acted this betting round
        self.is_sitting_out = False   # Sitting out (skip dealing)

        # Stats tracking (persistent, for AI opponent modeling)
        self.hands_played = 0
        self.hands_voluntarily_put_in = 0  # VPIP counter
        self.times_raised = 0
        self.times_called = 0
        self.times_folded = 0
        self.hands_won = 0
        self.total_winnings = 0           # Gross chips won (pot amounts)
        self.total_invested = 0           # Gross chips bet across all hands
        self.biggest_pot_won = 0
        self.starting_stack = stack       # For session P&L tracking
        self.times_went_to_showdown = 0   # Hands that reached showdown
        self.times_won_at_showdown = 0    # Hands won at showdown (not fold-wins)

    @property
    def is_human(self) -> bool:
        return self.player_type == PlayerType.HUMAN

    @property
    def is_ai(self) -> bool:
        return self.player_type == PlayerType.AI

    @property
    def is_active(self) -> bool:
        """Can still act in the current hand (not folded, not all-in, has chips)."""
        return not self.is_folded and not self.is_all_in and not self.is_sitting_out and self.stack > 0

    @property
    def is_in_hand(self) -> bool:
        """Still competing for the pot (not folded)."""
        return not self.is_folded and not self.is_sitting_out

    @property
    def vpip(self) -> float:
        """Voluntarily Put In Pot percentage (0-100)."""
        if self.hands_played == 0:
            return 0.0
        return (self.hands_voluntarily_put_in / self.hands_played) * 100

    @property
    def aggression_factor(self) -> float:
        """Raises / Calls ratio. Higher = more aggressive."""
        if self.times_called == 0:
            return float(self.times_raised) if self.times_raised else 0.0
        return self.times_raised / self.times_called

    @property
    def wtsd(self) -> float:
        """Went To Showdown percentage."""
        if self.hands_played == 0:
            return 0.0
        return (self.times_went_to_showdown / self.hands_played) * 100

    @property
    def wsd(self) -> float:
        """Won at Showdown percentage."""
        if self.times_went_to_showdown == 0:
            return 0.0
        return (self.times_won_at_showdown / self.times_went_to_showdown) * 100

    def reset_for_new_hand(self) -> None:
        """Clear per-hand state. Called at the start of each new hand."""
        self.hole_cards = []
        self.is_folded = False
        self.is_all_in = False
        self.current_bet = 0
        self.total_bet_this_hand = 0
        self.has_acted = False

    def reset_street_bet(self) -> None:
        """Reset per-street bet tracking. Called when a new street begins."""
        self.current_bet = 0
        self.has_acted = False

    def place_bet(self, amount: int) -> int:
        """
        Deduct chips from stack and add to current bet.
        Returns the actual amount bet (may be less if going all-in).
        """
        actual = min(amount, self.stack)
        self.stack -= actual
        self.current_bet += actual
        self.total_bet_this_hand += actual
        if self.stack == 0:
            self.is_all_in = True
        return actual

    def win_chips(self, amount: int) -> None:
        """Add chips to stack (pot winnings)."""
        self.stack += amount
        self.hands_won += 1
        self.total_winnings += amount
        if amount > self.biggest_pot_won:
            self.biggest_pot_won = amount

    def record_action(self, action: str, amount: int = 0) -> None:
        """Update lifetime stats based on action taken."""
        if action == "fold":
            self.times_folded += 1
        elif action == "call":
            self.times_called += 1
            self.hands_voluntarily_put_in += 1
        elif action in ("raise", "bet"):
            self.times_raised += 1
            self.hands_voluntarily_put_in += 1
        if amount > 0:
            self.total_invested += amount

    def to_dict(self, reveal_cards: bool = False) -> dict:
        """
        Serialize player state for JSON API.
        
        reveal_cards: If False, hole cards are omitted (for hidden hand mode).
        """
        data = {
            "seat": self.seat,
            "name": self.name,
            "stack": self.stack,
            "color": self.color,
            "player_type": self.player_type.value,
            "ai_style": self.ai_style.value,
            "is_folded": self.is_folded,
            "is_all_in": self.is_all_in,
            "is_active": self.is_active,
            "is_in_hand": self.is_in_hand,
            "is_sitting_out": self.is_sitting_out,
            "current_bet": self.current_bet,
            "total_bet_this_hand": self.total_bet_this_hand,
            "has_acted": self.has_acted,
            "hands_played": self.hands_played,
            "hands_won": self.hands_won,
            "vpip": round(self.vpip, 1),
            "aggression_factor": round(self.aggression_factor, 2),
            "win_rate": round((self.hands_won / self.hands_played * 100) if self.hands_played else 0, 1),
            "net_profit": self.stack - self.starting_stack,
            "total_winnings": self.total_winnings,
            "biggest_pot_won": self.biggest_pot_won,
            "times_folded": self.times_folded,
            "times_raised": self.times_raised,
            "times_called": self.times_called,
            "wtsd": round(self.wtsd, 1),
            "wsd": round(self.wsd, 1),
        }
        if reveal_cards and self.hole_cards:
            data["hole_cards"] = [c.to_dict() for c in self.hole_cards]
        else:
            data["hole_cards"] = None
            data["has_cards"] = len(self.hole_cards) > 0
        return data

    def __repr__(self) -> str:
        status = "folded" if self.is_folded else ("all-in" if self.is_all_in else "active")
        return f"Player(seat={self.seat}, {self.name}, ${self.stack}, {status})"
