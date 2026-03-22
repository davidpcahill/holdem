"""
AI decision engine for Texas Hold'em.

Three base styles:
- Loose-Passive: Calls wide, rarely raises, low bluff frequency
- Tight-Aggressive (TAG): Folds weak hands, 3-bets strong, pressures
- GTO: Balanced ranges, mixed strategies, positional awareness

Each style uses pot odds, equity, position, stack depth, and opponent
VPIP/aggression stats to make decisions. A variance parameter adds
controlled randomness to prevent robotic play.
"""

from __future__ import annotations
import random
import time
from typing import List, Dict, Optional, Tuple
from enum import Enum

from .player import Player, AIStyle
from .equity import EquityCalculator, EquityResult
from .deck import Card


class AIDecision:
    """Result of AI decision-making."""
    def __init__(self, action: str, amount: int = 0, reasoning: str = "",
                 think_time: float = 0.0):
        self.action = action      # "fold", "check", "call", "bet", "raise"
        self.amount = amount      # Total bet/raise amount
        self.reasoning = reasoning
        self.think_time = think_time

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "amount": self.amount,
            "reasoning": self.reasoning,
            "think_time": round(self.think_time, 1),
        }


# Style parameters
STYLE_PARAMS = {
    AIStyle.LOOSE_PASSIVE: {
        "preflop_call_threshold": 25,    # Calls with top 75% of hands
        "preflop_raise_threshold": 70,   # Only raises top 30%
        "postflop_call_threshold": 0.6,  # Calls when equity/pot odds > 0.6
        "bluff_frequency": 0.08,         # 8% bluff rate
        "raise_frequency": 0.15,         # Rarely raises post-flop
        "cbet_frequency": 0.30,          # Low c-bet rate
        "base_think_ms": 1500,
    },
    AIStyle.TIGHT_AGGRESSIVE: {
        "preflop_call_threshold": 50,    # Calls with top 50% of hands
        "preflop_raise_threshold": 60,   # Raises top 40%
        "postflop_call_threshold": 0.85, # Needs good odds to call
        "bluff_frequency": 0.22,         # Moderate bluff rate
        "raise_frequency": 0.55,         # Aggressive post-flop
        "cbet_frequency": 0.70,          # High c-bet rate
        "base_think_ms": 2000,
    },
    AIStyle.GTO: {
        "preflop_call_threshold": 40,    # Balanced calling range
        "preflop_raise_threshold": 55,   # Balanced raising range
        "postflop_call_threshold": 0.75, # Pot-odds based
        "bluff_frequency": 0.30,         # Theory-optimal bluff:value
        "raise_frequency": 0.40,
        "cbet_frequency": 0.55,          # Position-dependent
        "base_think_ms": 2500,
    },
}

# AI timing presets (multipliers on base think time)
TIMING_PRESETS = {
    "fast": 0.0,       # Instant (practice mode)
    "realistic": 1.0,  # Normal speed
    "tournament": 1.8,  # Slow, dramatic
}

# Difficulty presets bundle style behavior + timing + variance
# Used by the setup UI to offer Easy/Medium/Hard without tuning individual params
DIFFICULTY_PRESETS = {
    "easy": {
        "label": "Easy",
        "description": "Passive, predictable, fast — great for learning",
        "ai_style": "loose_passive",
        "timing_preset": "fast",
        "variance": 0.5,        # More erratic = weaker
        "equity_sims": 200,     # Fewer sims = worse decisions
    },
    "medium": {
        "label": "Medium",
        "description": "Balanced play with moderate aggression",
        "ai_style": "random",
        "timing_preset": "realistic",
        "variance": 0.3,
        "equity_sims": 500,
    },
    "hard": {
        "label": "Hard",
        "description": "Tight-aggressive with sharp reads",
        "ai_style": "tight_aggressive",
        "timing_preset": "realistic",
        "variance": 0.1,        # Less random = stronger
        "equity_sims": 1000,
    },
    "expert": {
        "label": "Expert",
        "description": "GTO-balanced, minimal mistakes, tournament pace",
        "ai_style": "gto",
        "timing_preset": "tournament",
        "variance": 0.05,       # Nearly optimal
        "equity_sims": 2000,
    },
}


class AIEngine:
    """
    Makes decisions for AI-controlled players.
    
    Uses equity estimation, pot odds, position, and style parameters
    to determine actions. Tracks opponent behavior for adjustment.
    """

    def __init__(self, timing_preset: str = "realistic", variance: float = 0.3):
        self.timing_preset = timing_preset
        self.variance = variance  # 0.0 = deterministic, 1.0 = very erratic
        self._rng = random.Random()

    def decide(
        self,
        player: Player,
        valid_actions: dict,
        equity: EquityResult,
        community_cards: List[Card],
        pot: int,
        street: str,
        position: str,
        num_opponents: int,
        opponent_stats: Optional[Dict] = None,
    ) -> AIDecision:
        """
        Make a decision for an AI player.
        
        Returns an AIDecision with action, amount, and reasoning.
        """
        # RANDOM style: pick a random base style each decision
        if player.ai_style == AIStyle.RANDOM:
            params = self._rng.choice(list(STYLE_PARAMS.values()))
        else:
            params = STYLE_PARAMS[player.ai_style]
        actions = valid_actions.get("actions", [])
        to_call = valid_actions.get("to_call", 0)
        current_bet = valid_actions.get("current_bet", 0)
        stack = player.stack

        if not actions:
            return AIDecision("check", reasoning="No valid actions")

        # Available action types
        can_fold = any(a["action"] == "fold" for a in actions)
        can_check = any(a["action"] == "check" for a in actions)
        can_call = any(a["action"] == "call" for a in actions)
        can_raise = any(a["action"] in ("bet", "raise") for a in actions)
        raise_info = next((a for a in actions if a["action"] in ("bet", "raise")), None)

        win_pct = equity.win
        pot_odds = (to_call / (pot + to_call)) * 100 if (pot + to_call) > 0 else 0

        # Stack-to-pot ratio
        spr = stack / pot if pot > 0 else 20

        # Position modifier: later position = more aggressive
        position_bonus = {
            "BTN": 8, "CO": 5, "HJ": 2, "BTN/SB": 3,
            "SB": -2, "BB": 0, "UTG": -5, "UTG+1": -3,
            "MP": 0, "MP+1": 1, "MP+2": 2,
        }.get(position, 0)

        # Adjust equity with position
        adjusted_equity = win_pct + position_bonus

        # --- Preflop logic ---
        if street == "preflop":
            return self._preflop_decision(
                player, params, adjusted_equity, to_call, pot, stack,
                can_check, can_call, can_raise, raise_info, position_bonus
            )

        # --- Post-flop logic ---
        return self._postflop_decision(
            player, params, adjusted_equity, win_pct, pot_odds, to_call,
            pot, stack, spr, can_check, can_call, can_raise, raise_info,
            street, position_bonus, num_opponents
        )

    def _preflop_decision(
        self, player, params, equity, to_call, pot, stack,
        can_check, can_call, can_raise, raise_info, pos_bonus
    ) -> AIDecision:
        """Preflop decision logic."""
        noise = self._rng.gauss(0, 5 * self.variance)
        eq = equity + noise

        # Strong hand: raise
        if eq >= params["preflop_raise_threshold"] and can_raise and raise_info:
            size = self._size_raise(raise_info, pot, stack, "value")
            return AIDecision("raise", size, f"Strong preflop hand (equity ~{equity:.0f}%)")

        # Playable hand: call
        if eq >= params["preflop_call_threshold"]:
            if can_check:
                return AIDecision("check", 0, "Check with marginal hand")
            if can_call:
                return AIDecision("call", 0, f"Calling with decent hand (equity ~{equity:.0f}%)")

        # Bluff raise (style-dependent)
        if can_raise and raise_info and self._rng.random() < params["bluff_frequency"] * 0.5:
            size = self._size_raise(raise_info, pot, stack, "bluff")
            return AIDecision("raise", size, "Preflop bluff raise")

        # Weak hand
        if can_check:
            return AIDecision("check", 0, "Checking weak hand")
        return AIDecision("fold", 0, f"Folding weak hand (equity ~{equity:.0f}%)")

    def _postflop_decision(
        self, player, params, adjusted_eq, raw_eq, pot_odds, to_call,
        pot, stack, spr, can_check, can_call, can_raise, raise_info,
        street, pos_bonus, num_opponents
    ) -> AIDecision:
        """Post-flop decision logic."""
        noise = self._rng.gauss(0, 8 * self.variance)
        eq = adjusted_eq + noise

        # Equity edge over pot odds
        equity_edge = raw_eq - pot_odds

        # --- Strong hand: bet/raise for value ---
        if eq > 70 and can_raise and raise_info:
            size = self._size_raise(raise_info, pot, stack, "value")
            return AIDecision(
                raise_info["action"], size,
                f"Value bet (equity ~{raw_eq:.0f}% vs pot odds {pot_odds:.0f}%)"
            )

        # --- Semi-bluff with draws ---
        if 40 < eq < 65 and can_raise and raise_info:
            if self._rng.random() < params["raise_frequency"]:
                size = self._size_raise(raise_info, pot, stack, "semi_bluff")
                return AIDecision(
                    raise_info["action"], size,
                    f"Semi-bluff (equity ~{raw_eq:.0f}%)"
                )

        # --- Continuation bet (if was last aggressor) ---
        if can_raise and raise_info and to_call == 0:
            if self._rng.random() < params["cbet_frequency"]:
                size = self._size_raise(raise_info, pot, stack, "cbet")
                return AIDecision(
                    raise_info["action"], size, "Continuation bet"
                )

        # --- Call with adequate equity ---
        if can_call and to_call > 0:
            call_threshold = pot_odds * params["postflop_call_threshold"]
            if raw_eq > call_threshold:
                return AIDecision("call", 0, f"Calling (equity {raw_eq:.0f}% > threshold {call_threshold:.0f}%)")

            # Occasional call as float (deception)
            if self._rng.random() < 0.1 * self.variance:
                return AIDecision("call", 0, "Floating call")

        # --- Pure bluff ---
        if can_raise and raise_info and self._rng.random() < params["bluff_frequency"]:
            if spr > 3:  # Don't bluff with shallow stack
                size = self._size_raise(raise_info, pot, stack, "bluff")
                return AIDecision(raise_info["action"], size, "Pure bluff")

        # --- Check if possible ---
        if can_check:
            return AIDecision("check", 0, "Checking")

        # --- Fold ---
        return AIDecision("fold", 0, f"Folding (equity ~{raw_eq:.0f}% insufficient)")

    def _size_raise(self, raise_info: dict, pot: int, stack: int, bet_type: str) -> int:
        """
        Determine raise size based on bet type and randomness.
        Returns the total raise-to amount, rounded to a clean increment.
        """
        min_raise = raise_info.get("min", 0)
        max_raise = raise_info.get("max", stack)

        if bet_type == "value":
            target = int(pot * (0.6 + self._rng.random() * 0.2))
        elif bet_type == "semi_bluff":
            target = int(pot * (0.5 + self._rng.random() * 0.15))
        elif bet_type == "cbet":
            target = int(pot * (0.4 + self._rng.random() * 0.2))
        elif bet_type == "bluff":
            target = int(pot * (0.55 + self._rng.random() * 0.2))
        else:
            target = int(pot * 0.5)

        # Clamp to valid range
        target = max(min_raise, min(target, max_raise))

        # Add noise
        noise = int(target * self._rng.gauss(0, 0.05 * self.variance))
        target = max(min_raise, min(target + noise, max_raise))

        # Round to clean increment (like a human would bet)
        target = self._round_bet(target, min_raise, max_raise)

        return target

    @staticmethod
    def _round_bet(amount: int, min_bet: int, max_bet: int) -> int:
        """
        Round a bet to a clean human-like increment.
        Small bets round to 5/10, medium to 25/50, large to 100/250.
        Never rounds below min_bet or above max_bet.
        All-in (amount >= max_bet * 0.9) snaps to exact max.
        """
        if amount >= max_bet * 0.9:
            return max_bet  # Close enough to all-in — just shove

        if amount < 50:
            step = 5
        elif amount < 200:
            step = 10
        elif amount < 500:
            step = 25
        elif amount < 2000:
            step = 50
        elif amount < 10000:
            step = 100
        else:
            step = 250

        rounded = round(amount / step) * step
        return max(min_bet, min(rounded, max_bet))

    def calculate_think_time(self, player: Player) -> float:
        """
        Calculate artificial think time for natural-feeling AI.
        Returns seconds to wait before executing action.
        """
        preset_mult = TIMING_PRESETS.get(self.timing_preset, 1.0)
        if preset_mult == 0:
            return 0.0

        if player.ai_style == AIStyle.RANDOM:
            params = self._rng.choice(list(STYLE_PARAMS.values()))
        else:
            params = STYLE_PARAMS[player.ai_style]
        base_ms = params["base_think_ms"]

        # Apply preset
        ms = base_ms * preset_mult

        # Add variance
        variance_range = ms * self.variance
        ms += self._rng.uniform(-variance_range, variance_range)

        return max(0.1, ms / 1000.0)
