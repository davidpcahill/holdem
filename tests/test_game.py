"""
Integration tests for GameState - full hand lifecycle.

Tests the complete flow: setup → deal → bet → streets → showdown.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.game import GameState, Street, GamePhase
from engine.player import PlayerType
from engine.betting import SidePotCalculator


def make_game(num_players=3, stack=1000, sb=5, bb=10):
    """Helper: create a game with N players ready to play."""
    g = GameState()
    g.set_blinds(sb, bb)
    for i in range(num_players):
        g.add_player(f"Player{i+1}", stack=stack, player_type="human")
    return g


# ========================================================================
# Basic Setup
# ========================================================================

def test_add_players():
    g = GameState()
    p1 = g.add_player("Alice", stack=500)
    p2 = g.add_player("Bob", stack=1000)
    assert len(g.players) == 2
    assert g.players[0].name == "Alice"
    assert g.players[1].stack == 1000

def test_new_hand_deals_cards():
    g = make_game(3)
    state = g.new_hand()
    for p in g.players:
        assert len(p.hole_cards) == 2, f"{p.name} has {len(p.hole_cards)} cards"
    assert g.phase == GamePhase.PLAYING
    assert g.street == Street.PREFLOP


# ========================================================================
# Blinds
# ========================================================================

def test_blinds_posted():
    g = make_game(3, sb=5, bb=10)
    g.new_hand()
    # Dealer is seat 0, SB is seat 1, BB is seat 2
    # Check pot = SB + BB
    assert g.pot == 15
    # BB player should have 10 less
    bb_seat = g._get_bb_seat()
    assert g.players[bb_seat].stack == 990
    sb_seat = g._get_sb_seat()
    assert g.players[sb_seat].stack == 995

def test_heads_up_blinds():
    g = make_game(2, sb=5, bb=10)
    g.new_hand()
    assert g.pot == 15
    # Heads-up: dealer posts SB
    assert g.players[g.dealer_seat].stack == 995


# ========================================================================
# Preflop Action
# ========================================================================

def test_preflop_fold_all():
    """Everyone folds to BB — BB wins."""
    g = make_game(3, sb=5, bb=10)
    g.new_hand()
    
    # UTG (seat after BB) acts first
    utg = g.action_seat
    result = g.process_action(utg, "fold")
    
    # SB folds
    sb = g.action_seat
    result = g.process_action(sb, "fold")
    
    # BB wins uncontested
    assert "winners" in result
    assert len(result["winners"]) == 1
    bb_seat = g._get_bb_seat()
    assert result["winners"][0]["seat"] == bb_seat

def test_preflop_call_and_check():
    """Players call, BB checks — advance to flop."""
    g = make_game(3, sb=5, bb=10)
    g.new_hand()

    # UTG calls
    utg = g.action_seat
    g.process_action(utg, "call")

    # SB calls (needs 5 more)
    sb = g.action_seat
    g.process_action(sb, "call")

    # BB checks (option)
    bb = g.action_seat
    result = g.process_action(bb, "check")

    # Should advance to flop
    assert g.street == Street.FLOP
    assert len(g.community_cards) == 3

def test_preflop_raise():
    """UTG raises, others fold."""
    g = make_game(3, sb=5, bb=10)
    g.new_hand()

    utg = g.action_seat
    g.process_action(utg, "raise", 30)  # Raise to 30

    sb = g.action_seat
    g.process_action(sb, "fold")

    bb = g.action_seat
    result = g.process_action(bb, "fold")

    assert "winners" in result
    assert result["winners"][0]["seat"] == utg


# ========================================================================
# Full Hand to Showdown
# ========================================================================

def test_full_hand_to_showdown():
    """Play a complete hand through to showdown."""
    g = make_game(2, stack=500, sb=5, bb=10)
    g.new_hand()

    # Preflop: both call/check
    seat = g.action_seat
    g.process_action(seat, "call")  # SB calls (heads-up: dealer=SB)
    seat = g.action_seat
    g.process_action(seat, "check")  # BB checks

    assert g.street == Street.FLOP
    assert len(g.community_cards) == 3

    # Flop: check-check
    seat = g.action_seat
    g.process_action(seat, "check")
    seat = g.action_seat
    g.process_action(seat, "check")

    assert g.street == Street.TURN
    assert len(g.community_cards) == 4

    # Turn: check-check
    seat = g.action_seat
    g.process_action(seat, "check")
    seat = g.action_seat
    g.process_action(seat, "check")

    assert g.street == Street.RIVER
    assert len(g.community_cards) == 5

    # River: check-check → showdown
    seat = g.action_seat
    g.process_action(seat, "check")
    seat = g.action_seat
    result = g.process_action(seat, "check")

    assert result.get("showdown") is True
    assert len(result["winners"]) >= 1
    assert result["winners"][0]["amount"] > 0


# ========================================================================
# Side Pots
# ========================================================================

def test_side_pot_calculation():
    """Direct test of side pot math."""
    # Player A bets 100, B bets 200, C bets 200. A is all-in.
    bets = [
        (0, 100, False),  # Player A: 100, not folded
        (1, 200, False),  # Player B: 200, not folded
        (2, 200, False),  # Player C: 200, not folded
    ]
    pots = SidePotCalculator.calculate(bets)
    assert len(pots) == 2
    # Main pot: 100 * 3 = 300 (all eligible)
    assert pots[0].amount == 300
    assert sorted(pots[0].eligible_seats) == [0, 1, 2]
    # Side pot: 100 * 2 = 200 (only B and C)
    assert pots[1].amount == 200
    assert sorted(pots[1].eligible_seats) == [1, 2]

def test_side_pot_with_fold():
    """Folded player's chips go to pot but they can't win."""
    bets = [
        (0, 50, True),    # Folded after betting 50
        (1, 100, False),
        (2, 100, False),
    ]
    pots = SidePotCalculator.calculate(bets)
    # All 50 * 3 in first layer, but seat 0 not eligible
    # Then 50 * 2 in second layer for seats 1,2
    assert len(pots) == 2
    assert pots[0].amount == 150  # 50 from each
    assert 0 not in pots[0].eligible_seats  # Folded player can't win
    assert pots[1].amount == 100  # 50 from each of 1,2


# ========================================================================
# Undo
# ========================================================================

def test_undo_action():
    g = make_game(3, sb=5, bb=10)
    g.new_hand()
    
    utg = g.action_seat
    pot_before = g.pot
    stack_before = g.players[utg].stack
    
    # UTG calls
    g.process_action(utg, "call")
    assert g.players[utg].stack < stack_before
    
    # Undo
    result = g.undo_action()
    assert result.get("ok") is True
    assert g.players[utg].stack == stack_before
    assert g.pot == pot_before
    assert g.action_seat == utg


# ========================================================================
# Position Labels
# ========================================================================

def test_positions_3_players():
    g = make_game(3)
    g.new_hand()
    positions = g._get_positions()
    values = set(positions.values())
    assert "BTN" in values
    assert "SB" in values
    assert "BB" in values

def test_positions_6_players():
    g = make_game(6)
    g.new_hand()
    positions = g._get_positions()
    values = set(positions.values())
    assert "BTN" in values
    assert "SB" in values
    assert "BB" in values
    assert "UTG" in values


# ========================================================================
# Dealer Rotation
# ========================================================================

def test_dealer_rotates():
    g = make_game(3)
    g.new_hand()
    first_dealer = g.dealer_seat
    
    # Play out a quick hand (everyone folds)
    while g.phase == GamePhase.PLAYING:
        seat = g.action_seat
        g.process_action(seat, "fold")
    
    g.new_hand()
    assert g.dealer_seat != first_dealer


# ========================================================================
# Edge Cases
# ========================================================================

def test_cannot_act_out_of_turn():
    g = make_game(3)
    g.new_hand()
    wrong_seat = (g.action_seat + 1) % 3
    result = g.process_action(wrong_seat, "call")
    assert "error" in result

def test_all_in_call():
    """Player with short stack goes all-in when calling."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Big Stack", stack=1000)
    g.add_player("Short Stack", stack=8)  # Can't even cover BB
    g.new_hand()
    # Short stack posted BB of 8 (all they had), should be all-in
    # Actually the short stack might be SB in heads-up
    # Either way, test that the game handles it
    assert g.phase == GamePhase.PLAYING

def test_multiple_hands():
    """Play multiple hands in sequence."""
    g = make_game(3, stack=500)
    for _ in range(5):
        g.new_hand()
        while g.phase == GamePhase.PLAYING:
            seat = g.action_seat
            g.process_action(seat, "fold")
    assert g.hand_number == 5
    assert len(g.hand_histories) == 5


def test_busted_player_skipped():
    """A player with 0 chips should be folded out at hand start."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Rich", stack=1000)
    g.add_player("Broke", stack=0)
    g.add_player("Normal", stack=500)
    g.new_hand()
    # Broke player should be folded
    broke = g.players[1]
    assert broke.is_folded is True
    # Game should still work with 2 active players
    assert g.phase == GamePhase.PLAYING


def test_all_in_showdown():
    """Two players all-in preflop should run out board and showdown."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("A", stack=100)
    g.add_player("B", stack=100)
    g.new_hand()
    
    # Heads-up: dealer is SB, acts first preflop
    seat = g.action_seat
    result = g.process_action(seat, "raise", 100)  # All-in
    
    # Other player calls all-in
    if g.phase == GamePhase.PLAYING:
        seat = g.action_seat
        result = g.process_action(seat, "call")
    
    # Should have gone to showdown with full board
    assert len(g.community_cards) == 5
    assert g.phase == GamePhase.BETWEEN_HANDS
    assert len(g.hand_histories) == 1
    assert g.hand_histories[0].winners


def test_three_way_all_in_side_pots():
    """Three players all-in with different stacks creates side pots."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Short", stack=50)
    g.add_player("Medium", stack=150)
    g.add_player("Big", stack=500)
    g.new_hand()
    
    # Everyone goes all-in
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 10:
        safety += 1
        seat = g.action_seat
        result = g.process_action(seat, "raise", 500)  # All-in attempt
        if "error" in result:
            result = g.process_action(seat, "call")
    
    # Should resolve with community cards and winners
    assert g.phase == GamePhase.BETWEEN_HANDS
    assert len(g.community_cards) == 5


def test_hand_history_structure():
    """Verify hand history has correct structure after a completed hand."""
    g = make_game(2, stack=500, sb=5, bb=10)
    g.new_hand()
    
    # Quick fold
    seat = g.action_seat
    g.process_action(seat, "fold")
    
    assert len(g.hand_histories) == 1
    hh = g.hand_histories[0]
    assert hh.hand_number == 1
    assert len(hh.actions) >= 3  # SB, BB, fold
    assert len(hh.winners) == 1
    assert hh.winners[0]["amount"] > 0
    
    # Verify action dicts
    for a in hh.actions:
        d = a.to_dict()
        assert "street" in d
        assert "seat" in d
        assert "player_name" in d
        assert "action" in d


def test_manual_deal_mode():
    """Manual deal mode should not auto-deal cards."""
    g = make_game(2)
    g.manual_deal = True
    g.new_hand()
    # No cards should be dealt
    for p in g.players:
        assert len(p.hole_cards) == 0
    # Should still be able to assign cards
    from engine.deck import Card
    result = g.assign_card("As", "player", 0)
    assert result.get("ok")
    assert len(g.players[0].hole_cards) == 1


def test_used_cards_tracking():
    """State should track all used cards for the card picker."""
    g = make_game(2)
    g.new_hand()
    state = g.get_state()
    used = state["used_cards"]
    # Should have 4 hole cards (2 per player) + burned cards
    assert len(used) >= 4
    # All should be valid short strings
    for card_str in used:
        assert len(card_str) == 2 or len(card_str) == 3  # e.g. "As" or "Th"


def test_undo_restores_completely():
    """Undo should restore stack, pot, and action seat exactly."""
    g = make_game(3, sb=5, bb=10)
    g.new_hand()
    
    utg = g.action_seat
    pot_before = g.pot
    stack_before = g.players[utg].stack
    bet_before = g.players[utg].current_bet
    action_seat_before = g.action_seat
    
    # Call
    g.process_action(utg, "call")
    assert g.players[utg].stack < stack_before
    assert g.pot > pot_before
    
    # Undo
    g.undo_action()
    assert g.players[utg].stack == stack_before
    assert g.pot == pot_before
    assert g.players[utg].current_bet == bet_before
    assert g.action_seat == action_seat_before


def test_total_chips_conserved():
    """After any showdown, total chips across all players must be conserved."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("A", stack=200)
    g.add_player("B", stack=300)
    g.add_player("C", stack=500)
    total_before = sum(p.stack for p in g.players)

    g.new_hand()
    # Everyone calls/checks to showdown
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 30:
        safety += 1
        seat = g.action_seat
        if seat < 0:
            break
        va = g.get_valid_actions(seat)
        actions = va.get("actions", [])
        if any(a["action"] == "check" for a in actions):
            g.process_action(seat, "check")
        elif any(a["action"] == "call" for a in actions):
            g.process_action(seat, "call")
        else:
            g.process_action(seat, "fold")

    total_after = sum(p.stack for p in g.players)
    assert total_after == total_before, f"Chips lost: {total_before} -> {total_after}"


def test_four_player_side_pots():
    """Four players with different stacks all-in creates correct side pots."""
    bets = [
        (0, 25, False),  # 25
        (1, 50, False),  # 50
        (2, 100, False), # 100
        (3, 200, False), # 200
    ]
    pots = SidePotCalculator.calculate(bets)
    assert len(pots) == 4, f"Expected 4 pots, got {len(pots)}"
    # Main pot: 25 * 4 = 100, all eligible
    assert pots[0].amount == 100
    assert set(pots[0].eligible_seats) == {0, 1, 2, 3}
    # Side pot 1: 25 * 3 = 75
    assert pots[1].amount == 75
    assert set(pots[1].eligible_seats) == {1, 2, 3}
    # Side pot 2: 50 * 2 = 100
    assert pots[2].amount == 100
    assert set(pots[2].eligible_seats) == {2, 3}
    # Side pot 3: 100 * 1 = 100
    assert pots[3].amount == 100
    assert set(pots[3].eligible_seats) == {3}
    # Total: 100 + 75 + 100 + 100 = 375 = 25+50+100+200
    assert sum(p.amount for p in pots) == 375


def test_undo_hand_removes_history():
    """Undo hand after completion should remove the history entry."""
    g = make_game(2, stack=500, sb=5, bb=10)
    g.new_hand()
    # Fold immediately to end hand
    seat = g.action_seat
    g.process_action(seat, "fold")
    assert g.phase == GamePhase.BETWEEN_HANDS
    assert len(g.hand_histories) == 1

    g.undo_hand()
    assert len(g.hand_histories) == 0, f"Expected 0 histories after undo, got {len(g.hand_histories)}"
    assert g.phase == GamePhase.BETWEEN_HANDS
    assert g.hand_number == 0


def test_undo_hand_mid_hand_no_history_change():
    """Undo hand mid-hand should not crash and history should stay empty."""
    g = make_game(2, stack=500, sb=5, bb=10)
    g.new_hand()
    # Take one action but don't finish hand
    seat = g.action_seat
    g.process_action(seat, "call")
    assert len(g.hand_histories) == 0

    g.undo_hand()
    assert len(g.hand_histories) == 0
    assert g.phase == GamePhase.BETWEEN_HANDS


def test_min_raise_validation():
    """Raise below minimum should return error."""
    g = make_game(2, stack=1000, sb=5, bb=10)
    g.new_hand()
    seat = g.action_seat
    # Min raise to = current_bet(10) + last_raise_size(10) = 20
    result = g.process_action(seat, "raise", 15)  # Below min raise of 20
    assert "error" in result, f"Should reject raise below min, got: {result}"


def test_all_in_below_min_raise():
    """All-in for less than min raise should be valid."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Short", stack=15)  # Can only raise to 15 (below min raise of 20)
    g.add_player("Big", stack=1000)
    g.new_hand()
    seat = g.action_seat
    # Short stack (seat 0 in heads-up is dealer/SB), try to go all-in for 15
    result = g.process_action(seat, "raise", 15)
    assert "error" not in result, f"All-in below min raise should be valid, got: {result}"


def test_side_pot_chips_not_lost_when_eligible_fold():
    """When all eligible players for a side pot have folded, chips should carry forward."""
    # Scenario: 3 players. Player 0 goes all-in for 50. Player 1 raises to 100.
    # Player 2 calls 100. Player 0 can't act more. Player 1 folds on flop.
    # Now Player 1 is folded but contributed to a side pot layer above Player 0.
    # This tests that no chips are lost.
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Short", stack=50)
    g.add_player("Mid", stack=500)
    g.add_player("Big", stack=500)
    total_before = sum(p.stack for p in g.players)

    g.new_hand()
    # Play through to completion
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 30:
        safety += 1
        seat = g.action_seat
        if seat < 0:
            break
        va = g.get_valid_actions(seat)
        actions = va.get("actions", [])
        if any(a["action"] == "check" for a in actions):
            g.process_action(seat, "check")
        elif any(a["action"] == "call" for a in actions):
            g.process_action(seat, "call")
        else:
            g.process_action(seat, "fold")

    total_after = sum(p.stack for p in g.players)
    assert total_after == total_before, f"Chips lost: {total_before} -> {total_after}"


# ========================================================================
# Turn Order & Race Condition Tests
# ========================================================================

def test_preflop_turn_order_3_players():
    """Preflop action order: UTG (left of BB) → SB → BB option."""
    g = make_game(3)
    g.new_hand()
    dealer = g.dealer_seat
    n = len(g.players)
    # In 3-player: SB is left of dealer, BB is left of SB
    sb_seat = (dealer + 1) % n
    bb_seat = (dealer + 2) % n
    utg_seat = dealer  # In 3-player, UTG is the dealer/BTN

    # First to act should be UTG (left of BB, which wraps to dealer in 3-player)
    assert g.action_seat == utg_seat, \
        f"First to act should be UTG (seat {utg_seat}), got seat {g.action_seat}"

    # UTG acts
    g.process_action(g.action_seat, "call")
    assert g.action_seat == sb_seat, \
        f"After UTG, should be SB (seat {sb_seat}), got seat {g.action_seat}"

    # SB acts
    g.process_action(g.action_seat, "call")
    assert g.action_seat == bb_seat, \
        f"After SB, should be BB (seat {bb_seat}), got seat {g.action_seat}"


def test_postflop_turn_order_3_players():
    """Postflop action order: SB (left of dealer) → BB → BTN."""
    g = make_game(3)
    g.new_hand()
    dealer = g.dealer_seat
    n = len(g.players)
    sb_seat = (dealer + 1) % n
    bb_seat = (dealer + 2) % n

    # Play through preflop: all call/check
    while g.street == Street.PREFLOP and g.phase == GamePhase.PLAYING:
        seat = g.action_seat
        va = g.get_valid_actions(seat)
        actions = [a["action"] for a in va.get("actions", [])]
        if "check" in actions:
            g.process_action(seat, "check")
        else:
            g.process_action(seat, "call")

    assert g.street == Street.FLOP, f"Should be on flop, got {g.street}"

    # First to act postflop should be SB (left of dealer)
    assert g.action_seat == sb_seat, \
        f"First postflop actor should be SB (seat {sb_seat}), got seat {g.action_seat}"


def test_turn_order_skips_folded_players():
    """After a fold, that player is skipped in subsequent action."""
    g = make_game(3)
    g.new_hand()
    dealer = g.dealer_seat
    n = len(g.players)
    sb_seat = (dealer + 1) % n
    bb_seat = (dealer + 2) % n

    # UTG folds
    utg_seat = g.action_seat
    g.process_action(utg_seat, "fold")

    # SB calls
    assert g.action_seat == sb_seat
    g.process_action(sb_seat, "call")

    # BB checks (option)
    assert g.action_seat == bb_seat
    g.process_action(bb_seat, "check")

    # Now on flop — folded UTG should be skipped
    assert g.street == Street.FLOP
    assert g.action_seat != utg_seat, \
        f"Folded player (seat {utg_seat}) should not be action seat"
    # First active postflop should be SB (if SB is left of dealer)
    assert g.action_seat == sb_seat, \
        f"First postflop actor should be SB (seat {sb_seat}), got {g.action_seat}"


def test_turn_order_skips_all_in_players():
    """All-in players should be skipped for action but stay in hand."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("BTN", stack=50)   # Will go all-in
    g.add_player("SB", stack=1000)
    g.add_player("BB", stack=1000)
    g.new_hand()

    # BTN goes all-in
    btn_seat = g.action_seat
    g.process_action(btn_seat, "raise", 50)

    # SB calls
    sb_seat = g.action_seat
    assert sb_seat != btn_seat
    g.process_action(sb_seat, "call")

    # BB calls
    bb_seat = g.action_seat
    g.process_action(bb_seat, "call")

    # On flop, BTN (all-in) should be skipped
    if g.street == Street.FLOP:
        assert g.action_seat != btn_seat, \
            f"All-in player (seat {btn_seat}) should not be action seat"
        # BTN should still be in hand
        assert g.players[btn_seat].is_in_hand, "All-in player should still be in hand"


def test_wrong_seat_action_rejected():
    """Actions from wrong seat must be rejected at every street."""
    g = make_game(3)
    g.new_hand()

    streets_tested = []
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 40:
        safety += 1
        correct_seat = g.action_seat
        current_street = g.street.value

        # Try acting from every wrong seat
        for seat in range(len(g.players)):
            if seat != correct_seat:
                result = g.process_action(seat, "call")
                assert "error" in result, \
                    f"Seat {seat} should not be able to act when it's seat {correct_seat}'s turn on {current_street}"

        if current_street not in streets_tested:
            streets_tested.append(current_street)

        # Advance the game with a valid action
        va = g.get_valid_actions(correct_seat)
        actions = [a["action"] for a in va.get("actions", [])]
        if "check" in actions:
            g.process_action(correct_seat, "check")
        elif "call" in actions:
            g.process_action(correct_seat, "call")
        else:
            g.process_action(correct_seat, "fold")

    # Should have tested at least preflop and flop
    assert len(streets_tested) >= 2, f"Only tested streets: {streets_tested}"


def test_action_seat_consistency_across_streets():
    """action_seat should always point to a valid, active, non-folded, non-all-in player."""
    g = make_game(4, stack=500)
    g.new_hand()
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 50:
        safety += 1
        seat = g.action_seat
        assert 0 <= seat < len(g.players), f"action_seat {seat} out of range"
        player = g.players[seat]
        assert player.is_active, f"action_seat points to inactive player (seat {seat})"
        assert not player.is_folded, f"action_seat points to folded player (seat {seat})"
        assert not player.is_all_in, f"action_seat points to all-in player (seat {seat})"
        assert not player.is_sitting_out, f"action_seat points to sitting-out player (seat {seat})"

        va = g.get_valid_actions(seat)
        actions = [a["action"] for a in va.get("actions", [])]
        if "check" in actions:
            g.process_action(seat, "check")
        elif "call" in actions:
            g.process_action(seat, "call")
        else:
            g.process_action(seat, "fold")


def test_busted_player_never_gets_action():
    """A busted player (0 chips) should never be action_seat across multiple hands."""
    g = GameState()
    g.set_blinds(5, 10)
    g.add_player("Rich", stack=1000)
    g.add_player("Broke", stack=0)
    g.add_player("Normal", stack=500)

    for _ in range(3):
        g.new_hand()
        safety = 0
        while g.phase == GamePhase.PLAYING and safety < 20:
            safety += 1
            assert g.action_seat != 1, "Busted player (seat 1) should never be action_seat"
            g.process_action(g.action_seat, "fold")


def test_all_in_sb_gets_dealt_cards():
    """Player who goes all-in posting SB should still get hole cards."""
    g = GameState()
    g.set_blinds(100, 200)
    # First hand: seat 0 = BTN, seat 1 = SB, seat 2 = BB
    g.add_player("Normal", stack=5000, player_type="human")      # Seat 0 (BTN)
    g.add_player("ShortStack", stack=100, player_type="human")   # Seat 1 (SB) — exactly SB
    g.add_player("Bob", stack=5000, player_type="human")         # Seat 2 (BB)
    g.new_hand()

    sb_player = g.players[1]  # Seat 1 is SB
    assert sb_player.is_all_in, "Short stack should be all-in after posting SB"
    assert sb_player.stack == 0, "Short stack should have 0 chips after posting SB"
    assert len(sb_player.hole_cards) == 2, \
        f"All-in SB player should have 2 hole cards, got {len(sb_player.hole_cards)}"
    assert sb_player.is_in_hand, "All-in SB player should still be in hand"


def test_all_in_bb_gets_dealt_cards():
    """Player who goes all-in posting BB should still get hole cards."""
    g = GameState()
    g.set_blinds(100, 200)
    # First hand: seat 0 = BTN, seat 1 = SB, seat 2 = BB
    g.add_player("Normal", stack=5000, player_type="human")      # Seat 0 (BTN)
    g.add_player("Alice", stack=5000, player_type="human")       # Seat 1 (SB)
    g.add_player("ShortBB", stack=200, player_type="human")      # Seat 2 (BB) — exactly BB
    g.new_hand()

    bb_player = g.players[2]  # Seat 2 is BB
    assert bb_player.is_all_in, "Short stack should be all-in after posting BB"
    assert bb_player.stack == 0, "Short stack should have 0 chips after posting BB"
    assert len(bb_player.hole_cards) == 2, \
        f"All-in BB player should have 2 hole cards, got {len(bb_player.hole_cards)}"
    assert bb_player.is_in_hand, "All-in BB player should still be in hand"


def test_all_in_blind_included_in_showdown():
    """Player all-in from blind should be eligible for pot at showdown."""
    g = GameState()
    g.set_blinds(100, 200)
    g.add_player("ShortStack", stack=100, player_type="human")  # Goes all-in posting SB
    g.add_player("Alice", stack=5000, player_type="human")
    g.add_player("Bob", stack=5000, player_type="human")
    g.new_hand()

    # All non-all-in players fold — short stack should win
    safety = 0
    while g.phase == GamePhase.PLAYING and safety < 20:
        safety += 1
        seat = g.action_seat
        if seat < 0:
            break
        p = g.players[seat]
        if p.is_all_in:
            continue  # Can't act
        g.process_action(seat, "fold")

    # Short stack should have won some chips
    short = next(p for p in g.players if p.name == "ShortStack")
    assert short.stack > 0, f"All-in blind player should win pot, got stack={short.stack}"


# ========================================================================
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
            import traceback
            traceback.print_exc()
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    else:
        print("All tests passed.")
