"""
Tutorial system for Texas Hold'em.

Provides contextual tips that teach poker concepts progressively
based on the current game situation and advisor analysis.
"""

from __future__ import annotations
from typing import Optional

# Ordered list of poker concepts for progressive teaching.
# Each concept has conditions under which it's most relevant.
TUTORIAL_CONCEPTS = [
    {
        "id": "hand_strength",
        "title": "Hand Strength",
        "explanation": (
            "Your hand strength is shown as 'Equity' — the percentage chance "
            "you'll win if the hand goes to showdown. Premium hands like AA, KK, "
            "AKs have 65-85% equity heads-up. Mid-range hands (55-65%) are "
            "playable but need caution. Below 45% is usually a fold unless you're "
            "getting good pot odds."
        ),
        "trigger": "always",  # Show early to establish baseline
    },
    {
        "id": "position",
        "title": "Position Matters",
        "explanation": (
            "Acting last (Button/CO) is a huge advantage — you see what everyone "
            "else does before deciding. The Advisor shows a position modifier: "
            "positive from late position, negative from early. Play tighter from "
            "UTG/SB and looser from BTN/CO."
        ),
        "trigger": "has_position",
    },
    {
        "id": "pot_odds",
        "title": "Pot Odds",
        "explanation": (
            "Pot Odds tell you the minimum equity needed to call profitably. "
            "If the pot is $100 and you need to call $20, pot odds are 20/(100+20) = "
            "16.7%. If your equity is higher than that, calling is profitable long-term. "
            "The Edge stat shows equity minus pot odds — positive means +EV."
        ),
        "trigger": "facing_bet",
    },
    {
        "id": "outs",
        "title": "Counting Outs",
        "explanation": (
            "Outs are cards that improve your hand. A flush draw has 9 outs, "
            "an open-ended straight draw has 8, and a gutshot has 4. "
            "Quick math: multiply outs by 2 for one card, by 4 for two cards "
            "remaining. 9 outs × 4 = ~36% chance of hitting by the river."
        ),
        "trigger": "has_outs",
    },
    {
        "id": "spr",
        "title": "Stack-to-Pot Ratio (SPR)",
        "explanation": (
            "SPR = your stack ÷ pot size. Low SPR (<3) means you're pot-committed "
            "— it rarely makes sense to fold. Medium SPR (3-8) is normal play. "
            "High SPR (>8) means deep stacks where you can be more speculative "
            "with drawing hands."
        ),
        "trigger": "has_spr",
    },
    {
        "id": "fold_equity",
        "title": "Fold Equity",
        "explanation": (
            "Fold Equity is the chance your opponents fold when you bet. "
            "Even with a weak hand, a bet can be profitable if fold equity "
            "is high enough. This is the basis of bluffing — you don't always "
            "need the best hand if opponents fold often enough."
        ),
        "trigger": "can_raise",
    },
    {
        "id": "ev_actions",
        "title": "Expected Value (EV)",
        "explanation": (
            "Each recommended action has an EV number. Positive EV means the "
            "action is profitable on average. The star (★) marks the best action. "
            "Always prefer the highest EV option. EV = (equity × pot gained) "
            "minus cost. Fold is always EV 0 (baseline)."
        ),
        "trigger": "has_actions",
    },
    {
        "id": "bet_sizing",
        "title": "Bet Sizing",
        "explanation": (
            "The Advisor suggests bet sizes labeled Value, Semi-Bluff, or Bluff. "
            "Value bets (60-80% pot) extract chips when you have the best hand. "
            "Semi-bluffs (40-60% pot) apply pressure with drawing hands. "
            "Bluffs work best with 50-75% pot sizing to risk less."
        ),
        "trigger": "can_raise",
    },
    {
        "id": "bluffing",
        "title": "When to Bluff",
        "explanation": (
            "Good bluff spots: you're in late position, the board is scary "
            "(possible straights/flushes), your opponent seems tight (high fold equity), "
            "and the pot is small relative to the bet. "
            "Bad bluff spots: multi-way pots, loose opponents, dry boards."
        ),
        "trigger": "low_equity_can_raise",
    },
    {
        "id": "preflop_ranges",
        "title": "Preflop Hand Selection",
        "explanation": (
            "Not all starting hands are created equal. Check the Preflop Ranges "
            "chart (bottom of Advisor tab) to see which hands to play from each "
            "position. Green = raise, yellow = call, red = fold. "
            "Discipline to fold bad hands preflop is the #1 skill for beginners."
        ),
        "trigger": "preflop",
    },
]


def get_tutorial_tip(
    advisor_result: Optional[dict],
    street: str,
    position: str,
    hand_number: int,
    seen_concepts: list,
) -> Optional[dict]:
    """
    Pick the most relevant tutorial tip for the current situation.

    Returns dict with {id, title, explanation} or None if no tip is relevant.
    Skips concepts already in seen_concepts.
    """
    if not advisor_result:
        return None

    for concept in TUTORIAL_CONCEPTS:
        if concept["id"] in seen_concepts:
            continue

        trigger = concept["trigger"]

        if trigger == "always":
            return _format_tip(concept)

        if trigger == "has_position" and position:
            return _format_tip(concept)

        if trigger == "facing_bet" and advisor_result.get("pot_odds", 0) > 0:
            return _format_tip(concept)

        if trigger == "has_outs":
            outs = advisor_result.get("outs", {})
            if isinstance(outs, dict) and outs.get("count", 0) > 0:
                return _format_tip(concept)

        if trigger == "has_spr" and advisor_result.get("spr") is not None:
            return _format_tip(concept)

        if trigger == "can_raise":
            actions = advisor_result.get("actions", [])
            if any(a.get("action") in ("raise", "bet") for a in actions):
                return _format_tip(concept)

        if trigger == "has_actions" and advisor_result.get("actions"):
            return _format_tip(concept)

        if trigger == "low_equity_can_raise":
            eq = advisor_result.get("equity", {})
            win = eq.get("win", 50) if isinstance(eq, dict) else 50
            actions = advisor_result.get("actions", [])
            if win < 40 and any(a.get("action") in ("raise", "bet") for a in actions):
                return _format_tip(concept)

        if trigger == "preflop" and street == "preflop":
            return _format_tip(concept)

    return None


def _format_tip(concept: dict) -> dict:
    return {
        "id": concept["id"],
        "title": concept["title"],
        "explanation": concept["explanation"],
    }
