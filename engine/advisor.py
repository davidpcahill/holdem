"""
Advisor for human players in Texas Hold'em.

Provides real-time recommendations including:
- Equity (win/tie/loss percentages)
- Outs counting and hit probability
- Pot odds analysis
- Stack-to-Pot Ratio (SPR) assessment
- Expected Value (EV) estimation
- Action ranking with reasoning
- Suggested bet sizing

The advisor is non-blocking: it provides recommendations but the player
always has full freedom to choose any action.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Tuple
from collections import Counter
from itertools import combinations

from .deck import Card, Suit, RANK_SHORT, RANK_DISPLAY, SUIT_SYMBOLS
from .hand_eval import HandEvaluator, HandRank
from .equity import EquityCalculator, EquityResult
import time as _time


class OutsInfo:
    """Information about drawing outs."""
    def __init__(self, count: int = 0, draws: List[str] = None,
                 hit_turn_pct: float = 0, hit_river_pct: float = 0,
                 hit_either_pct: float = 0, out_cards: List[dict] = None):
        self.count = count
        self.draws = draws or []
        self.hit_turn_pct = hit_turn_pct
        self.hit_river_pct = hit_river_pct
        self.hit_either_pct = hit_either_pct
        self.out_cards = out_cards or []

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "draws": self.draws,
            "hit_turn_pct": round(self.hit_turn_pct, 1),
            "hit_river_pct": round(self.hit_river_pct, 1),
            "hit_either_pct": round(self.hit_either_pct, 1),
            "out_cards": self.out_cards[:12],
        }


class ActionRecommendation:
    """A recommended action with score and reasoning."""
    def __init__(self, action: str, score: float, ev: float = 0,
                 label: str = "", reasoning: str = "",
                 bet_range: Optional[Tuple[int, int]] = None,
                 bet_type: str = ""):
        self.action = action       # "fold", "check", "call", "raise", "bet"
        self.score = score         # 0-100 score for ranking
        self.ev = ev               # Expected value in chips
        self.label = label         # Short label like "Strong Call"
        self.reasoning = reasoning
        self.bet_range = bet_range # (min, max) suggested bet size
        self.bet_type = bet_type   # "value", "semi_bluff", "bluff"

    def to_dict(self) -> dict:
        d = {
            "action": self.action,
            "score": round(self.score, 1),
            "ev": round(self.ev, 1),
            "label": self.label,
            "reasoning": self.reasoning,
            "bet_type": self.bet_type,
        }
        if self.bet_range:
            d["bet_range"] = list(self.bet_range)
        return d


class AdvisorResult:
    """Complete advisory information for a player."""
    def __init__(self):
        self.equity: Optional[EquityResult] = None
        self.hand_name: str = ""
        self.hand_rank: str = ""
        self.draw_description: str = ""
        self.outs: Optional[OutsInfo] = None
        self.pot_odds: float = 0           # Required equity to call (%)
        self.pot_odds_ratio: str = ""      # e.g., "3.5:1"
        self.spr: float = 0               # Stack-to-Pot Ratio
        self.spr_label: str = ""           # "committed", "medium", "deep"
        self.implied_odds: float = 0       # Estimated implied odds ratio
        self.fold_equity: float = 0        # Estimated fold equity (%)
        self.equity_edge: float = 0        # Equity minus pot odds
        self.position: str = ""
        self.position_modifier: float = 0
        self.estimated_ev: float = 0       # EV of top recommendation
        self.actions: List[ActionRecommendation] = []
        self.top_action: Optional[ActionRecommendation] = None
        self.best_hand_cards: List[dict] = []  # The 5 cards making the best hand
        self.adjusted_equity: Optional[float] = None  # Equity discounted for opponent betting strength
        self.timing: dict = {}  # Section timings in ms

    def to_dict(self) -> dict:
        return {
            "equity": self.equity.to_dict() if self.equity else None,
            "adjusted_equity": round(self.adjusted_equity, 1) if self.adjusted_equity is not None else None,
            "hand_name": self.hand_name,
            "hand_rank": self.hand_rank,
            "draw_description": self.draw_description,
            "best_hand_cards": self.best_hand_cards,
            "outs": self.outs.to_dict() if self.outs else None,
            "pot_odds": round(self.pot_odds, 1),
            "pot_odds_ratio": self.pot_odds_ratio,
            "spr": round(self.spr, 1),
            "spr_label": self.spr_label,
            "implied_odds": round(self.implied_odds, 1),
            "fold_equity": round(self.fold_equity, 1),
            "equity_edge": round(self.equity_edge, 1),
            "position": self.position,
            "position_modifier": round(self.position_modifier, 1),
            "estimated_ev": round(self.estimated_ev, 1),
            "actions": [a.to_dict() for a in self.actions],
            "top_action": self.top_action.to_dict() if self.top_action else None,
            "timing": self.timing,
        }


class Advisor:
    """
    Generates real-time advisory information for human players.
    """

    @staticmethod
    def analyze(
        hole_cards: List[Card],
        community: List[Card],
        pot: int,
        to_call: int,
        stack: int,
        position: str,
        num_opponents: int,
        valid_actions: dict,
        equity: Optional[EquityResult] = None,
    ) -> AdvisorResult:
        """
        Generate complete advisory analysis for a player's situation.
        """
        result = AdvisorResult()
        t_start = _time.perf_counter()

        # --- Hand evaluation ---
        t0 = _time.perf_counter()
        all_cards = hole_cards + community
        if community and len(all_cards) >= 5:
            hand_result = HandEvaluator.evaluate(all_cards)
            result.hand_name = hand_result.name
            result.hand_rank = hand_result.rank.name
            result.draw_description = HandEvaluator.describe_best_draw(hole_cards, community)
            result.best_hand_cards = [c.to_dict() for c in hand_result.cards]
        elif community and len(all_cards) >= 2:
            hand_result = HandEvaluator.evaluate(all_cards)
            result.hand_name = hand_result.name
            result.hand_rank = hand_result.rank.name
            result.draw_description = HandEvaluator.describe_best_draw(hole_cards, community)
            result.best_hand_cards = [c.to_dict() for c in hand_result.cards]
        elif len(hole_cards) == 2:
            c1, c2 = hole_cards
            result.hand_name = f"{RANK_DISPLAY[c1.rank]}{SUIT_SYMBOLS[c1.suit]} {RANK_DISPLAY[c2.rank]}{SUIT_SYMBOLS[c2.suit]}"
            result.hand_rank = "PREFLOP"
            result.draw_description = ""
            result.best_hand_cards = [c.to_dict() for c in hole_cards]
        result.timing["hand"] = round((_time.perf_counter() - t0) * 1000, 1)

        # --- Equity ---
        t0 = _time.perf_counter()
        if equity:
            result.equity = equity
        elif len(hole_cards) == 2:
            if not community:
                result.equity = EquityCalculator.preflop_equity(hole_cards, num_opponents)
            else:
                result.equity = EquityCalculator.monte_carlo(
                    hole_cards, community, num_opponents, simulations=3000
                )
        result.timing["equity"] = round((_time.perf_counter() - t0) * 1000, 1)

        win_pct = result.equity.win if result.equity else 50.0

        # --- Outs ---
        t0 = _time.perf_counter()
        if community and len(community) < 5:
            result.outs = Advisor._count_outs(hole_cards, community)
        result.timing["outs"] = round((_time.perf_counter() - t0) * 1000, 1)

        # --- Pot odds ---
        if to_call > 0 and (pot + to_call) > 0:
            result.pot_odds = (to_call / (pot + to_call)) * 100
            ratio = pot / to_call if to_call > 0 else 0
            result.pot_odds_ratio = f"{ratio:.1f}:1"
        else:
            result.pot_odds = 0
            result.pot_odds_ratio = "Free"

        # --- SPR (Stack-to-Pot Ratio) ---
        if pot > 0:
            result.spr = stack / pot
            if result.spr < 3:
                result.spr_label = "committed"
            elif result.spr < 8:
                result.spr_label = "medium"
            else:
                result.spr_label = "deep"
        else:
            result.spr = 99
            result.spr_label = "deep"

        # --- Equity edge ---
        result.equity_edge = win_pct - result.pot_odds

        # --- Position ---
        result.position = position
        result.position_modifier = {
            "BTN": 5, "CO": 3, "HJ": 1, "BTN/SB": 2,
            "SB": -2, "BB": 0, "UTG": -4, "UTG+1": -3,
            "MP": 0, "MP+1": 1,
        }.get(position, 0)

        # --- Implied odds (rough estimate) ---
        if to_call > 0:
            # Implied odds = (pot + expected future bets) / to_call
            future_bets = pot * 0.5 * (5 - len(community))  # Rough
            result.implied_odds = (pot + future_bets) / to_call
        else:
            result.implied_odds = 0

        # --- Fold equity estimate ---
        # Based on bet size relative to pot, position, and opponent tendencies
        result.fold_equity = Advisor._estimate_fold_equity(
            pot, to_call, position, num_opponents
        )

        # --- Action recommendations ---
        # When facing a bet, discount equity: opponent is NOT holding random cards.
        # The larger the bet and the later the street, the stronger their likely hand.
        # BUT: when pot-committed (low SPR), reduce the discount — folding is rarely
        # correct when you're getting extreme pot odds.
        action_equity = win_pct
        if to_call > 0 and len(community) > 0:
            bet_fraction = to_call / max(pot - to_call, 1)  # Bet relative to pot before their bet
            street_factor = len(community) / 5.0  # 0.6 on flop, 0.8 on turn, 1.0 on river

            # River bets are the most reliable signal — opponent has seen all cards
            if bet_fraction > 0.75:
                discount = 0.70 * street_factor  # Big bet: heavy discount
            elif bet_fraction > 0.4:
                discount = 0.50 * street_factor  # Medium bet: moderate discount
            elif bet_fraction > 0.2:
                discount = 0.30 * street_factor  # Small bet: light discount
            else:
                discount = 0.15 * street_factor  # Min bet: minimal discount

            # Reduce discount when pot-committed (low SPR)
            # SPR < 1: nearly all-in, discount barely applies (you're getting huge odds)
            # SPR 1-3: pot committed, halve the discount
            # SPR > 3: full discount
            if result.spr < 1:
                discount *= 0.2  # Almost irrelevant — you're priced in
            elif result.spr < 2:
                discount *= 0.4
            elif result.spr < 3:
                discount *= 0.65

            action_equity = win_pct * (1 - discount)
            # Floor: never discount below pot odds (otherwise fold is always right)
            action_equity = max(action_equity, result.pot_odds * 0.9)

        # Store adjusted equity so UI can show the discount
        if action_equity != win_pct:
            result.adjusted_equity = action_equity

        t0 = _time.perf_counter()
        result.actions = Advisor._rank_actions(
            action_equity, result.pot_odds, action_equity - result.pot_odds,
            result.spr, result.fold_equity, result.implied_odds,
            result.position_modifier, pot, to_call, stack,
            valid_actions, num_opponents, has_community=len(community) > 0
        )
        result.timing["actions"] = round((_time.perf_counter() - t0) * 1000, 1)

        if result.actions:
            result.top_action = result.actions[0]
            result.estimated_ev = result.actions[0].ev

        result.timing["total"] = round((_time.perf_counter() - t_start) * 1000, 1)
        return result

    @staticmethod
    def _count_outs(hole_cards: List[Card], community: List[Card]) -> OutsInfo:
        """
        Count outs for improving the hand.
        Checks for flush draws, straight draws, and pair-to-set draws.
        """
        all_cards = hole_cards + community
        current = HandEvaluator.evaluate(all_cards)
        
        # Cards already used
        used = set(all_cards)
        
        # All possible remaining cards
        remaining = [
            Card(r, Suit(s))
            for s in range(4) for r in range(2, 15)
            if Card(r, Suit(s)) not in used
        ]

        outs = 0
        draws = []

        # Count meaningful outs — cards that give YOU a better hand
        # Board pairings don't count: pairing a 3 on the board helps everyone equally
        # Only count: pairing hole cards, completing flushes/straights, improving to trips+
        improving_cards = []
        out_card_details = []  # {card info, makes: "Pair of Ks"}
        hole_ranks = set(c.rank for c in hole_cards)
        hole_suits = [c.suit for c in hole_cards]

        for card in remaining:
            test_cards = all_cards + [card]
            new_result = HandEvaluator.evaluate(test_cards)
            if new_result.rank <= current.rank:
                continue  # No rank improvement at all

            # Check if this card meaningfully helps US (not just the board)
            is_meaningful = False

            # Pairs or improves one of our hole cards
            if card.rank in hole_ranks:
                is_meaningful = True
            # Completes a flush with our suited hole cards
            elif card.suit in hole_suits:
                suit_count = sum(1 for c in all_cards if c.suit == card.suit)
                if suit_count >= 3:
                    is_meaningful = True
            # Makes two pair or better using at least one hole card
            elif new_result.rank.value >= 2:  # TWO_PAIR or better
                new_hand_ranks = [c.rank for c in new_result.cards] if hasattr(new_result, 'cards') and new_result.cards else []
                if any(r in new_hand_ranks for r in hole_ranks):
                    is_meaningful = True
            # Straight completions where our hole card matters
            elif new_result.rank == HandRank.STRAIGHT:
                is_meaningful = True

            if is_meaningful:
                improving_cards.append(card)
                out_card_details.append({
                    "short": card.short,
                    "display": f"{RANK_DISPLAY[card.rank]}{SUIT_SYMBOLS[card.suit]}",
                    "is_red": card.is_red,
                    "makes": new_result.name,
                    "rank_value": new_result.rank.value,
                })

        outs = len(improving_cards)

        # Sort by hand strength descending (flush > straight > trips > two pair > pair)
        out_card_details.sort(key=lambda x: (-x['rank_value'], x['display']))
        # Remove rank_value from output (internal sorting only)
        for oc in out_card_details:
            del oc['rank_value']

        # Identify draw types
        suit_counts = Counter(c.suit for c in all_cards)
        for suit, count in suit_counts.items():
            if count == 4:
                draws.append("Flush draw")
                break

        ranks = sorted(set(c.rank for c in all_cards))
        # Open-ended straight draw
        found_oesd = False
        for i in range(len(ranks) - 3):
            window = ranks[i:i+4]
            if window[-1] - window[0] == 3:
                draws.append("Open-ended straight draw")
                found_oesd = True
                break
        if not found_oesd:
            # Gutshot
            for i in range(len(ranks) - 3):
                window = ranks[i:i+4]
                if window[-1] - window[0] == 4:
                    draws.append("Gutshot straight draw")
                    break

        # Overcards
        if current.rank == HandRank.HIGH_CARD and community:
            board_high = max(c.rank for c in community)
            overcards = sum(1 for c in hole_cards if c.rank > board_high)
            if overcards == 1:
                draws.append("1 overcard")
            elif overcards > 1:
                draws.append(f"{overcards} overcards")

        # Calculate hit probabilities
        unseen = 52 - len(used)
        hit_turn = (outs / unseen * 100) if unseen > 0 else 0
        unseen_river = unseen - 1
        hit_river = (outs / unseen_river * 100) if unseen_river > 0 else 0

        # Probability of hitting by river (if on flop): 1 - (miss_turn * miss_river)
        if len(community) == 3:
            miss_turn = (unseen - outs) / unseen if unseen > 0 else 1
            miss_river = (unseen - 1 - outs) / (unseen - 1) if unseen > 1 else 1
            hit_either = (1 - miss_turn * miss_river) * 100
        else:
            hit_either = hit_turn  # Only one card to come

        # Add individual hit percentage per out card
        single_out_pct = (1.0 / unseen * 100) if unseen > 0 else 0
        for oc in out_card_details:
            oc["hit_pct"] = round(single_out_pct, 1)

        return OutsInfo(
            count=outs,
            draws=draws,
            hit_turn_pct=hit_turn,
            hit_river_pct=hit_river,
            hit_either_pct=hit_either,
            out_cards=out_card_details,
        )

    @staticmethod
    def _estimate_fold_equity(pot: int, to_call: int, position: str, num_opponents: int) -> float:
        """
        Rough fold equity estimate based on situation.
        
        Key insight: if to_call > 0, an opponent bet into us — they've shown
        strength and are much less likely to fold to a raise. Fold equity
        drops significantly when facing aggression.
        """
        base = 30.0
        # Late position = more fold equity
        pos_adj = {"BTN": 10, "CO": 5, "HJ": 2, "SB": -5, "BB": -3}.get(position, 0)
        # Fewer opponents = more fold equity
        opp_adj = max(0, (3 - num_opponents) * 8)

        raw = base + pos_adj + opp_adj

        # Facing a bet: opponent has shown strength — cut fold equity sharply
        if to_call > 0:
            # The larger the bet relative to pot, the stronger they are
            bet_fraction = to_call / max(pot, 1)
            if bet_fraction > 0.5:
                raw *= 0.3   # Big bet = very unlikely to fold
            elif bet_fraction > 0.25:
                raw *= 0.45  # Medium bet
            else:
                raw *= 0.6   # Small bet / min-raise

        return min(60, max(3, raw))

    @staticmethod
    def _rank_actions(
        equity, pot_odds, equity_edge, spr, fold_equity, implied_odds,
        position_mod, pot, to_call, stack, valid_actions, num_opponents,
        has_community=False
    ) -> List[ActionRecommendation]:
        """
        Rank available actions by incremental expected value.
        
        EV is displayed RELATIVE to folding (fold = 0). This means:
        - Positive EV = profitable compared to giving up
        - The EV represents marginal chip gain from the new chips being risked
        
        Fold is NEVER recommended over check (check is free).
        Semi-bluffs and bluffs are only offered post-flop (need community cards for draws).
        When nearly all-in (stack < pot/2), skip intermediate raise sizes.
        """
        recs = []
        actions = valid_actions.get("actions", [])
        check_available = any(a["action"] == "check" for a in actions)
        eq = equity / 100.0  # 0.0 to 1.0

        # Remaining stack (actual chips the player can still commit)
        remaining = stack
        # Detect nearly all-in: no room for meaningful raise sizing
        nearly_allin = remaining > 0 and (remaining < to_call * 2 or spr < 1.5)

        for action_info in actions:
            action = action_info["action"]

            if action == "fold":
                # Fold EV = 0 (baseline — you risk nothing more, gain nothing)
                ev = 0
                if check_available:
                    score = 1
                    label = "Unnecessary"
                    reasoning = "You can check for free"
                else:
                    score = max(5, min(50, (100 - equity) * 0.5))
                    label = "Give Up" if equity < 25 else "Fold"
                    reasoning = f"Equity ({equity:.0f}%) vs pot odds ({pot_odds:.0f}%)"
                recs.append(ActionRecommendation(action, score, ev, label, reasoning))

            elif action == "check":
                # Check EV must account for imperfect equity realization:
                # - Checking gives opponents free cards to improve
                # - You miss value extraction from worse hands
                # Standard equity realization for checks is ~65-80%
                # Higher equity = more value missed by not betting
                if eq > 0.65:
                    # Strong hands lose the most by checking (missed value)
                    realization = 0.65
                elif eq > 0.45:
                    # Medium hands realize reasonably well by checking
                    realization = 0.75
                else:
                    # Weak hands benefit most from free cards
                    realization = 0.85
                ev = eq * pot * realization
                score = max(30, min(80, 30 + equity * 0.5))
                if equity > 85:
                    label = "Check"
                    reasoning = "Free card — but consider betting for value"
                elif equity > 55:
                    label = "Check"
                    reasoning = "Free card with decent equity"
                else:
                    label = "Check"
                    reasoning = "No cost to see next card"
                recs.append(ActionRecommendation(action, score, ev, label, reasoning))

            elif action == "call":
                call_amt = action_info.get("amount", to_call)
                if call_amt <= 0:
                    continue
                # Incremental EV: what you gain by calling vs folding
                # EV = equity * (pot + call) - call
                # This is the expected profit from investing 'call' chips
                ev = eq * (pot + call_amt) - call_amt
                if ev > 0:
                    if equity_edge > 15:
                        label = "Strong Call"
                    else:
                        label = "Profitable Call"
                    reasoning = f"Equity {equity:.0f}% vs {pot_odds:.0f}% needed"
                else:
                    label = "Speculative Call"
                    reasoning = f"Equity {equity:.0f}% below {pot_odds:.0f}% needed"
                    if implied_odds > 3:
                        label = "Drawing Call"
                        reasoning += f" (implied odds {implied_odds:.1f}:1)"
                score = max(10, min(85, 50 + ev / max(pot, 1) * 100))
                recs.append(ActionRecommendation(action, score, ev, label, reasoning))

            elif action in ("bet", "raise"):
                min_bet = action_info.get("min", 0)
                max_bet = action_info.get("max", remaining)

                # Hard clamp: can't bet more than remaining stack
                max_bet = min(max_bet, remaining + (valid_actions.get("player_current_bet", 0)))
                actual_max_new_chips = remaining  # Max NEW chips we can put in

                # If nearly all-in, only offer all-in (skip intermediate sizes)
                if nearly_allin and actual_max_new_chips > 0:
                    # All-in is the only raise option when short
                    additional = actual_max_new_chips
                    ev_allin = eq * (pot + additional) - additional
                    if ev_allin > 0 or spr < 1.5:
                        label = "All-In" if spr < 1.5 else "All-In (Value)"
                        reasoning = f"Short-stacked (SPR {spr:.1f})" if spr < 3 else f"Strong equity ({equity:.0f}%)"
                        score = max(40, min(90, 50 + ev_allin / max(pot, 1) * 80))
                        recs.append(ActionRecommendation(
                            action, score, ev_allin, label, reasoning,
                            bet_range=(max_bet, max_bet), bet_type="value",
                        ))
                    continue

                # Value bet/raise: strong equity
                if equity > 55:
                    # Bet sizing as fraction of pot, clamped to stack
                    new_chips_lo = min(actual_max_new_chips, max(int(pot * 0.4), min_bet - valid_actions.get("player_current_bet", 0)))
                    new_chips_hi = min(actual_max_new_chips, max(int(pot * 0.75), new_chips_lo))
                    avg_new = max(1, (new_chips_lo + new_chips_hi) // 2)
                    # EV = equity * (pot + new_chips) - new_chips
                    ev_val = eq * (pot + avg_new) - avg_new
                    score = max(50, min(90, 50 + ev_val / max(pot, 1) * 80))
                    bet_lo_total = valid_actions.get("player_current_bet", 0) + new_chips_lo
                    bet_hi_total = valid_actions.get("player_current_bet", 0) + new_chips_hi
                    bet_lo_total = max(min_bet, bet_lo_total)
                    bet_hi_total = min(max_bet, bet_hi_total)
                    recs.append(ActionRecommendation(
                        action, score, ev_val,
                        "Value Bet" if action == "bet" else "Value Raise",
                        f"Equity {equity:.0f}% — extract value",
                        bet_range=(bet_lo_total, bet_hi_total), bet_type="value",
                    ))

                # Semi-bluff: only post-flop, only if the math actually works out
                # Lower equity requires higher fold equity to be profitable
                min_fold_eq = max(25, 60 - equity)  # e.g., 25% equity needs 35% fold equity
                if has_community and 25 < equity < 60 and fold_equity > min_fold_eq:
                    new_chips = min(actual_max_new_chips, max(int(pot * 0.45), 1))
                    ev_semi = (fold_equity / 100) * pot + (1 - fold_equity / 100) * (eq * (pot + new_chips) - new_chips)
                    # Only recommend if EV is actually positive
                    if ev_semi > 0:
                        score = max(30, min(70, 30 + ev_semi / max(pot, 1) * 80))
                        bet_total = max(min_bet, min(max_bet, valid_actions.get("player_current_bet", 0) + new_chips))
                        recs.append(ActionRecommendation(
                            action, score, ev_semi, "Semi-Bluff",
                            f"Fold equity {fold_equity:.0f}% + draw equity {equity:.0f}%",
                            bet_range=(bet_total, min(max_bet, bet_total + int(pot * 0.2))),
                            bet_type="semi_bluff",
                        ))

                # Bluff: only post-flop (preflop bluffs need range-based logic we don't have)
                if has_community and equity < 30 and fold_equity > 35 and spr > 3:
                    new_chips = min(actual_max_new_chips, max(int(pot * 0.5), 1))
                    ev_bluff = (fold_equity / 100) * pot - (1 - fold_equity / 100) * new_chips
                    if ev_bluff > 0:
                        score = max(10, fold_equity * 0.4)
                        bet_total = max(min_bet, min(max_bet, valid_actions.get("player_current_bet", 0) + new_chips))
                        recs.append(ActionRecommendation(
                            action, score, ev_bluff, "Bluff",
                            f"Fold equity {fold_equity:.0f}% makes bluff profitable",
                            bet_range=(bet_total, min(max_bet, bet_total + int(pot * 0.15))),
                            bet_type="bluff",
                        ))

                # All-in (when not nearly_allin but pot-committed or premium)
                if actual_max_new_chips > 0 and not nearly_allin and (spr < 3 or equity > 80):
                    ev_allin = eq * (pot + actual_max_new_chips) - actual_max_new_chips
                    if ev_allin > 0:
                        label = "All-In (Committed)" if spr < 3 else "All-In (Value)"
                        reasoning = f"SPR {spr:.1f} — pot committed" if spr < 3 else f"Premium equity {equity:.0f}%"
                        score = max(40, min(95, 50 + ev_allin / max(pot, 1) * 80))
                        recs.append(ActionRecommendation(
                            action, score, ev_allin, label, reasoning,
                            bet_range=(max_bet, max_bet), bet_type="value",
                        ))

        # Sort by EV descending
        recs.sort(key=lambda r: (r.ev, r.score), reverse=True)

        # Normalize score bars to 0-100 relative to best EV
        if recs:
            max_ev = max(r.ev for r in recs)
            min_ev = min(r.ev for r in recs)
            ev_range = max_ev - min_ev if max_ev != min_ev else 1
            for r in recs:
                r.score = max(5, ((r.ev - min_ev) / ev_range) * 90 + 10)
            recs[0].score = 100

        return recs
