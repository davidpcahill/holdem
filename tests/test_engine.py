"""
Test suite for Card, Deck, and HandEvaluator.

Run with: python -m pytest tests/test_engine.py -v
Or: python tests/test_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.deck import Card, Deck, Suit, make_card
from engine.hand_eval import HandEvaluator, HandRank


def c(s: str) -> Card:
    """Shorthand card constructor: c('As') = Ace of Spades."""
    return Card.from_short(s)


# ========================================================================
# Card Tests
# ========================================================================

def test_card_creation():
    card = Card(14, Suit.SPADES)
    assert card.rank == 14
    assert card.suit == Suit.SPADES
    assert str(card) == "A♠"
    assert card.short == "As"
    assert card.is_red is False

def test_card_from_short():
    assert c("As") == Card(14, Suit.SPADES)
    assert c("Th") == Card(10, Suit.HEARTS)
    assert c("2c") == Card(2, Suit.CLUBS)
    assert c("Kd") == Card(13, Suit.DIAMONDS)

def test_card_immutability():
    card = c("As")
    try:
        card.rank = 10
        assert False, "Should have raised"
    except AttributeError:
        pass

def test_card_equality_and_hash():
    a = c("As")
    b = c("As")
    assert a == b
    assert hash(a) == hash(b)
    assert a != c("Ah")
    assert len({a, b}) == 1

def test_card_red_suits():
    assert c("Ah").is_red is True
    assert c("Ad").is_red is True
    assert c("As").is_red is False
    assert c("Ac").is_red is False


# ========================================================================
# Deck Tests
# ========================================================================

def test_deck_52_cards():
    deck = Deck(shuffle=False)
    assert len(deck) == 52
    # All cards unique
    all_cards = deck.available_cards()
    assert len(set(all_cards)) == 52

def test_deck_draw():
    deck = Deck(seed=42)
    cards = deck.draw(2)
    assert len(cards) == 2
    assert len(deck) == 50

def test_deck_burn():
    deck = Deck(seed=42)
    burned = deck.burn()
    assert len(deck) == 51
    assert len(deck.burned) == 1
    assert burned == deck.burned[0]

def test_deck_remove_specific():
    deck = Deck(shuffle=False)
    ace_spades = c("As")
    assert deck.is_available(ace_spades)
    assert deck.remove(ace_spades) is True
    assert deck.is_available(ace_spades) is False
    assert len(deck) == 51
    # Double remove fails
    assert deck.remove(ace_spades) is False

def test_deck_seeded_reproducibility():
    d1 = Deck(seed=123)
    d2 = Deck(seed=123)
    c1 = d1.draw(5)
    c2 = d2.draw(5)
    assert c1 == c2


# ========================================================================
# Hand Evaluation - Individual Hand Types
# ========================================================================

def test_royal_flush():
    cards = [c("As"), c("Ks"), c("Qs"), c("Js"), c("Ts")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.ROYAL_FLUSH
    assert "Royal Flush" in result.name

def test_straight_flush():
    cards = [c("9h"), c("8h"), c("7h"), c("6h"), c("5h")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT_FLUSH
    assert "9" in result.name

def test_straight_flush_wheel():
    """A-2-3-4-5 of same suit = straight flush, 5 high."""
    cards = [c("Ah"), c("2h"), c("3h"), c("4h"), c("5h")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT_FLUSH
    assert result.score == (HandRank.STRAIGHT_FLUSH, 5)

def test_four_of_a_kind():
    cards = [c("Ks"), c("Kh"), c("Kd"), c("Kc"), c("7s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FOUR_OF_A_KIND
    assert result.kickers[0] == 13  # Kings

def test_full_house():
    cards = [c("Jh"), c("Js"), c("Jd"), c("4c"), c("4s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FULL_HOUSE
    assert result.kickers == (11, 4)

def test_flush():
    cards = [c("Ad"), c("Td"), c("7d"), c("4d"), c("2d")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FLUSH
    assert result.kickers[0] == 14

def test_straight_normal():
    cards = [c("Ts"), c("9h"), c("8d"), c("7c"), c("6s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT
    assert result.score == (HandRank.STRAIGHT, 10)

def test_straight_wheel():
    """A-2-3-4-5 = straight, 5 high (ace plays low)."""
    cards = [c("As"), c("2h"), c("3d"), c("4c"), c("5s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT
    assert result.score == (HandRank.STRAIGHT, 5)

def test_straight_broadway():
    """A-K-Q-J-T = straight, ace high."""
    cards = [c("As"), c("Kh"), c("Qd"), c("Jc"), c("Ts")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT
    assert result.score == (HandRank.STRAIGHT, 14)

def test_three_of_a_kind():
    cards = [c("8s"), c("8h"), c("8d"), c("Kc"), c("3s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.THREE_OF_A_KIND
    assert result.kickers[0] == 8

def test_two_pair():
    cards = [c("As"), c("Ah"), c("Kd"), c("Kc"), c("5s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.TWO_PAIR
    assert result.kickers == (14, 13, 5)

def test_one_pair():
    cards = [c("9s"), c("9h"), c("Ad"), c("7c"), c("3s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.ONE_PAIR
    assert result.kickers[0] == 9

def test_high_card():
    cards = [c("Ad"), c("Jh"), c("8s"), c("5c"), c("2d")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.HIGH_CARD
    assert result.kickers[0] == 14


# ========================================================================
# 7-Card Evaluation (Best of 21 combinations)
# ========================================================================

def test_seven_card_finds_flush():
    """7 cards with flush buried among non-flush cards."""
    cards = [c("Ah"), c("Kh"), c("7h"), c("3h"), c("2h"), c("Qs"), c("Jd")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FLUSH

def test_seven_card_finds_straight():
    """Straight with extra high cards."""
    cards = [c("As"), c("Kh"), c("8d"), c("7c"), c("6s"), c("5h"), c("4d")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.STRAIGHT
    assert result.score == (HandRank.STRAIGHT, 8)

def test_seven_card_full_house_over_flush():
    """Full house beats a possible flush in the same 7 cards."""
    cards = [c("Jh"), c("Jd"), c("Js"), c("4h"), c("4d"), c("8h"), c("2h")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FULL_HOUSE

def test_seven_card_best_two_pair():
    """Three pairs in 7 cards — should pick the two highest pairs."""
    cards = [c("As"), c("Ah"), c("Kd"), c("Kc"), c("5s"), c("5h"), c("2d")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.TWO_PAIR
    # Best two pair is AA and KK with 5 kicker
    assert result.kickers == (14, 13, 5)

def test_seven_card_quads_with_better_kicker():
    """Four of a kind — should pick the best kicker from remaining 3."""
    cards = [c("9s"), c("9h"), c("9d"), c("9c"), c("As"), c("Kh"), c("2d")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank == HandRank.FOUR_OF_A_KIND
    assert result.kickers == (9, 14)  # Ace kicker, not K or 2


# ========================================================================
# Hand Comparison / Tiebreakers
# ========================================================================

def test_higher_pair_wins():
    aa = HandEvaluator.evaluate([c("As"), c("Ah"), c("7d"), c("4c"), c("2s")])
    kk = HandEvaluator.evaluate([c("Ks"), c("Kh"), c("7d"), c("4c"), c("2s")])
    assert aa.beats(kk)
    assert not kk.beats(aa)

def test_same_pair_kicker_breaks_tie():
    hand_a = HandEvaluator.evaluate([c("As"), c("Ah"), c("Kd"), c("7c"), c("3s")])
    hand_b = HandEvaluator.evaluate([c("Ad"), c("Ac"), c("Qd"), c("7c"), c("3s")])
    assert hand_a.beats(hand_b)  # K kicker > Q kicker

def test_flush_kicker_comparison():
    """Two flushes — compare rank by rank."""
    flush_a = HandEvaluator.evaluate([c("Ah"), c("Kh"), c("9h"), c("5h"), c("2h")])
    flush_b = HandEvaluator.evaluate([c("Ad"), c("Kd"), c("9d"), c("4d"), c("2d")])
    assert flush_a.beats(flush_b)  # 5 > 4

def test_identical_hands_tie():
    """Same ranks different suits = tie in poker."""
    hand_a = HandEvaluator.evaluate([c("As"), c("Kh"), c("8d"), c("5c"), c("2s")])
    hand_b = HandEvaluator.evaluate([c("Ah"), c("Kd"), c("8s"), c("5h"), c("2d")])
    assert hand_a.ties(hand_b)

def test_straight_vs_straight():
    high = HandEvaluator.evaluate([c("Ts"), c("9h"), c("8d"), c("7c"), c("6s")])
    low = HandEvaluator.evaluate([c("9s"), c("8h"), c("7d"), c("6c"), c("5s")])
    assert high.beats(low)

def test_wheel_is_lowest_straight():
    wheel = HandEvaluator.evaluate([c("As"), c("2h"), c("3d"), c("4c"), c("5s")])
    six_high = HandEvaluator.evaluate([c("6s"), c("5h"), c("4d"), c("3c"), c("2s")])
    assert six_high.beats(wheel)

def test_full_house_comparison():
    """Higher trips wins, regardless of pair."""
    fh_high = HandEvaluator.evaluate([c("Ks"), c("Kh"), c("Kd"), c("2c"), c("2s")])
    fh_low = HandEvaluator.evaluate([c("Qs"), c("Qh"), c("Qd"), c("As"), c("Ah")])
    assert fh_high.beats(fh_low)

def test_two_pair_high_pair_wins():
    tp_high = HandEvaluator.evaluate([c("As"), c("Ah"), c("3d"), c("3c"), c("7s")])
    tp_low = HandEvaluator.evaluate([c("Ks"), c("Kh"), c("Qd"), c("Qc"), c("As")])
    assert tp_high.beats(tp_low)


# ========================================================================
# find_winners
# ========================================================================

def test_find_single_winner():
    hands = [
        (0, HandEvaluator.evaluate([c("As"), c("Ah"), c("Kd"), c("7c"), c("3s")])),
        (1, HandEvaluator.evaluate([c("Ks"), c("Kh"), c("Qd"), c("7c"), c("3s")])),
    ]
    winners = HandEvaluator.find_winners(hands)
    assert winners == [0]

def test_find_tied_winners():
    # Same hand, different suits
    hands = [
        (0, HandEvaluator.evaluate([c("As"), c("Kh"), c("8d"), c("5c"), c("2s")])),
        (1, HandEvaluator.evaluate([c("Ah"), c("Kd"), c("8s"), c("5h"), c("2d")])),
    ]
    winners = HandEvaluator.find_winners(hands)
    assert sorted(winners) == [0, 1]


# ========================================================================
# Score-only fast path (used in Monte Carlo)
# ========================================================================

def test_score_only_matches_full_eval():
    """Verify fast score path produces same result as full evaluation."""
    test_hands = [
        [c("As"), c("Ks"), c("Qs"), c("Js"), c("Ts")],                # Royal
        [c("9h"), c("8h"), c("7h"), c("6h"), c("5h")],                # SF
        [c("As"), c("2h"), c("3d"), c("4c"), c("5s")],                # Wheel
        [c("Ks"), c("Kh"), c("Kd"), c("Kc"), c("7s")],               # Quads
        [c("Jh"), c("Js"), c("Jd"), c("4c"), c("4s")],               # FH
        [c("Ad"), c("Td"), c("7d"), c("4d"), c("2d")],               # Flush
        [c("Ts"), c("9h"), c("8d"), c("7c"), c("6s")],               # Straight
        [c("8s"), c("8h"), c("8d"), c("Kc"), c("3s")],               # Trips
        [c("As"), c("Ah"), c("Kd"), c("Kc"), c("5s")],               # Two pair
        [c("9s"), c("9h"), c("Ad"), c("7c"), c("3s")],               # Pair
        [c("Ad"), c("Jh"), c("8s"), c("5c"), c("2d")],               # High card
    ]
    for cards in test_hands:
        full = HandEvaluator.evaluate(cards)
        fast = HandEvaluator.evaluate_score(cards)
        assert full.score == fast, f"Mismatch for {[str(c) for c in cards]}: {full.score} vs {fast}"

def test_score_seven_card():
    """Seven-card fast score path."""
    cards = [c("As"), c("Ah"), c("Kh"), c("Kd"), c("7c"), c("3s"), c("2d")]
    full = HandEvaluator.evaluate(cards)
    fast = HandEvaluator.evaluate_score(cards)
    assert full.score == fast


# ========================================================================
# Edge cases
# ========================================================================

def test_two_card_eval():
    """Preflop: just hole cards."""
    result = HandEvaluator.evaluate([c("As"), c("Kh")])
    assert result.rank == HandRank.HIGH_CARD

def test_two_card_pair():
    result = HandEvaluator.evaluate([c("As"), c("Ah")])
    assert result.rank == HandRank.ONE_PAIR

def test_ace_not_wrapping():
    """K-A-2-3-4 is NOT a straight (ace doesn't wrap)."""
    cards = [c("Ks"), c("Ah"), c("2d"), c("3c"), c("4s")]
    result = HandEvaluator.evaluate(cards)
    assert result.rank != HandRank.STRAIGHT

def test_describe_best_draw():
    """Test the draw description helper."""
    # Flush draw on flop
    hole = [c("Ah"), c("Kh")]
    community = [c("7h"), c("3h"), c("Ts")]
    desc = HandEvaluator.describe_best_draw(hole, community)
    assert "Flush draw" in desc


# ========================================================================
# Equity Calculator
# ========================================================================

def test_preflop_equity_pocket_aces():
    """Pocket aces should have 80-90% equity heads-up."""
    from engine.equity import EquityCalculator
    aa = [Card.from_short("As"), Card.from_short("Ah")]
    result = EquityCalculator.preflop_equity(aa, num_opponents=1)
    assert 80 <= result.win <= 90, f"AA equity {result.win}% not in expected range"
    assert result.is_preflop is True


def test_preflop_equity_ordering():
    """AA should beat KK should beat 72o in preflop equity."""
    from engine.equity import EquityCalculator
    aa = [Card.from_short("As"), Card.from_short("Ah")]
    kk = [Card.from_short("Ks"), Card.from_short("Kh")]
    low = [Card.from_short("7s"), Card.from_short("2h")]
    eq_aa = EquityCalculator.preflop_equity(aa, 1).win
    eq_kk = EquityCalculator.preflop_equity(kk, 1).win
    eq_low = EquityCalculator.preflop_equity(low, 1).win
    assert eq_aa > eq_kk > eq_low, f"Ordering wrong: AA={eq_aa} KK={eq_kk} 72o={eq_low}"


def test_monte_carlo_sum_to_100():
    """Monte Carlo win + tie + loss should sum to ~100%."""
    from engine.equity import EquityCalculator
    hole = [Card.from_short("As"), Card.from_short("Kh")]
    community = [Card.from_short("Qs"), Card.from_short("Jd"), Card.from_short("2c")]
    result = EquityCalculator.monte_carlo(hole, community, num_opponents=1, simulations=1000)
    total = result.win + result.tie + result.loss
    assert 99.0 <= total <= 101.0, f"Sum {total}% not ~100%"


def test_monte_carlo_strong_hand():
    """Top set on rainbow flop should have >80% equity heads-up."""
    from engine.equity import EquityCalculator
    hole = [Card.from_short("Qs"), Card.from_short("Qh")]
    community = [Card.from_short("Qd"), Card.from_short("7c"), Card.from_short("2s")]
    result = EquityCalculator.monte_carlo(hole, community, num_opponents=1, simulations=2000)
    assert result.win > 80, f"Top set equity {result.win}% should be >80%"


def test_preflop_equity_multiway():
    """Equity should decrease with more opponents."""
    from engine.equity import EquityCalculator
    hand = [Card.from_short("As"), Card.from_short("Kh")]
    eq_1 = EquityCalculator.preflop_equity(hand, 1).win
    eq_3 = EquityCalculator.preflop_equity(hand, 3).win
    eq_5 = EquityCalculator.preflop_equity(hand, 5).win
    assert eq_1 > eq_3 > eq_5, f"Equity should decrease: 1={eq_1} 3={eq_3} 5={eq_5}"


# ========================================================================
# ========================================================================
# Preflop Range Charts
# ========================================================================

def test_range_grid_dimensions():
    """Range grid is 13×13 with correct cell structure."""
    from engine.ranges import get_range_grid
    grid = get_range_grid("BTN")
    assert len(grid) == 13
    for row in grid:
        assert len(row) == 13
    cell = grid[0][0]
    assert "hand" in cell
    assert "equity" in cell
    assert "action" in cell
    assert cell["hand"] == "AA"


def test_range_grid_actions():
    """Range grid has raise/call/fold actions based on position."""
    from engine.ranges import get_range_grid
    grid = get_range_grid("BTN")
    # AA should always be raise from any position
    assert grid[0][0]["action"] == "raise"
    # Weak hand should be fold
    assert grid[12][11]["action"] == "fold"  # 32o


def test_range_positions_differ():
    """Different positions produce different grids (tighter UTG)."""
    from engine.ranges import get_range_grid
    utg = get_range_grid("UTG")
    btn = get_range_grid("BTN")
    utg_raises = sum(1 for r in utg for c in r if c["action"] == "raise")
    btn_raises = sum(1 for r in btn for c in r if c["action"] == "raise")
    assert btn_raises > utg_raises, "BTN should have more raises than UTG"


def test_hand_key_mapping():
    """hand_key correctly maps grid positions to hand names."""
    from engine.ranges import hand_key
    assert hand_key(0, 0) == "AA"     # Diagonal = pair
    assert hand_key(0, 1) == "AKs"    # Above diagonal = suited
    assert hand_key(1, 0) == "AKo"    # Below diagonal = offsuit
    assert hand_key(12, 12) == "22"   # Last pair


def test_all_positions_exist():
    """All standard positions are available."""
    from engine.ranges import get_all_positions
    positions = get_all_positions()
    assert len(positions) >= 8
    assert "BTN" in positions
    assert "UTG" in positions
    assert "BB" in positions


# ========================================================================
# Tutorial Tests
# ========================================================================

def test_tutorial_tip_first_always():
    """First unseen concept with 'always' trigger is returned."""
    from engine.tutorial import get_tutorial_tip
    tip = get_tutorial_tip({"equity": {"win": 50}}, "preflop", "BTN", 1, [])
    assert tip is not None
    assert tip["id"] == "hand_strength"
    assert "title" in tip
    assert "explanation" in tip


def test_tutorial_tip_skips_seen():
    """Concepts already in seen_concepts are skipped."""
    from engine.tutorial import get_tutorial_tip
    tip = get_tutorial_tip(
        {"equity": {"win": 50}}, "preflop", "BTN", 1, ["hand_strength"]
    )
    assert tip is not None
    assert tip["id"] == "position"  # Next concept that matches


def test_tutorial_tip_none_when_all_seen():
    """Returns None when all concepts have been seen."""
    from engine.tutorial import get_tutorial_tip, TUTORIAL_CONCEPTS
    all_ids = [c["id"] for c in TUTORIAL_CONCEPTS]
    tip = get_tutorial_tip({"equity": {"win": 50}}, "preflop", "BTN", 1, all_ids)
    assert tip is None


def test_tutorial_tip_none_without_advisor():
    """Returns None when advisor_result is None."""
    from engine.tutorial import get_tutorial_tip
    tip = get_tutorial_tip(None, "preflop", "BTN", 1, [])
    assert tip is None


def test_tutorial_tip_pot_odds_trigger():
    """Pot odds concept triggers when facing a bet."""
    from engine.tutorial import get_tutorial_tip
    seen = ["hand_strength", "position"]
    tip = get_tutorial_tip(
        {"pot_odds": 16.7, "equity": {"win": 40}}, "flop", "BTN", 3, seen
    )
    assert tip is not None
    assert tip["id"] == "pot_odds"


def test_tutorial_tip_outs_trigger():
    """Outs concept triggers when outs count > 0."""
    from engine.tutorial import get_tutorial_tip
    seen = ["hand_strength", "position", "pot_odds"]
    tip = get_tutorial_tip(
        {"outs": {"count": 9, "draws": ["flush draw"]}}, "flop", "CO", 4, seen
    )
    assert tip is not None
    assert tip["id"] == "outs"


def test_tutorial_concepts_have_required_fields():
    """Every concept has id, title, explanation, and trigger."""
    from engine.tutorial import TUTORIAL_CONCEPTS
    for concept in TUTORIAL_CONCEPTS:
        assert "id" in concept, f"Missing id in concept"
        assert "title" in concept, f"Missing title in {concept['id']}"
        assert "explanation" in concept, f"Missing explanation in {concept['id']}"
        assert "trigger" in concept, f"Missing trigger in {concept['id']}"


# Runner
# ========================================================================

if __name__ == "__main__":
    test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    else:
        print("All tests passed.")
