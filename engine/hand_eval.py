"""
Texas Hold'em Hand Evaluator.

Evaluates the best 5-card poker hand from up to 7 cards using exhaustive
combination checking. Returns a HandResult with rank, kickers, and description.

Hand rankings (highest to lowest):
    Royal Flush > Straight Flush > Four of a Kind > Full House > Flush >
    Straight > Three of a Kind > Two Pair > One Pair > High Card

The evaluator produces a numeric score tuple that can be directly compared:
    (hand_rank, *tiebreakers)
Higher tuple = better hand. Python tuple comparison handles this naturally.
"""

from __future__ import annotations
from enum import IntEnum
from itertools import combinations
from typing import List, Tuple, Optional, NamedTuple
from collections import Counter
from .deck import Card, RANK_SHORT, RANK_DISPLAY, SUIT_SYMBOLS


class HandRank(IntEnum):
    """
    Poker hand rankings. Higher value = better hand.
    These are the primary sort key in hand comparison.
    """
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


# Human-readable names for display
HAND_RANK_NAMES = {
    HandRank.HIGH_CARD: "High Card",
    HandRank.ONE_PAIR: "One Pair",
    HandRank.TWO_PAIR: "Two Pair",
    HandRank.THREE_OF_A_KIND: "Three of a Kind",
    HandRank.STRAIGHT: "Straight",
    HandRank.FLUSH: "Flush",
    HandRank.FULL_HOUSE: "Full House",
    HandRank.FOUR_OF_A_KIND: "Four of a Kind",
    HandRank.STRAIGHT_FLUSH: "Straight Flush",
    HandRank.ROYAL_FLUSH: "Royal Flush",
}


class HandResult(NamedTuple):
    """
    Result of evaluating a poker hand.
    
    rank: HandRank enum (PRIMARY comparison key)
    score: Full comparison tuple (rank, *tiebreakers). Compare these directly.
    cards: The 5 cards that make the best hand
    name: Human-readable hand description (e.g. "Two Pair, Aces and Kings")
    kickers: Tiebreaker card ranks in descending order
    """
    rank: HandRank
    score: Tuple[int, ...]
    cards: Tuple[Card, ...]
    name: str
    kickers: Tuple[int, ...]

    def beats(self, other: HandResult) -> bool:
        """True if this hand strictly beats the other."""
        return self.score > other.score

    def ties(self, other: HandResult) -> bool:
        """True if this hand ties the other."""
        return self.score == other.score

    def to_dict(self) -> dict:
        """Serialize for JSON API."""
        return {
            "rank": self.rank.value,
            "rank_name": HAND_RANK_NAMES[self.rank],
            "name": self.name,
            "cards": [c.to_dict() for c in self.cards],
            "kickers": list(self.kickers),
        }


class HandEvaluator:
    """
    Evaluates poker hands using exhaustive 5-card combination checking.
    
    For 7 cards this checks C(7,5) = 21 combinations. Fast enough for
    gameplay and even Monte Carlo simulations (millions of evals/sec in Python
    with the numeric scoring shortcut).
    """

    @staticmethod
    def evaluate(cards: List[Card]) -> HandResult:
        """
        Find the best 5-card poker hand from a list of 2-7 cards.
        
        For fewer than 5 cards (e.g., preflop with 2 cards), evaluates
        the best hand possible with available cards.
        
        Returns a HandResult with full comparison info.
        """
        if len(cards) < 2:
            raise ValueError(f"Need at least 2 cards, got {len(cards)}")

        if len(cards) <= 5:
            # With 5 or fewer cards, there's only one combination
            return HandEvaluator._evaluate_five(tuple(sorted(cards, reverse=True)))

        # Check all C(n, 5) combinations, keep the best
        best: Optional[HandResult] = None
        for combo in combinations(cards, 5):
            five = tuple(sorted(combo, reverse=True))
            result = HandEvaluator._evaluate_five(five)
            if best is None or result.score > best.score:
                best = result

        assert best is not None
        return best

    @staticmethod
    def evaluate_score(cards: List[Card]) -> Tuple[int, ...]:
        """
        Fast path: returns only the score tuple for comparison.
        Used in Monte Carlo simulations where we don't need the full HandResult.
        """
        if len(cards) <= 5:
            five = tuple(sorted(cards, reverse=True))
            return HandEvaluator._score_five(five)

        best_score: Optional[Tuple[int, ...]] = None
        for combo in combinations(cards, 5):
            five = tuple(sorted(combo, reverse=True))
            score = HandEvaluator._score_five(five)
            if best_score is None or score > best_score:
                best_score = score

        assert best_score is not None
        return best_score

    @staticmethod
    def _evaluate_five(cards: Tuple[Card, ...]) -> HandResult:
        """
        Evaluate exactly 5 cards. Cards must be sorted descending by rank.
        Returns full HandResult.
        """
        ranks = tuple(c.rank for c in cards)
        suits = tuple(c.suit for c in cards)
        rank_counts = Counter(ranks)
        is_flush = len(set(suits)) == 1
        is_straight, straight_high = HandEvaluator._check_straight(ranks)

        # --- Straight Flush / Royal Flush ---
        if is_flush and is_straight:
            if straight_high == 14:
                return HandResult(
                    rank=HandRank.ROYAL_FLUSH,
                    score=(HandRank.ROYAL_FLUSH, 14),
                    cards=cards,
                    name="Royal Flush",
                    kickers=(14,),
                )
            return HandResult(
                rank=HandRank.STRAIGHT_FLUSH,
                score=(HandRank.STRAIGHT_FLUSH, straight_high),
                cards=cards,
                name=f"Straight Flush, {RANK_DISPLAY[straight_high]} high",
                kickers=(straight_high,),
            )

        # --- Four of a Kind ---
        if 4 in rank_counts.values():
            quad_rank = [r for r, c in rank_counts.items() if c == 4][0]
            kicker = max(r for r in ranks if r != quad_rank)
            return HandResult(
                rank=HandRank.FOUR_OF_A_KIND,
                score=(HandRank.FOUR_OF_A_KIND, quad_rank, kicker),
                cards=cards,
                name=f"Four of a Kind, {RANK_DISPLAY[quad_rank]}s",
                kickers=(quad_rank, kicker),
            )

        # --- Full House ---
        if sorted(rank_counts.values()) == [2, 3]:
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            return HandResult(
                rank=HandRank.FULL_HOUSE,
                score=(HandRank.FULL_HOUSE, trip_rank, pair_rank),
                cards=cards,
                name=f"Full House, {RANK_DISPLAY[trip_rank]}s full of {RANK_DISPLAY[pair_rank]}s",
                kickers=(trip_rank, pair_rank),
            )

        # --- Flush ---
        if is_flush:
            return HandResult(
                rank=HandRank.FLUSH,
                score=(HandRank.FLUSH, *ranks),
                cards=cards,
                name=f"Flush, {RANK_DISPLAY[ranks[0]]} high",
                kickers=ranks,
            )

        # --- Straight ---
        if is_straight:
            return HandResult(
                rank=HandRank.STRAIGHT,
                score=(HandRank.STRAIGHT, straight_high),
                cards=cards,
                name=f"Straight, {RANK_DISPLAY[straight_high]} high",
                kickers=(straight_high,),
            )

        # --- Three of a Kind ---
        if 3 in rank_counts.values():
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            kickers = sorted([r for r in ranks if r != trip_rank], reverse=True)
            return HandResult(
                rank=HandRank.THREE_OF_A_KIND,
                score=(HandRank.THREE_OF_A_KIND, trip_rank, *kickers),
                cards=cards,
                name=f"Three of a Kind, {RANK_DISPLAY[trip_rank]}s",
                kickers=(trip_rank, *kickers),
            )

        # --- Two Pair ---
        pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
        if len(pairs) == 2:
            kicker = max(r for r in ranks if r not in pairs)
            return HandResult(
                rank=HandRank.TWO_PAIR,
                score=(HandRank.TWO_PAIR, pairs[0], pairs[1], kicker),
                cards=cards,
                name=f"Two Pair, {RANK_DISPLAY[pairs[0]]}s and {RANK_DISPLAY[pairs[1]]}s",
                kickers=(pairs[0], pairs[1], kicker),
            )

        # --- One Pair ---
        if len(pairs) == 1:
            pair_rank = pairs[0]
            kickers = sorted([r for r in ranks if r != pair_rank], reverse=True)
            return HandResult(
                rank=HandRank.ONE_PAIR,
                score=(HandRank.ONE_PAIR, pair_rank, *kickers),
                cards=cards,
                name=f"Pair of {RANK_DISPLAY[pair_rank]}s",
                kickers=(pair_rank, *kickers),
            )

        # --- High Card ---
        return HandResult(
            rank=HandRank.HIGH_CARD,
            score=(HandRank.HIGH_CARD, *ranks),
            cards=cards,
            name=f"High Card, {RANK_DISPLAY[ranks[0]]}",
            kickers=ranks,
        )

    @staticmethod
    def _score_five(cards: Tuple[Card, ...]) -> Tuple[int, ...]:
        """
        Fast scoring — returns only the comparison tuple, no string building.
        Used in Monte Carlo hot loop.
        """
        ranks = tuple(c.rank for c in cards)
        suits = tuple(c.suit for c in cards)
        rank_counts = Counter(ranks)
        is_flush = suits[0] == suits[1] == suits[2] == suits[3] == suits[4]
        is_straight, straight_high = HandEvaluator._check_straight(ranks)

        if is_flush and is_straight:
            return (HandRank.ROYAL_FLUSH if straight_high == 14 else HandRank.STRAIGHT_FLUSH, straight_high)

        counts_sorted = sorted(rank_counts.values())

        if counts_sorted == [1, 4]:
            quad_rank = [r for r, c in rank_counts.items() if c == 4][0]
            kicker = max(r for r in ranks if r != quad_rank)
            return (HandRank.FOUR_OF_A_KIND, quad_rank, kicker)

        if counts_sorted == [2, 3]:
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            return (HandRank.FULL_HOUSE, trip_rank, pair_rank)

        if is_flush:
            return (HandRank.FLUSH, *ranks)

        if is_straight:
            return (HandRank.STRAIGHT, straight_high)

        if counts_sorted == [1, 1, 3]:
            trip_rank = [r for r, c in rank_counts.items() if c == 3][0]
            kickers = sorted([r for r in ranks if r != trip_rank], reverse=True)
            return (HandRank.THREE_OF_A_KIND, trip_rank, *kickers)

        if counts_sorted == [1, 2, 2]:
            pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
            kicker = max(r for r in ranks if r not in pairs)
            return (HandRank.TWO_PAIR, pairs[0], pairs[1], kicker)

        if counts_sorted == [1, 1, 1, 2]:
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            kickers = sorted([r for r in ranks if r != pair_rank], reverse=True)
            return (HandRank.ONE_PAIR, pair_rank, *kickers)

        return (HandRank.HIGH_CARD, *ranks)

    @staticmethod
    def _check_straight(ranks: Tuple[int, ...]) -> Tuple[bool, int]:
        """
        Check if 5 sorted-descending ranks form a straight.
        
        Returns (is_straight, high_card_rank).
        Handles the wheel (A-2-3-4-5) where ace plays low.
        """
        unique = sorted(set(ranks), reverse=True)
        if len(unique) != 5:
            return False, 0

        # Normal straight: consecutive descending
        if unique[0] - unique[4] == 4:
            return True, unique[0]

        # Wheel straight: A-5-4-3-2 (ace plays as 1)
        if unique == [14, 5, 4, 3, 2]:
            return True, 5  # 5-high straight

        return False, 0

    @staticmethod
    def compare(hand_a: HandResult, hand_b: HandResult) -> int:
        """
        Compare two evaluated hands.
        Returns: 1 if a wins, -1 if b wins, 0 if tie.
        """
        if hand_a.score > hand_b.score:
            return 1
        elif hand_a.score < hand_b.score:
            return -1
        return 0

    @staticmethod
    def find_winners(hands: List[Tuple[int, HandResult]]) -> List[int]:
        """
        Given a list of (player_index, HandResult) pairs, return the
        indices of all players who tie for the best hand.
        """
        if not hands:
            return []
        best_score = max(h.score for _, h in hands)
        return [idx for idx, h in hands if h.score == best_score]

    @staticmethod
    def describe_best_draw(hole_cards: List[Card], community: List[Card]) -> str:
        """
        Describe the current best hand and any notable draws.
        Used by the advisor to give human-readable status.
        """
        all_cards = hole_cards + community
        result = HandEvaluator.evaluate(all_cards)
        desc = result.name

        # Check for draws if we haven't reached the river
        if len(community) < 5:
            draws = []
            # Flush draw: 4 of same suit
            suit_counts = Counter(c.suit for c in all_cards)
            for suit, count in suit_counts.items():
                if count == 4:
                    draws.append("Flush draw")
                    break

            # Straight draw (open-ended or gutshot)
            ranks = sorted(set(c.rank for c in all_cards))
            # Check for open-ended straight draw (4 consecutive)
            for i in range(len(ranks) - 3):
                window = ranks[i:i+4]
                if window[-1] - window[0] == 3 and len(window) == 4:
                    draws.append("Open-ended straight draw")
                    break
            # Check for gutshot (4 of 5 consecutive with one gap)
            else:
                for i in range(len(ranks) - 3):
                    window = ranks[i:i+4]
                    if window[-1] - window[0] == 4 and len(window) == 4:
                        draws.append("Gutshot straight draw")
                        break

            if draws:
                desc += " + " + ", ".join(draws)

        return desc
