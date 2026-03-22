"""Tests for the scripted tutorial system."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.tutorial import TutorialState, TUTORIAL_HANDS
from engine.game import GameState, GamePhase
from engine.player import PlayerType, AIStyle
from engine.deck import Card, Deck


# ── Tutorial Data Tests ──

def test_tutorial_has_10_hands():
    assert len(TUTORIAL_HANDS) == 10


def test_each_hand_has_required_fields():
    required = {"title", "intro", "player_cards", "bot_cards", "community",
                "bot_script", "guided", "outro"}
    for i, hand in enumerate(TUTORIAL_HANDS):
        for field in required:
            assert field in hand, f"Hand {i+1} missing field: {field}"


def test_each_hand_has_valid_cards():
    for i, hand in enumerate(TUTORIAL_HANDS):
        # Player cards
        assert len(hand["player_cards"]) == 2, f"Hand {i+1}: need 2 player cards"
        for c in hand["player_cards"]:
            Card.from_short(c)  # Should not raise
        # Bot cards
        assert len(hand["bot_cards"]) == 2, f"Hand {i+1}: need 2 bot cards"
        for c in hand["bot_cards"]:
            Card.from_short(c)
        # Community
        assert len(hand["community"]) == 5, f"Hand {i+1}: need 5 community cards"
        for c in hand["community"]:
            Card.from_short(c)


def test_no_duplicate_cards_in_any_hand():
    for i, hand in enumerate(TUTORIAL_HANDS):
        all_cards = hand["player_cards"] + hand["bot_cards"] + hand["community"]
        assert len(all_cards) == len(set(all_cards)), f"Hand {i+1}: duplicate cards"


def test_each_hand_has_at_least_one_guided_action():
    for i, hand in enumerate(TUTORIAL_HANDS):
        assert len(hand["guided"]) >= 1, f"Hand {i+1}: needs guided actions"


def test_intro_and_outro_have_title_and_body():
    for i, hand in enumerate(TUTORIAL_HANDS):
        assert "title" in hand["intro"], f"Hand {i+1}: intro missing title"
        assert "body" in hand["intro"], f"Hand {i+1}: intro missing body"
        assert "title" in hand["outro"], f"Hand {i+1}: outro missing title"
        assert "body" in hand["outro"], f"Hand {i+1}: outro missing body"


def test_hand_1_and_10_are_pocket_aces():
    """Tutorial starts and ends with AA for narrative symmetry."""
    assert set(TUTORIAL_HANDS[0]["player_cards"]) == {"Ah", "As"}
    assert set(TUTORIAL_HANDS[9]["player_cards"]) == {"Ah", "As"}


def test_hand_7_guided_action_is_fold():
    """Hand 7 teaches folding discipline."""
    guided = TUTORIAL_HANDS[6]["guided"]
    assert any(g["action"] == "fold" for g in guided)


# ── TutorialState Tests ──

def test_tutorial_state_init():
    ts = TutorialState()
    assert ts.hand_index == 0
    assert ts.is_active
    assert not ts.is_complete


def test_tutorial_state_current_hand():
    ts = TutorialState()
    hand = ts.current_hand()
    assert hand is not None
    assert hand["title"] == TUTORIAL_HANDS[0]["title"]


def test_tutorial_state_advance():
    ts = TutorialState()
    for i in range(9):
        assert not ts.advance_hand()
        assert ts.hand_index == i + 1
    assert ts.advance_hand()  # 10th advance completes
    assert ts.is_complete
    assert not ts.is_active


def test_tutorial_state_get_bot_action():
    ts = TutorialState()
    # Hand 1: bot folds preflop
    action = ts.get_bot_action("preflop")
    assert action is not None
    assert action["action"] == "fold"


def test_tutorial_state_get_guided_action():
    ts = TutorialState()
    # Hand 1: guided raise preflop
    guided = ts.get_guided_action("preflop")
    assert guided is not None
    assert guided["action"] == "raise"


def test_tutorial_state_to_dict():
    ts = TutorialState()
    d = ts.to_dict()
    assert d["active"] is True
    assert d["complete"] is False
    assert d["hand_index"] == 0
    assert d["total_hands"] == 10


# ── Deck.stack_top Tests ──

def test_deck_stack_top():
    deck = Deck(seed=42)
    card_a = Card.from_short("As")
    card_k = Card.from_short("Kh")
    deck.stack_top([card_a, card_k])
    drawn = deck.draw(2)
    assert drawn[0] == card_a
    assert drawn[1] == card_k


def test_deck_stack_top_removes_from_original():
    deck = Deck(seed=42)
    original_len = len(deck)
    card = Card.from_short("As")
    deck.stack_top([card])
    # Length unchanged — card moved, not added
    assert len(deck) == original_len


# ── Game Tutorial Deal Tests ──

def test_tutorial_deal_assigns_correct_cards():
    game = GameState()
    game.add_player("You", 1000, "human")
    game.add_player("Bot", 1000, "ai", "loose_passive")
    game.small_blind = 5
    game.big_blind = 10

    game.tutorial_deal = {
        "player_cards": ["Ah", "As"],
        "bot_cards": ["7d", "2c"],
        "community": ["Ks", "8d", "3c", "5h", "Jd"],
        "dealer_seat": 0,
        "player_seat": 0,
        "bot_seat": 1,
    }

    game.new_hand()

    # Check hole cards
    player_shorts = [c.short for c in game.players[0].hole_cards]
    assert set(player_shorts) == {"Ah", "As"}

    bot_shorts = [c.short for c in game.players[1].hole_cards]
    assert set(bot_shorts) == {"7d", "2c"}


def test_tutorial_deal_community_cards():
    game = GameState()
    game.add_player("You", 1000, "human")
    game.add_player("Bot", 1000, "ai", "loose_passive")
    game.small_blind = 5
    game.big_blind = 10

    expected_community = ["Ks", "8d", "3c", "5h", "Jd"]
    game.tutorial_deal = {
        "player_cards": ["Ah", "As"],
        "bot_cards": ["7d", "2c"],
        "community": expected_community,
        "dealer_seat": 0,
        "player_seat": 0,
        "bot_seat": 1,
    }

    game.new_hand()

    # Advance to flop by simulating action completion
    # The community cards should come from the tutorial override
    assert game._tutorial_community is not None
    assert len(game._tutorial_community) == 5
    shorts = [c.short for c in game._tutorial_community]
    assert shorts == expected_community


def test_tutorial_deal_overrides_dealer():
    game = GameState()
    game.add_player("You", 1000, "human")
    game.add_player("Bot", 1000, "ai", "loose_passive")
    game.small_blind = 5
    game.big_blind = 10
    game.dealer_seat = 1  # Would normally stay 1 for first hand

    game.tutorial_deal = {
        "player_cards": ["Ah", "As"],
        "bot_cards": ["7d", "2c"],
        "community": ["Ks", "8d", "3c", "5h", "Jd"],
        "dealer_seat": 0,
        "player_seat": 0,
        "bot_seat": 1,
    }

    game.new_hand()
    assert game.dealer_seat == 0


def test_tutorial_deal_clears_after_use():
    game = GameState()
    game.add_player("You", 1000, "human")
    game.add_player("Bot", 1000, "ai", "loose_passive")
    game.small_blind = 5
    game.big_blind = 10

    game.tutorial_deal = {
        "player_cards": ["Ah", "As"],
        "bot_cards": ["7d", "2c"],
        "community": ["Ks", "8d", "3c", "5h", "Jd"],
        "dealer_seat": 0,
        "player_seat": 0,
        "bot_seat": 1,
    }

    game.new_hand()
    assert game.tutorial_deal is None  # Cleared after use
