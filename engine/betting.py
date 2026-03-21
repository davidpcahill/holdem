"""
Betting round logic and side pot calculator for Texas Hold'em.

Handles action validation, bet sizing rules, and multi-way side pot
construction for all-in situations.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field


@dataclass
class SidePot:
    """
    A side pot with the amount and eligible player seats.
    
    When a player goes all-in for less than other players' bets,
    a side pot is created that the all-in player can win, and a
    new pot is created for remaining active players.
    """
    amount: int
    eligible_seats: List[int]
    label: str = ""  # "Main Pot", "Side Pot 1", etc.

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "eligible_seats": self.eligible_seats,
            "label": self.label,
        }


class SidePotCalculator:
    """
    Builds side pots from player bet totals after a hand.
    
    Algorithm: Sort players by total bet ascending. For each unique bet level,
    create a pot containing contributions from all players up to that level.
    """

    @staticmethod
    def calculate(players_bets: List[Tuple[int, int, bool]]) -> List[SidePot]:
        """
        Calculate side pots from player contributions.
        
        Args:
            players_bets: List of (seat, total_bet_this_hand, is_folded) tuples
                          for all players who contributed to the pot.
        
        Returns:
            List of SidePot objects, from main pot to last side pot.
        """
        # Filter out players who bet 0
        bettors = [(seat, bet, folded) for seat, bet, folded in players_bets if bet > 0]
        if not bettors:
            return []

        # Sort by bet amount ascending
        bettors.sort(key=lambda x: x[1])

        # Get unique bet levels
        bet_levels = sorted(set(bet for _, bet, _ in bettors))

        pots: List[SidePot] = []
        prev_level = 0

        for level in bet_levels:
            # How much each player contributes to this pot layer
            layer_per_player = level - prev_level
            if layer_per_player <= 0:
                continue

            # Players who contributed at least this much
            contributors = [seat for seat, bet, _ in bettors if bet >= level]
            # Eligible to win: contributed AND not folded
            eligible = [seat for seat, bet, folded in bettors if bet >= level and not folded]

            pot_amount = layer_per_player * len(contributors)
            if pot_amount > 0 and eligible:
                pots.append(SidePot(amount=pot_amount, eligible_seats=eligible))

            prev_level = level

        # Label pots
        if pots:
            pots[0].label = "Main Pot"
            for i in range(1, len(pots)):
                pots[i].label = f"Side Pot {i}"

        return pots


@dataclass
class ActionResult:
    """Result of processing a player action."""
    valid: bool
    action: str = ""          # "fold", "check", "call", "bet", "raise"
    amount: int = 0           # Chips put in (0 for fold/check)
    is_all_in: bool = False   # Player went all-in with this action
    error: str = ""           # Error message if invalid
    street_complete: bool = False  # Betting round is done

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "action": self.action,
            "amount": self.amount,
            "is_all_in": self.is_all_in,
            "error": self.error,
        }


class BettingRound:
    """
    Manages a single betting round (preflop, flop, turn, or river).
    
    Tracks the current bet, last raise size, and determines when
    the round is complete (all active players have acted and bets are matched).
    """

    def __init__(
        self,
        num_players: int,
        big_blind: int,
        is_preflop: bool = False,
    ):
        self.big_blind = big_blind
        self.is_preflop = is_preflop
        self.current_bet = 0        # Highest bet on the table this street
        self.last_raise_size = big_blind  # Minimum raise = last raise size
        self.num_actions = 0
        self.pot_this_street = 0    # Chips added to pot this street

    def validate_action(
        self,
        action: str,
        amount: int,
        player_stack: int,
        player_current_bet: int,
        to_call: int,
        is_big_blind: bool = False,
        num_active: int = 2,
    ) -> ActionResult:
        """
        Validate and normalize a player action.
        
        Args:
            action: "fold", "check", "call", "bet", "raise"
            amount: Chip amount for bet/raise (total, not additional)
            player_stack: Player's current stack before this action
            player_current_bet: What player has already bet this street
            to_call: Additional chips needed to match current bet
            is_big_blind: True if player is BB in preflop (option to check)
            num_active: Number of players who can still act
            
        Returns:
            ActionResult with validated action details.
        """
        # Fold is always valid (except when checking is free)
        if action == "fold":
            return ActionResult(valid=True, action="fold", amount=0)

        # Check: valid only when no bet to call (or BB preflop with no raise)
        if action == "check":
            if to_call > 0 and not (is_big_blind and self.current_bet == self.big_blind
                                     and player_current_bet == self.big_blind):
                return ActionResult(valid=False, error=f"Cannot check, must call {to_call} or fold")
            return ActionResult(valid=True, action="check", amount=0)

        # Call: match the current bet
        if action == "call":
            if to_call <= 0:
                # Nothing to call, convert to check
                return ActionResult(valid=True, action="check", amount=0)
            actual_call = min(to_call, player_stack)
            is_all_in = actual_call >= player_stack
            return ActionResult(
                valid=True, action="call", amount=actual_call, is_all_in=is_all_in
            )

        # Bet or Raise
        if action in ("bet", "raise"):
            # Normalize: "bet" when no current bet, "raise" when there is one
            if self.current_bet > 0:
                action = "raise"
            else:
                action = "bet"

            # All-in is always valid regardless of minimum
            if amount >= player_stack + player_current_bet:
                actual = player_stack
                return ActionResult(
                    valid=True, action=action, amount=actual, is_all_in=True
                )

            # Minimum bet/raise validation
            if action == "bet":
                min_bet = self.big_blind
                if amount < min_bet:
                    return ActionResult(
                        valid=False,
                        error=f"Minimum bet is {min_bet}"
                    )
                additional = amount - player_current_bet
                return ActionResult(
                    valid=True, action="bet", amount=additional
                )
            else:  # raise
                # Min raise = current bet + last raise size
                min_raise_to = self.current_bet + self.last_raise_size
                if amount < min_raise_to:
                    # If player can't afford min raise, must go all-in or call
                    if amount >= player_stack + player_current_bet:
                        actual = player_stack
                        return ActionResult(
                            valid=True, action="raise", amount=actual, is_all_in=True
                        )
                    return ActionResult(
                        valid=False,
                        error=f"Minimum raise is to {min_raise_to} (current bet {self.current_bet} + last raise {self.last_raise_size})"
                    )
                # Amount is the total the player wants their bet to be
                additional = amount - player_current_bet
                if additional > player_stack:
                    additional = player_stack
                return ActionResult(
                    valid=True, action="raise", amount=additional,
                    is_all_in=(additional >= player_stack)
                )

        return ActionResult(valid=False, error=f"Unknown action: {action}")

    def apply_bet(self, amount: int, player_current_bet: int) -> None:
        """
        Update round state after a bet/raise is applied.
        
        Args:
            amount: Additional chips the player put in
            player_current_bet: Player's total bet this street AFTER the action
        """
        new_total = player_current_bet
        if new_total > self.current_bet:
            raise_size = new_total - self.current_bet
            self.last_raise_size = max(raise_size, self.last_raise_size)
            self.current_bet = new_total
        self.pot_this_street += amount
        self.num_actions += 1

    def apply_call(self, amount: int) -> None:
        """Update round state after a call."""
        self.pot_this_street += amount
        self.num_actions += 1

    def apply_check(self) -> None:
        """Update round state after a check."""
        self.num_actions += 1

    def apply_fold(self) -> None:
        """Update round state after a fold."""
        self.num_actions += 1

    @staticmethod
    def is_round_complete(
        players_active: List[dict],
        current_bet: int,
    ) -> bool:
        """
        Check if the betting round is complete.
        
        A round is complete when all active (non-folded, non-all-in) players
        have acted and their bets match the current bet.
        
        Args:
            players_active: List of dicts with keys:
                'is_folded', 'is_all_in', 'has_acted', 'current_bet'
            current_bet: The current highest bet on this street
        """
        for p in players_active:
            if p["is_folded"] or p["is_all_in"]:
                continue
            if not p["has_acted"]:
                return False
            if p["current_bet"] < current_bet:
                return False
        return True
