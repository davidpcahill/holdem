"""
Texas Hold'em Game State Machine.

Manages the complete game lifecycle: table setup, dealing, betting rounds,
community cards, showdown, pot distribution, and hand/dealer rotation.

The GameState is the single source of truth. The frontend is a dumb render
layer that reads serialized state from this class.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
import time

from .deck import Card, Deck
from .player import Player, PlayerType, AIStyle
from .betting import BettingRound, SidePotCalculator, SidePot, ActionResult
from .hand_eval import HandEvaluator, HandResult, HAND_RANK_NAMES


class Street(Enum):
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    HAND_OVER = "hand_over"


class GamePhase(Enum):
    SETUP = "setup"         # Configuring players, not started
    PLAYING = "playing"     # Hand in progress
    BETWEEN_HANDS = "between_hands"  # Hand finished, waiting for next


@dataclass
class HandLogEntry:
    """A single action in the hand history."""
    street: str
    seat: int
    player_name: str
    action: str
    amount: int = 0
    is_all_in: bool = False
    timestamp: float = 0.0
    pot_after: int = 0             # Pot size after this action

    def to_dict(self) -> dict:
        return {
            "street": self.street,
            "seat": self.seat,
            "player_name": self.player_name,
            "action": self.action,
            "amount": self.amount,
            "is_all_in": self.is_all_in,
            "pot_after": self.pot_after,
        }


@dataclass
class HandHistory:
    """Complete history for one hand."""
    hand_number: int
    players: List[dict]            # Snapshot of player states at start
    community_cards: List[str]     # Card short strings
    actions: List[HandLogEntry] = field(default_factory=list)
    winners: List[dict] = field(default_factory=list)  # [{seat, name, amount, hand_name}]
    pot_total: int = 0
    hole_cards: dict = field(default_factory=dict)     # {seat: [card_short, ...]}
    hand_ranks: dict = field(default_factory=dict)     # {seat: "Pair of Aces"}

    def to_dict(self) -> dict:
        return {
            "hand_number": self.hand_number,
            "players": self.players,
            "community_cards": self.community_cards,
            "actions": [a.to_dict() for a in self.actions],
            "winners": self.winners,
            "pot_total": self.pot_total,
            "hole_cards": self.hole_cards,
            "hand_ranks": self.hand_ranks,
        }


class GameState:
    """
    Complete Texas Hold'em game state.
    
    Manages:
    - Table configuration (players, blinds, dealer position)
    - Hand lifecycle (deal, bet, community cards, showdown)
    - Pot management (main pot + side pots)
    - Action validation and application
    - Hand history logging
    """

    def __init__(self):
        # Table config
        self.players: List[Player] = []
        self.small_blind = 5
        self.big_blind = 10
        self.dealer_seat = 0         # Button position (seat index into self.players)
        self.hand_number = 0
        self.burn_cards_enabled = True

        # Blind escalation
        self.auto_escalate = False
        self.escalate_interval = 10   # Every N hands
        self.escalate_multiplier = 1.5

        # Current hand state
        self.phase = GamePhase.SETUP
        self.street = Street.PREFLOP
        self.deck: Optional[Deck] = None
        self.community_cards: List[Card] = []
        self.burned_cards: List[Card] = []
        self.pot = 0                  # Main pot (all chips from completed streets)
        self.street_pot = 0           # Chips added this street (for display)
        self.side_pots: List[SidePot] = []
        self.betting_round: Optional[BettingRound] = None

        # Turn tracking
        self.action_seat = -1        # Seat index of player whose turn it is
        self.last_aggressor_seat = -1  # Last player who bet/raised

        # Manual deal mode
        self.manual_deal = False

        # Tutorial mode: predetermined cards
        self.tutorial_deal: Optional[dict] = None  # {player_cards, bot_cards, community, dealer_seat}
        self._tutorial_community: Optional[List[Card]] = None  # stacked community cards

        # History
        self.hand_histories: List[HandHistory] = []
        self.current_hand_log: Optional[HandHistory] = None

        # Undo stack: snapshots of state before each action
        self._undo_stack: List[dict] = []
        self._hand_start_snapshot: Optional[dict] = None

    # ------------------------------------------------------------------
    # Table Setup
    # ------------------------------------------------------------------

    def add_player(
        self,
        name: str,
        stack: int = 1000,
        player_type: str = "human",
        ai_style: str = "tight_aggressive",
        color: Optional[str] = None,
    ) -> Player:
        """Add a player to the next available seat."""
        if len(self.players) >= 10:
            raise ValueError("Table is full (max 10 players)")
        seat = len(self.players)
        p = Player(
            seat=seat,
            name=name,
            stack=stack,
            player_type=PlayerType(player_type),
            ai_style=AIStyle(ai_style),
            color=color,
        )
        self.players.append(p)
        return p

    def remove_player(self, seat: int) -> None:
        """Remove a player by seat index. Only valid during SETUP/BETWEEN_HANDS."""
        if self.phase == GamePhase.PLAYING:
            raise ValueError("Cannot remove player during a hand")
        self.players = [p for p in self.players if p.seat != seat]
        # Reindex seats
        for i, p in enumerate(self.players):
            p.seat = i

    def set_blinds(self, small_blind: int, big_blind: int) -> None:
        self.small_blind = small_blind
        self.big_blind = big_blind

    # ------------------------------------------------------------------
    # Hand Lifecycle
    # ------------------------------------------------------------------

    def new_hand(self) -> dict:
        """
        Start a new hand. Rotates dealer, posts blinds, deals hole cards.
        Returns the new game state dict.
        """
        active_players = [p for p in self.players if not p.is_sitting_out and p.stack > 0]
        if len(active_players) < 2:
            raise ValueError("Need at least 2 active players with chips")

        # Escalate blinds if needed
        if self.auto_escalate and self.hand_number > 0:
            if self.hand_number % self.escalate_interval == 0:
                self.small_blind = int(self.small_blind * self.escalate_multiplier)
                self.big_blind = int(self.big_blind * self.escalate_multiplier)

        # Rotate dealer (or override for tutorial)
        if self.tutorial_deal and "dealer_seat" in self.tutorial_deal:
            self.dealer_seat = self.tutorial_deal["dealer_seat"]
        elif self.hand_number > 0:
            self.dealer_seat = self._next_active_seat(self.dealer_seat)

        self.hand_number += 1
        self.phase = GamePhase.PLAYING
        self.street = Street.PREFLOP
        self.community_cards = []
        self.burned_cards = []
        self.pot = 0
        self.street_pot = 0
        self.side_pots = []
        self.last_aggressor_seat = -1
        self._undo_stack = []

        # Reset all players for new hand
        for p in self.players:
            p.reset_for_new_hand()
            if not p.is_sitting_out and p.stack > 0:
                p.hands_played += 1
            elif p.stack <= 0 and not p.is_sitting_out:
                # Busted player — fold them out of this hand
                p.is_folded = True

        # Fresh deck
        self.deck = Deck()

        # Tutorial: apply predetermined cards
        if self.tutorial_deal:
            self._apply_tutorial_deal()

        # Start hand log (must be before _post_blinds so blind actions are logged)
        self.current_hand_log = HandHistory(
            hand_number=self.hand_number,
            players=[p.to_dict(reveal_cards=True) for p in self.players
                     if not p.is_sitting_out and p.stack > 0],
            community_cards=[],
        )

        # Post blinds
        self._post_blinds()

        # Deal hole cards (2 per active player)
        if not self.manual_deal:
            self._deal_hole_cards()

        # Initialize betting round
        self.betting_round = BettingRound(
            num_players=len(active_players),
            big_blind=self.big_blind,
            is_preflop=True,
        )
        self.betting_round.current_bet = self.big_blind

        # First to act preflop: UTG (left of BB)
        bb_seat = self._get_bb_seat()
        self.action_seat = self._next_active_seat(bb_seat)

        # Save snapshot for undo-hand
        self._hand_start_snapshot = self._snapshot()

        return self.get_state()

    def _post_blinds(self) -> None:
        """Post small and big blinds."""
        active = self._active_player_seats()
        if len(active) < 2:
            return

        if len(active) == 2:
            # Heads-up: dealer posts SB, other posts BB
            sb_seat = self.dealer_seat
            bb_seat = self._next_active_seat(self.dealer_seat)
        else:
            sb_seat = self._next_active_seat(self.dealer_seat)
            bb_seat = self._next_active_seat(sb_seat)

        # Post SB
        sb_player = self.players[sb_seat]
        sb_actual = sb_player.place_bet(self.small_blind)
        self.pot += sb_actual
        self._log_action(sb_seat, "small_blind", sb_actual)

        # Post BB
        bb_player = self.players[bb_seat]
        bb_actual = bb_player.place_bet(self.big_blind)
        self.pot += bb_actual
        self._log_action(bb_seat, "big_blind", bb_actual)

    def _apply_tutorial_deal(self) -> None:
        """Set up predetermined cards for tutorial mode.

        Assigns specific hole cards to players and stacks the community
        cards on top of the deck so _deal_community draws them naturally.
        """
        from engine.deck import Card as DeckCard
        td = self.tutorial_deal
        if not td:
            return

        # Parse community cards and remove from deck
        community = [DeckCard.from_short(c) for c in td.get("community", [])]
        self.deck.remove_cards(community)
        self._tutorial_community = community

        # Parse and assign hole cards to specific seats
        for seat_key in ("player_cards", "bot_cards"):
            if seat_key not in td:
                continue
            seat = td.get("player_seat" if seat_key == "player_cards" else "bot_seat", -1)
            if seat < 0 or seat >= len(self.players):
                continue
            cards = [DeckCard.from_short(c) for c in td[seat_key]]
            self.deck.remove_cards(cards)
            # Store for _deal_hole_cards to pick up
            self.players[seat]._tutorial_hole = cards

        # Clear the tutorial_deal so it doesn't persist
        self.tutorial_deal = None

    def _deal_hole_cards(self) -> None:
        """Deal 2 cards to each player in the hand (including all-in from blinds)."""
        # Use is_in_hand (not is_active) so players who went all-in posting
        # blinds still get dealt cards.
        in_hand = [p.seat for p in self.players if p.is_in_hand]
        # Deal one card at a time around the table, starting left of dealer
        start = self._next_in_hand_seat(self.dealer_seat)
        order = self._seats_from(start, in_hand)
        for _ in range(2):
            for seat in order:
                # Tutorial override: use predetermined cards
                tutorial_cards = getattr(self.players[seat], '_tutorial_hole', None)
                if tutorial_cards and len(self.players[seat].hole_cards) < 2:
                    idx = len(self.players[seat].hole_cards)
                    self.players[seat].hole_cards.append(tutorial_cards[idx])
                else:
                    card = self.deck.draw_one()
                    self.players[seat].hole_cards.append(card)
        # Clean up tutorial attributes
        for p in self.players:
            if hasattr(p, '_tutorial_hole'):
                del p._tutorial_hole

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def get_valid_actions(self, seat: int) -> dict:
        """
        Get valid actions for a player.
        Returns dict with available actions and constraints.
        """
        if seat < 0 or seat >= len(self.players):
            return {"actions": [], "error": "Invalid seat"}
        player = self.players[seat]
        if not player.is_active or seat != self.action_seat:
            return {"actions": [], "error": "Not your turn"}

        to_call = self.betting_round.current_bet - player.current_bet
        to_call = max(0, to_call)
        min_raise_to = self.betting_round.current_bet + self.betting_round.last_raise_size
        max_raise_to = player.current_bet + player.stack  # All-in

        actions = []

        # Fold (always available, though checking is better when free)
        actions.append({"action": "fold"})

        # Check or Call
        if to_call <= 0 or (self._is_bb(seat) and self.street == Street.PREFLOP
                            and self.betting_round.current_bet == self.big_blind
                            and player.current_bet >= self.big_blind):
            actions.append({"action": "check"})
        else:
            call_amount = min(to_call, player.stack)
            actions.append({"action": "call", "amount": call_amount,
                          "is_all_in": call_amount >= player.stack})

        # Bet / Raise (if player has chips beyond calling)
        if player.stack > to_call:
            if self.betting_round.current_bet == 0:
                # Opening bet
                actions.append({
                    "action": "bet",
                    "min": self.big_blind,
                    "max": player.stack,
                })
            else:
                # Raise
                min_raise = min(min_raise_to, max_raise_to)
                actions.append({
                    "action": "raise",
                    "min": min_raise,
                    "max": max_raise_to,
                    "to_call": to_call,
                })
        elif player.stack > 0 and player.stack <= to_call:
            # Can only go all-in (can't raise, but can shove)
            actions.append({
                "action": "call",
                "amount": player.stack,
                "is_all_in": True,
                "label": "All-In",
            })

        # Max opponent stack (for effective bet display)
        opponents_in = [p for p in self.players if p.is_in_hand and p.seat != seat]
        max_opp_stack = max((p.stack + p.current_bet for p in opponents_in), default=0)

        return {
            "actions": actions,
            "to_call": to_call,
            "pot": self.pot,
            "current_bet": self.betting_round.current_bet,
            "min_raise_to": min_raise_to,
            "player_stack": player.stack,
            "player_current_bet": player.current_bet,
            "max_opponent_stack": max_opp_stack,
        }

    def process_action(self, seat: int, action: str, amount: int = 0) -> dict:
        """
        Process a player action.
        
        Args:
            seat: Player seat index
            action: "fold", "check", "call", "bet", "raise"
            amount: For bet/raise, the TOTAL bet amount (not additional chips)
            
        Returns:
            dict with action result and updated game state
        """
        if self.phase != GamePhase.PLAYING:
            return {"error": "No hand in progress"}

        if seat != self.action_seat:
            return {"error": f"Not seat {seat}'s turn (waiting for seat {self.action_seat})"}

        player = self.players[seat]
        if not player.is_active:
            return {"error": f"{player.name} cannot act (folded or all-in)"}

        # Save undo snapshot
        self._undo_stack.append(self._snapshot())

        to_call = max(0, self.betting_round.current_bet - player.current_bet)

        # Validate
        result = self.betting_round.validate_action(
            action=action,
            amount=amount,
            player_stack=player.stack,
            player_current_bet=player.current_bet,
            to_call=to_call,
            is_big_blind=self._is_bb(seat) and self.street == Street.PREFLOP,
            num_active=len([p for p in self.players if p.is_active]),
        )

        if not result.valid:
            self._undo_stack.pop()
            return {"error": result.error}

        # Apply action
        actual_action = result.action
        chips_in = 0

        if actual_action == "fold":
            player.is_folded = True
            self.betting_round.apply_fold()

        elif actual_action == "check":
            self.betting_round.apply_check()

        elif actual_action == "call":
            chips_in = player.place_bet(result.amount)
            self.pot += chips_in
            self.street_pot += chips_in
            self.betting_round.apply_call(chips_in)

        elif actual_action in ("bet", "raise"):
            chips_in = player.place_bet(result.amount)
            self.pot += chips_in
            self.street_pot += chips_in
            self.betting_round.apply_bet(chips_in, player.current_bet)
            self.last_aggressor_seat = seat
            # When someone raises, reset has_acted for all other active players
            for p in self.players:
                if p.seat != seat and p.is_active:
                    p.has_acted = False

        player.has_acted = True
        player.record_action(actual_action, chips_in)

        # Log
        self._log_action(seat, actual_action, chips_in, result.is_all_in)

        # Check if hand is over (all but one folded)
        players_in_hand = [p for p in self.players if p.is_in_hand]
        if len(players_in_hand) <= 1:
            return self._end_hand_single_winner(players_in_hand)

        # Check if betting round is complete
        if self._is_betting_complete():
            return self._advance_street()

        # Advance to next player
        self.action_seat = self._next_active_seat(seat)

        return {
            "action": result.to_dict(),
            "state": self.get_state(),
        }

    # ------------------------------------------------------------------
    # Street Advancement
    # ------------------------------------------------------------------

    def _advance_street(self) -> dict:
        """Advance to the next street or showdown."""
        # Reset per-street bets
        for p in self.players:
            p.reset_street_bet()

        # Check if we should go straight to showdown (all but one all-in)
        active_not_allin = [p for p in self.players if p.is_in_hand and not p.is_all_in]
        if len(active_not_allin) <= 1:
            # Run out remaining community cards, then showdown
            return self._run_out_and_showdown()

        if self.street == Street.PREFLOP:
            self.street = Street.FLOP
            self._deal_community(3)
        elif self.street == Street.FLOP:
            self.street = Street.TURN
            self._deal_community(1)
        elif self.street == Street.TURN:
            self.street = Street.RIVER
            self._deal_community(1)
        elif self.street == Street.RIVER:
            return self._showdown()

        # New betting round
        self.street_pot = 0
        self.betting_round = BettingRound(
            num_players=len([p for p in self.players if p.is_active]),
            big_blind=self.big_blind,
            is_preflop=False,
        )

        # First to act postflop: first active player left of dealer
        self.action_seat = self._first_postflop_actor()

        return {"state": self.get_state(), "street_advanced": self.street.value}

    def _deal_community(self, count: int) -> None:
        """Burn one card, then deal to community."""
        if self.burn_cards_enabled and self.deck and self.deck.remaining > count:
            burned = self.deck.burn()
            self.burned_cards.append(burned)
        # Tutorial: use predetermined community cards
        if self._tutorial_community:
            cards = self._tutorial_community[:count]
            self._tutorial_community = self._tutorial_community[count:]
            self.community_cards.extend(cards)
        elif self.deck:
            cards = self.deck.draw(count)
            self.community_cards.extend(cards)

    def _run_out_and_showdown(self) -> dict:
        """Deal remaining community cards and go to showdown."""
        remaining = 5 - len(self.community_cards)
        for _ in range(remaining):
            self._deal_community(1)
        return self._showdown()

    # ------------------------------------------------------------------
    # Showdown & Pot Distribution
    # ------------------------------------------------------------------

    def _showdown(self) -> dict:
        """Evaluate hands and distribute pots."""
        self.street = Street.SHOWDOWN

        players_in = [p for p in self.players if p.is_in_hand]

        # Track showdown participation
        for p in players_in:
            p.times_went_to_showdown += 1

        # Evaluate each player's hand
        hand_results: List[Tuple[int, HandResult]] = []
        for p in players_in:
            all_cards = p.hole_cards + self.community_cards
            result = HandEvaluator.evaluate(all_cards)
            hand_results.append((p.seat, result))

        # Calculate side pots
        bets = [(p.seat, p.total_bet_this_hand, p.is_folded) for p in self.players]
        pots = SidePotCalculator.calculate(bets)

        if not pots:
            # Shouldn't happen, but safety fallback
            pots = [SidePot(amount=self.pot, eligible_seats=[p.seat for p in players_in], label="Main Pot")]

        # Distribute each pot to winners
        winners_info = []
        # Track total per seat to consolidate side pot wins
        seat_totals = {}
        carry_forward = 0  # Chips from pots with no eligible players
        for pot in pots:
            eligible_hands = [(s, h) for s, h in hand_results if s in pot.eligible_seats]
            if not eligible_hands:
                carry_forward += pot.amount
                continue
            pot_amount = pot.amount + carry_forward
            carry_forward = 0
            winner_seats = HandEvaluator.find_winners(eligible_hands)
            share = pot_amount // len(winner_seats)
            remainder = pot_amount % len(winner_seats)

            for i, wseat in enumerate(winner_seats):
                win_amount = share + (1 if i < remainder else 0)
                self.players[wseat].win_chips(win_amount)
                if wseat not in seat_totals:
                    hand_name = next(h.name for s, h in hand_results if s == wseat)
                    seat_totals[wseat] = {
                        "seat": wseat,
                        "name": self.players[wseat].name,
                        "amount": 0,
                        "hand_name": hand_name,
                        "pot_label": pot.label,
                    }
                seat_totals[wseat]["amount"] += win_amount

        # If any carry_forward remains (all pots had no eligible players), give to first non-folded
        if carry_forward > 0 and players_in:
            fallback = players_in[0]
            fallback.win_chips(carry_forward)
            if fallback.seat not in seat_totals:
                seat_totals[fallback.seat] = {
                    "seat": fallback.seat,
                    "name": fallback.name,
                    "amount": 0,
                    "hand_name": "Unclaimed pot",
                    "pot_label": "Main Pot",
                }
            seat_totals[fallback.seat]["amount"] += carry_forward

        winners_info = list(seat_totals.values())

        # Track showdown win stats
        for wseat in seat_totals:
            self.players[wseat].times_won_at_showdown += 1

        # Log results
        if self.current_hand_log:
            self.current_hand_log.winners = winners_info
            self.current_hand_log.pot_total = self.pot
            self.current_hand_log.community_cards = [c.short for c in self.community_cards]
            # Capture hole cards and hand ranks for history
            for p in self.players:
                if p.hole_cards:
                    self.current_hand_log.hole_cards[p.seat] = [c.short for c in p.hole_cards]
            for seat, result in hand_results:
                self.current_hand_log.hand_ranks[seat] = result.name
            self.hand_histories.append(self.current_hand_log)

        self.phase = GamePhase.BETWEEN_HANDS
        self.street = Street.HAND_OVER

        return {
            "showdown": True,
            "winners": winners_info,
            "hand_results": {s: r.to_dict() for s, r in hand_results},
            "pots": [p.to_dict() for p in pots],
            "state": self.get_state(),
        }

    def _end_hand_single_winner(self, players_in: List[Player]) -> dict:
        """Everyone folded to one player — they win the pot."""
        if players_in:
            winner = players_in[0]
            winner.win_chips(self.pot)
            winners_info = [{
                "seat": winner.seat,
                "name": winner.name,
                "amount": self.pot,
                "hand_name": "Last player standing",
                "pot_label": "Main Pot",
            }]
        else:
            winners_info = []

        if self.current_hand_log:
            self.current_hand_log.winners = winners_info
            self.current_hand_log.pot_total = self.pot
            self.current_hand_log.community_cards = [c.short for c in self.community_cards]
            # Capture hole cards for history
            for p in self.players:
                if p.hole_cards:
                    self.current_hand_log.hole_cards[p.seat] = [c.short for c in p.hole_cards]
            self.hand_histories.append(self.current_hand_log)

        self.phase = GamePhase.BETWEEN_HANDS
        self.street = Street.HAND_OVER

        return {
            "showdown": False,
            "winners": winners_info,
            "pots": [{"amount": self.pot, "eligible_seats": [w["seat"] for w in winners_info], "label": "Main Pot"}],
            "state": self.get_state(),
        }

    # ------------------------------------------------------------------
    # Manual Deal (Cheat Mode)
    # ------------------------------------------------------------------

    def assign_card(self, card_str: str, target: str, seat: Optional[int] = None) -> dict:
        """
        Manually assign a card in manual deal mode.
        
        Args:
            card_str: Short card notation (e.g. "As")
            target: "player" or "community"
            seat: Player seat (required if target is "player")
        """
        card = Card.from_short(card_str)
        if self.deck and not self.deck.remove(card):
            return {"error": f"Card {card_str} is not available (already dealt)"}

        if target == "player":
            if seat is None:
                return {"error": "Must specify seat for player card"}
            player = self.players[seat]
            if len(player.hole_cards) >= 2:
                return {"error": f"{player.name} already has 2 cards"}
            player.hole_cards.append(card)
        elif target == "community":
            if len(self.community_cards) >= 5:
                return {"error": "Community already has 5 cards"}
            self.community_cards.append(card)
        else:
            return {"error": f"Unknown target: {target}"}

        return {"ok": True, "state": self.get_state()}

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def undo_action(self) -> dict:
        """Undo the last action. Returns updated state or error."""
        if not self._undo_stack:
            return {"error": "Nothing to undo"}
        snapshot = self._undo_stack.pop()
        self._restore_snapshot(snapshot)
        return {"ok": True, "state": self.get_state()}

    def undo_hand(self) -> dict:
        """Undo to the start of the current hand."""
        if self._hand_start_snapshot is None:
            return {"error": "No hand to undo"}
        # Remove history entry if the hand was completed and logged
        if self.hand_histories and self.hand_histories[-1].hand_number == self.hand_number:
            self.hand_histories.pop()
        self._restore_snapshot(self._hand_start_snapshot)
        self._undo_stack = []
        self.phase = GamePhase.BETWEEN_HANDS
        self.hand_number -= 1
        return {"ok": True, "state": self.get_state()}

    # ------------------------------------------------------------------
    # State Serialization
    # ------------------------------------------------------------------

    def get_state(self, viewer_seat: Optional[int] = None) -> dict:
        """
        Serialize complete game state for the frontend.
        
        viewer_seat: If set, only reveal that player's hole cards
                    (for hidden hand mode). None reveals all.
        """
        players_data = []
        for p in self.players:
            if viewer_seat is not None:
                # Reveal cards at showdown/hand_over for players still in hand
                at_showdown = self.street in (Street.SHOWDOWN, Street.HAND_OVER)
                reveal = (p.seat == viewer_seat) or (at_showdown and p.is_in_hand)
            else:
                reveal = True
            players_data.append(p.to_dict(reveal_cards=reveal))

        # Position labels
        positions = self._get_positions()

        return {
            "phase": self.phase.value,
            "street": self.street.value,
            "hand_number": self.hand_number,
            "dealer_seat": self.dealer_seat,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "pot": self.pot,
            "community_cards": [c.to_dict() for c in self.community_cards],
            "burned_cards": len(self.burned_cards),
            "players": players_data,
            "positions": positions,
            "action_seat": self.action_seat if self.phase == GamePhase.PLAYING else -1,
            "current_bet": self.betting_round.current_bet if self.betting_round else 0,
            "valid_actions": self.get_valid_actions(self.action_seat) if self.phase == GamePhase.PLAYING and self.action_seat >= 0 else None,
            "can_start_hand": self._can_start_hand(),
            "hand_history": self.hand_histories[-1].to_dict() if self.hand_histories else None,
            "current_actions": [a.to_dict() for a in self.current_hand_log.actions] if self.current_hand_log else [],
            "used_cards": self._get_used_cards(),
            "manual_deal": self.manual_deal,
            "game_over": self._check_game_over(),
        }

    def _check_game_over(self) -> Optional[dict]:
        """Check if only one player has chips — they win the game."""
        if self.phase == GamePhase.PLAYING:
            return None
        alive = [p for p in self.players if not p.is_sitting_out and p.stack > 0]
        if len(alive) == 1:
            return {
                "winner_seat": alive[0].seat,
                "winner_name": alive[0].name,
                "winner_stack": alive[0].stack,
                "hands_played": self.hand_number,
            }
        if len(alive) == 0:
            return {"winner_seat": -1, "winner_name": "Nobody", "winner_stack": 0, "hands_played": self.hand_number}
        return None

    def _can_start_hand(self) -> bool:
        """Check if a new hand can be started."""
        if self.phase == GamePhase.PLAYING:
            return False
        active = [p for p in self.players if not p.is_sitting_out and p.stack > 0]
        return len(active) >= 2

    def _get_used_cards(self) -> List[str]:
        """Return short strings of all cards currently in play (for card picker)."""
        used = []
        for p in self.players:
            for c in p.hole_cards:
                used.append(c.short)
        for c in self.community_cards:
            used.append(c.short)
        for c in self.burned_cards:
            used.append(c.short)
        return used

    # ------------------------------------------------------------------
    # Position / Seat Helpers
    # ------------------------------------------------------------------

    def _active_player_seats(self) -> List[int]:
        """Seats of players who are in the hand (not folded, not sitting out)."""
        return [p.seat for p in self.players if not p.is_sitting_out and p.stack > 0]

    def _next_active_seat(self, current: int) -> int:
        """Find the next active (not folded, not all-in, not sitting out) seat."""
        n = len(self.players)
        for i in range(1, n + 1):
            next_seat = (current + i) % n
            p = self.players[next_seat]
            if p.is_active and not p.is_sitting_out:
                return next_seat
        return current  # Shouldn't happen

    def _next_in_hand_seat(self, current: int) -> int:
        """Find next seat that's still in the hand (including all-in)."""
        n = len(self.players)
        for i in range(1, n + 1):
            next_seat = (current + i) % n
            p = self.players[next_seat]
            if p.is_in_hand:
                return next_seat
        return current

    def _first_postflop_actor(self) -> int:
        """First active player left of dealer for postflop streets."""
        return self._next_active_seat(self.dealer_seat)

    def _get_sb_seat(self) -> int:
        active = self._active_player_seats()
        if len(active) == 2:
            return self.dealer_seat  # Heads-up: dealer is SB
        return self._next_active_seat(self.dealer_seat)

    def _get_bb_seat(self) -> int:
        sb = self._get_sb_seat()
        return self._next_active_seat(sb)

    def _is_bb(self, seat: int) -> bool:
        return seat == self._get_bb_seat()

    def _seats_from(self, start: int, valid_seats: List[int]) -> List[int]:
        """Order seats starting from 'start', wrapping around, filtered to valid_seats."""
        n = len(self.players)
        result = []
        for i in range(n):
            s = (start + i) % n
            if s in valid_seats:
                result.append(s)
        return result

    def _get_positions(self) -> Dict[int, str]:
        """Get position labels for each active seat."""
        active = self._active_player_seats()
        n = len(active)
        if n == 0:
            return {}

        positions = {}
        # Dealer / BTN
        positions[self.dealer_seat] = "BTN"

        if n == 2:
            # Heads-up: Dealer=SB/BTN, other=BB
            positions[self.dealer_seat] = "BTN/SB"
            other = self._next_active_seat(self.dealer_seat)
            positions[other] = "BB"
            return positions

        # SB and BB
        sb = self._next_active_seat(self.dealer_seat)
        bb = self._next_active_seat(sb)
        positions[sb] = "SB"
        positions[bb] = "BB"

        # Remaining positions
        remaining = [s for s in self._seats_from(self._next_active_seat(bb), active)
                     if s not in positions]

        # Standard position names for up to 10 players
        pos_names = {
            1: ["UTG"],
            2: ["UTG", "CO"],
            3: ["UTG", "HJ", "CO"],
            4: ["UTG", "UTG+1", "HJ", "CO"],
            5: ["UTG", "UTG+1", "MP", "HJ", "CO"],
            6: ["UTG", "UTG+1", "MP", "MP+1", "HJ", "CO"],
            7: ["UTG", "UTG+1", "MP", "MP+1", "MP+2", "HJ", "CO"],
        }

        if remaining:
            names = pos_names.get(len(remaining), [f"Seat {i}" for i in range(len(remaining))])
            for seat, name in zip(remaining, names):
                positions[seat] = name

        return positions

    def _is_betting_complete(self) -> bool:
        """Check if current betting round is complete."""
        players_state = []
        for p in self.players:
            if p.is_sitting_out:
                continue
            players_state.append({
                "is_folded": p.is_folded,
                "is_all_in": p.is_all_in,
                "has_acted": p.has_acted,
                "current_bet": p.current_bet,
            })
        return BettingRound.is_round_complete(
            players_state,
            self.betting_round.current_bet if self.betting_round else 0,
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_action(self, seat: int, action: str, amount: int = 0, is_all_in: bool = False) -> None:
        if self.current_hand_log:
            entry = HandLogEntry(
                street=self.street.value,
                seat=seat,
                player_name=self.players[seat].name,
                action=action,
                amount=amount,
                is_all_in=is_all_in,
                timestamp=time.time(),
                pot_after=self.pot,
            )
            self.current_hand_log.actions.append(entry)

    # ------------------------------------------------------------------
    # Snapshot / Undo
    # ------------------------------------------------------------------

    def _snapshot(self) -> dict:
        """Create a serializable snapshot of the entire game state for undo."""
        return {
            "players": [(p.seat, p.name, p.stack, p.hole_cards[:], p.is_folded,
                         p.is_all_in, p.current_bet, p.total_bet_this_hand,
                         p.has_acted) for p in self.players],
            "pot": self.pot,
            "street_pot": self.street_pot,
            "street": self.street,
            "community_cards": self.community_cards[:],
            "burned_cards": self.burned_cards[:],
            "action_seat": self.action_seat,
            "last_aggressor_seat": self.last_aggressor_seat,
            "phase": self.phase,
            "betting_round": {
                "current_bet": self.betting_round.current_bet,
                "last_raise_size": self.betting_round.last_raise_size,
                "num_actions": self.betting_round.num_actions,
                "pot_this_street": self.betting_round.pot_this_street,
                "is_preflop": self.betting_round.is_preflop,
            } if self.betting_round else None,
            "log_len": len(self.current_hand_log.actions) if self.current_hand_log else 0,
        }

    def _restore_snapshot(self, snap: dict) -> None:
        """Restore game state from a snapshot."""
        for (seat, name, stack, hole, folded, allin, cbet, tbet, acted) in snap["players"]:
            p = self.players[seat]
            p.stack = stack
            p.hole_cards = hole
            p.is_folded = folded
            p.is_all_in = allin
            p.current_bet = cbet
            p.total_bet_this_hand = tbet
            p.has_acted = acted

        self.pot = snap["pot"]
        self.street_pot = snap["street_pot"]
        self.street = snap["street"]
        self.community_cards = snap["community_cards"]
        self.burned_cards = snap["burned_cards"]
        self.action_seat = snap["action_seat"]
        self.last_aggressor_seat = snap["last_aggressor_seat"]
        self.phase = snap["phase"]

        if snap["betting_round"] and self.betting_round:
            br = snap["betting_round"]
            self.betting_round.current_bet = br["current_bet"]
            self.betting_round.last_raise_size = br["last_raise_size"]
            self.betting_round.num_actions = br["num_actions"]
            self.betting_round.pot_this_street = br["pot_this_street"]
            self.betting_round.is_preflop = br["is_preflop"]

        if self.current_hand_log:
            self.current_hand_log.actions = self.current_hand_log.actions[:snap["log_len"]]
