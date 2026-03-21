"""
Monte Carlo equity calculator for Texas Hold'em.

Provides win/tie/loss percentages by simulating random runouts.
Uses a preflop lookup table for instant 2-card equity, and Monte Carlo
simulation for post-flop situations.

Designed to run in a background thread and push results via callback.
"""

from __future__ import annotations
import random
import threading
from typing import List, Optional, Tuple, Dict, Callable
from collections import defaultdict

from .deck import Card, Suit, Deck
from .hand_eval import HandEvaluator


# ========================================================================
# Preflop Hand Strength Table (Chen formula approximation)
# ========================================================================

# 169 canonical starting hands mapped to approximate equity vs random hand.
# Format: "AKs" = suited, "AKo" = offsuit, "AA" = pair.
# Values are approximate win % heads-up vs one random hand.
PREFLOP_EQUITY = {
    "AA": 85.0, "KK": 82.0, "QQ": 80.0, "JJ": 77.5, "TT": 75.0,
    "99": 72.0, "88": 69.0, "77": 66.5, "66": 63.5, "55": 60.5,
    "44": 57.5, "33": 54.5, "22": 51.5,
    "AKs": 67.0, "AQs": 66.0, "AJs": 65.0, "ATs": 64.5, "A9s": 62.5,
    "A8s": 61.5, "A7s": 60.5, "A6s": 59.5, "A5s": 60.0, "A4s": 59.0,
    "A3s": 58.5, "A2s": 57.5,
    "AKo": 65.0, "AQo": 64.0, "AJo": 63.0, "ATo": 62.0, "A9o": 60.0,
    "A8o": 59.0, "A7o": 58.0, "A6o": 56.5, "A5o": 57.0, "A4o": 56.0,
    "A3o": 55.5, "A2o": 54.5,
    "KQs": 63.5, "KJs": 62.5, "KTs": 61.5, "K9s": 59.5, "K8s": 57.5,
    "K7s": 56.5, "K6s": 55.5, "K5s": 55.0, "K4s": 54.0, "K3s": 53.5,
    "K2s": 52.5,
    "KQo": 61.5, "KJo": 60.5, "KTo": 59.5, "K9o": 57.0, "K8o": 55.0,
    "K7o": 54.0, "K6o": 53.0, "K5o": 52.0, "K4o": 51.0, "K3o": 50.5,
    "K2o": 49.5,
    "QJs": 60.5, "QTs": 59.5, "Q9s": 57.5, "Q8s": 55.5, "Q7s": 54.0,
    "Q6s": 53.5, "Q5s": 52.5, "Q4s": 52.0, "Q3s": 51.0, "Q2s": 50.5,
    "QJo": 58.5, "QTo": 57.5, "Q9o": 55.0, "Q8o": 53.0, "Q7o": 51.0,
    "Q6o": 50.5, "Q5o": 49.5, "Q4o": 49.0, "Q3o": 48.0, "Q2o": 47.0,
    "JTs": 57.5, "J9s": 55.5, "J8s": 54.0, "J7s": 52.0, "J6s": 50.5,
    "J5s": 50.0, "J4s": 49.0, "J3s": 48.5, "J2s": 47.5,
    "JTo": 55.5, "J9o": 53.0, "J8o": 51.0, "J7o": 49.5, "J6o": 47.5,
    "J5o": 47.0, "J4o": 46.0, "J3o": 45.0, "J2o": 44.5,
    "T9s": 54.0, "T8s": 52.5, "T7s": 50.5, "T6s": 49.0, "T5s": 47.5,
    "T4s": 47.0, "T3s": 46.0, "T2s": 45.5,
    "T9o": 51.5, "T8o": 50.0, "T7o": 48.0, "T6o": 46.0, "T5o": 44.5,
    "T4o": 44.0, "T3o": 43.0, "T2o": 42.5,
    "98s": 51.0, "97s": 49.5, "96s": 47.5, "95s": 46.0, "94s": 44.5,
    "93s": 44.0, "92s": 43.0,
    "98o": 48.5, "97o": 47.0, "96o": 44.5, "95o": 43.0, "94o": 41.5,
    "93o": 41.0, "92o": 40.0,
    "87s": 48.5, "86s": 46.5, "85s": 45.0, "84s": 43.0, "83s": 42.0,
    "82s": 41.0,
    "87o": 46.0, "86o": 44.0, "85o": 42.0, "84o": 40.0, "83o": 39.0,
    "82o": 38.0,
    "76s": 46.0, "75s": 44.5, "74s": 43.0, "73s": 41.0, "72s": 40.0,
    "76o": 43.5, "75o": 42.0, "74o": 40.0, "73o": 38.0, "72o": 37.0,
    "65s": 44.0, "64s": 42.5, "63s": 41.0, "62s": 39.5,
    "65o": 41.5, "64o": 40.0, "63o": 38.0, "62o": 36.5,
    "54s": 42.0, "53s": 40.5, "52s": 39.0,
    "54o": 39.5, "53o": 38.0, "52o": 36.0,
    "43s": 39.0, "42s": 37.5,
    "43o": 36.0, "42o": 34.5,
    "32s": 36.0, "32o": 33.0,
}


def _canonical_hand(card_a: Card, card_b: Card) -> str:
    """
    Convert two hole cards to canonical notation for preflop table lookup.
    E.g., A♠K♥ → "AKo", T♦T♣ → "TT", 5♠7♠ → "75s"
    """
    from .deck import RANK_SHORT
    r1, r2 = card_a.rank, card_b.rank
    s1, s2 = card_a.suit, card_b.suit

    # Ensure higher rank first
    if r2 > r1:
        r1, r2 = r2, r1
        s1, s2 = s2, s1

    high = RANK_SHORT[r1]
    low = RANK_SHORT[r2]

    if r1 == r2:
        return f"{high}{low}"  # Pair: "AA", "KK"
    elif s1 == s2:
        return f"{high}{low}s"  # Suited: "AKs"
    else:
        return f"{high}{low}o"  # Offsuit: "AKo"


class EquityResult:
    """Result of an equity calculation."""

    def __init__(self, win: float = 0, tie: float = 0, loss: float = 0,
                 simulations: int = 0, is_preflop: bool = False):
        self.win = win
        self.tie = tie
        self.loss = loss
        self.simulations = simulations
        self.is_preflop = is_preflop

    def to_dict(self) -> dict:
        return {
            "win": round(self.win, 1),
            "tie": round(self.tie, 1),
            "loss": round(self.loss, 1),
            "simulations": self.simulations,
            "is_preflop": self.is_preflop,
        }


class EquityCalculator:
    """
    Calculates hand equity via Monte Carlo simulation.
    
    Can run synchronously or in a background thread with callback.
    """

    DEFAULT_SIMULATIONS = 8000

    @staticmethod
    def preflop_equity(hole_cards: List[Card], num_opponents: int = 1) -> EquityResult:
        """
        Instant preflop equity from lookup table.
        Adjusts for number of opponents (rough approximation).
        """
        if len(hole_cards) != 2:
            return EquityResult()

        key = _canonical_hand(hole_cards[0], hole_cards[1])
        base_equity = PREFLOP_EQUITY.get(key, 50.0)

        # Rough multi-opponent adjustment:
        # equity vs N opponents ≈ (base_equity/100)^(0.8*N) * 100
        # This is a known approximation, not exact
        if num_opponents > 1:
            adjusted = (base_equity / 100.0) ** (0.85 + 0.15 * num_opponents) * 100
        else:
            adjusted = base_equity

        return EquityResult(
            win=adjusted,
            tie=1.0,  # Rough tie estimate
            loss=100.0 - adjusted - 1.0,
            simulations=0,
            is_preflop=True,
        )

    @staticmethod
    def monte_carlo(
        hole_cards: List[Card],
        community: List[Card],
        num_opponents: int = 1,
        dead_cards: Optional[List[Card]] = None,
        simulations: int = DEFAULT_SIMULATIONS,
        known_opponent_cards: Optional[List[List[Card]]] = None,
    ) -> EquityResult:
        """
        Run Monte Carlo equity simulation.
        
        Args:
            hole_cards: Player's 2 hole cards
            community: Current community cards (0-5)
            num_opponents: Number of opponents
            dead_cards: Cards known to be out of play (burned, etc.)
            simulations: Number of random runouts to simulate
            known_opponent_cards: If known (e.g., card picker mode)
        """
        if len(hole_cards) != 2:
            return EquityResult()

        # Build the deck of remaining cards
        used = set()
        for c in hole_cards:
            used.add(c)
        for c in community:
            used.add(c)
        if dead_cards:
            for c in dead_cards:
                used.add(c)
        if known_opponent_cards:
            for hand in known_opponent_cards:
                for c in hand:
                    used.add(c)

        all_52 = [Card(r, Suit(s)) for s in range(4) for r in range(2, 15)]
        remaining = [c for c in all_52 if c not in used]

        wins = 0
        ties = 0
        losses = 0
        rng = random.Random()

        community_needed = 5 - len(community)
        opponent_cards_needed = num_opponents * 2
        if known_opponent_cards:
            opponent_cards_needed -= sum(len(h) for h in known_opponent_cards)

        total_needed = community_needed + opponent_cards_needed
        if total_needed > len(remaining):
            # Not enough cards to simulate
            return EquityResult()

        for _ in range(simulations):
            # Sample random cards for community + opponents
            sampled = rng.sample(remaining, total_needed)
            idx = 0

            sim_community = list(community) + sampled[idx:idx + community_needed]
            idx += community_needed

            # Evaluate hero
            hero_cards = hole_cards + sim_community
            hero_score = HandEvaluator.evaluate_score(hero_cards)

            # Evaluate opponents
            hero_wins = True
            hero_ties = False

            opp_idx = 0
            for opp in range(num_opponents):
                if known_opponent_cards and opp < len(known_opponent_cards):
                    opp_hole = known_opponent_cards[opp]
                else:
                    opp_hole = sampled[idx:idx + 2]
                    idx += 2

                opp_cards = list(opp_hole) + sim_community
                opp_score = HandEvaluator.evaluate_score(opp_cards)

                if opp_score > hero_score:
                    hero_wins = False
                    hero_ties = False
                    break
                elif opp_score == hero_score:
                    hero_ties = True

            if hero_wins and not hero_ties:
                wins += 1
            elif hero_ties:
                ties += 1
            else:
                losses += 1

        total = wins + ties + losses
        if total == 0:
            return EquityResult()

        return EquityResult(
            win=(wins / total) * 100,
            tie=(ties / total) * 100,
            loss=(losses / total) * 100,
            simulations=total,
        )

    @staticmethod
    def calculate_async(
        hole_cards: List[Card],
        community: List[Card],
        num_opponents: int,
        callback: Callable[[EquityResult], None],
        dead_cards: Optional[List[Card]] = None,
        simulations: int = DEFAULT_SIMULATIONS,
    ) -> threading.Thread:
        """
        Run equity calculation in a background thread.
        Calls callback(result) when complete.
        Returns the thread object.
        """
        def _run():
            if not community:
                result = EquityCalculator.preflop_equity(hole_cards, num_opponents)
            else:
                result = EquityCalculator.monte_carlo(
                    hole_cards, community, num_opponents, dead_cards, simulations
                )
            callback(result)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
