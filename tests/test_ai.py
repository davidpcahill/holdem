"""
Tests for the AI decision engine.

Tests that AI produces valid actions for all styles and handles edge cases.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ai import AIEngine, AIDecision
from engine.player import Player, PlayerType, AIStyle
from engine.equity import EquityResult


def make_player(style="tight_aggressive", stack=1000):
    """Helper: create a player for AI testing."""
    return Player(
        seat=0, name="TestAI", stack=stack,
        player_type=PlayerType.AI, ai_style=AIStyle(style),
    )


def make_valid_actions(to_call=10, pot=30, can_raise=True, raise_min=20, raise_max=1000):
    """Helper: build a valid_actions dict."""
    actions = [{"action": "fold"}]
    if to_call <= 0:
        actions.append({"action": "check"})
    else:
        actions.append({"action": "call", "amount": to_call, "is_all_in": False})
    if can_raise:
        act = "raise" if to_call > 0 else "bet"
        actions.append({"action": act, "min": raise_min, "max": raise_max})
    return {
        "actions": actions,
        "to_call": to_call,
        "pot": pot,
        "current_bet": to_call,
        "player_current_bet": 0,
        "player_stack": 1000,
    }


# ========================================================================
# Tests
# ========================================================================

def test_ai_returns_valid_action():
    """AI decision should always return a valid action for each style."""
    engine = AIEngine(timing_preset="fast", variance=0.3)
    equity = EquityResult(win=50, tie=2, loss=48, simulations=0, is_preflop=True)
    valid = make_valid_actions(to_call=10, pot=30)

    for style in ["loose_passive", "tight_aggressive", "gto", "random"]:
        player = make_player(style)
        decision = engine.decide(
            player=player, valid_actions=valid, equity=equity,
            community_cards=[], pot=30, street="preflop",
            position="BTN", num_opponents=2,
        )
        assert decision.action in ("fold", "check", "call", "bet", "raise"), \
            f"Style {style} returned invalid action: {decision.action}"


def test_ai_think_time_positive():
    """Think time should be positive for realistic preset."""
    engine = AIEngine(timing_preset="realistic", variance=0.3)
    player = make_player("tight_aggressive")
    think_time = engine.calculate_think_time(player)
    assert think_time > 0, f"Think time should be >0, got {think_time}"


def test_ai_think_time_fast_is_zero():
    """Think time for fast preset should be 0."""
    engine = AIEngine(timing_preset="fast", variance=0.3)
    player = make_player("tight_aggressive")
    think_time = engine.calculate_think_time(player)
    assert think_time == 0.0, f"Fast think time should be 0, got {think_time}"


def test_ai_handles_only_fold_check():
    """AI should work when only fold and check are available."""
    engine = AIEngine(timing_preset="fast", variance=0.3)
    equity = EquityResult(win=30, tie=2, loss=68, simulations=0)
    valid = make_valid_actions(to_call=0, pot=20, can_raise=False)
    player = make_player("tight_aggressive")
    decision = engine.decide(
        player=player, valid_actions=valid, equity=equity,
        community_cards=[], pot=20, street="flop",
        position="BB", num_opponents=1,
    )
    assert decision.action in ("fold", "check"), \
        f"Should fold or check, got {decision.action}"


def test_ai_decision_structure():
    """AIDecision should have required fields and to_dict should work."""
    d = AIDecision(action="call", amount=10, reasoning="Test")
    assert d.action == "call"
    assert d.amount == 10
    assert d.reasoning == "Test"
    dd = d.to_dict()
    assert dd["action"] == "call"
    assert dd["amount"] == 10
    assert "reasoning" in dd


def test_ai_postflop_decision():
    """AI should make a valid postflop decision."""
    engine = AIEngine(timing_preset="fast", variance=0.0)
    equity = EquityResult(win=70, tie=3, loss=27, simulations=1000)
    valid = make_valid_actions(to_call=20, pot=50, can_raise=True, raise_min=40, raise_max=500)
    player = make_player("tight_aggressive", stack=500)
    decision = engine.decide(
        player=player, valid_actions=valid, equity=equity,
        community_cards=[], pot=50, street="flop",
        position="BTN", num_opponents=1,
    )
    assert decision.action in ("fold", "check", "call", "bet", "raise"), \
        f"Invalid action: {decision.action}"


# ========================================================================
# Adaptive AI Tests
# ========================================================================

def test_adaptive_ai_returns_valid_action():
    """Adaptive AI with opponent stats still returns valid action."""
    player = make_player("tight_aggressive")
    player.adaptive = True
    engine = AIEngine(timing_preset="fast", variance=0.1)
    equity = EquityResult(win=55, tie=5, loss=40)

    opp_stats = {
        1: {"vpip": 60, "af": 0.3, "hands_played": 20, "wtsd": 30},
        2: {"vpip": 20, "af": 2.5, "hands_played": 15, "wtsd": 40},
    }

    valid_actions = {
        "actions": [
            {"action": "fold"},
            {"action": "call", "amount": 20},
            {"action": "raise", "min": 40, "max": 1000},
        ],
        "to_call": 20,
        "current_bet": 0,
    }

    decision = engine.decide(
        player=player, valid_actions=valid_actions, equity=equity,
        community_cards=[], pot=50, street="flop", position="BTN",
        num_opponents=2, opponent_stats=opp_stats,
    )
    assert decision.action in ("fold", "check", "call", "raise", "bet")


def test_adaptive_reduces_bluffs_vs_loose():
    """Adaptive AI bluffs less against loose opponents (high VPIP)."""
    from engine.ai import STYLE_PARAMS
    engine = AIEngine(timing_preset="fast", variance=0.0)

    base_params = dict(STYLE_PARAMS[AIStyle.GTO])
    opp_stats_loose = {
        1: {"vpip": 75, "af": 0.5, "hands_played": 50, "wtsd": 40},
    }
    adjusted = engine._adjust_for_opponents(dict(base_params), opp_stats_loose)
    assert adjusted["bluff_frequency"] < base_params["bluff_frequency"], \
        "Bluff frequency should decrease vs loose opponents"


def test_adaptive_increases_bluffs_vs_tight():
    """Adaptive AI bluffs more against tight opponents (low VPIP)."""
    from engine.ai import STYLE_PARAMS
    engine = AIEngine(timing_preset="fast", variance=0.0)

    base_params = dict(STYLE_PARAMS[AIStyle.GTO])
    opp_stats_tight = {
        1: {"vpip": 12, "af": 1.5, "hands_played": 50, "wtsd": 20},
    }
    adjusted = engine._adjust_for_opponents(dict(base_params), opp_stats_tight)
    assert adjusted["bluff_frequency"] > base_params["bluff_frequency"], \
        "Bluff frequency should increase vs tight opponents"


def test_adaptive_ignores_small_sample():
    """Adaptive AI ignores opponents with < 10 hands played."""
    from engine.ai import STYLE_PARAMS
    engine = AIEngine(timing_preset="fast", variance=0.0)

    base_params = dict(STYLE_PARAMS[AIStyle.GTO])
    opp_stats_small = {
        1: {"vpip": 90, "af": 0.1, "hands_played": 5, "wtsd": 10},
    }
    adjusted = engine._adjust_for_opponents(dict(base_params), opp_stats_small)
    assert adjusted["bluff_frequency"] == base_params["bluff_frequency"], \
        "Should not adjust with < 10 hands sample"


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
