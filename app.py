"""
Texas Hold'em Poker Advisor & Simulator — Flask Application

Single entry point. Run with: python app.py
Serves the web UI and provides REST + WebSocket API for the game engine.
"""

import os
import json
import time
import threading
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit

from engine.game import GameState, GamePhase, Street
from engine.player import PlayerType, AIStyle
from engine.equity import EquityCalculator
from engine.ai import AIEngine, AIDecision
from engine.advisor import Advisor

app = Flask(__name__)
app.secret_key = os.urandom(24)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ──────────────────────────────────────────────
# Global game state (single-user local tool)
# ──────────────────────────────────────────────
game = GameState()
ai_engine = AIEngine(timing_preset="realistic", variance=0.3)
_equity_cache = {}
_ai_lock = threading.Lock()
_game_version = 0  # Incremented on new game; AI threads check this to abort

# Settings
settings = {
    "timing_preset": "realistic",
    "variance": 30,           # 0-100
    "deal_speed_ms": 150,
    "street_reveal_ms": 800,
    "pass_play_countdown": 3,
    "auto_advance": False,
    "auto_advance_delay": 3,
    "hide_hands": True,
    "peek_enabled": False,
    "burn_cards": True,
}


def _get_full_state(viewer_seat=None):
    """Build the complete state payload for the frontend."""
    state = game.get_state(viewer_seat=viewer_seat)
    state["settings"] = settings
    state["hand_histories"] = [h.to_dict() for h in game.hand_histories[-20:]]
    return state


def _run_ai_turn():
    """
    Process AI player turns in sequence.
    Runs in a background thread, pushes state updates via SocketIO.
    Only emits ai_action events — no redundant state_update emits that can race.
    """
    my_version = _game_version
    with _ai_lock:
        while (game.phase == GamePhase.PLAYING
               and game.action_seat >= 0
               and game.action_seat < len(game.players)
               and _game_version == my_version):

            player = game.players[game.action_seat]
            if player.player_type != PlayerType.AI:
                break  # Human's turn — stop and wait
            if not player.is_active:
                break

            # Calculate think time
            think_time = ai_engine.calculate_think_time(player)

            # Get equity for AI decision
            community = game.community_cards
            num_opponents = len([p for p in game.players if p.is_in_hand and p.seat != player.seat])

            if not community:
                equity = EquityCalculator.preflop_equity(player.hole_cards, num_opponents)
            else:
                equity = EquityCalculator.monte_carlo(
                    player.hole_cards, community, num_opponents, simulations=2000
                )

            # Get valid actions
            valid = game.get_valid_actions(player.seat)
            positions = game._get_positions()
            position = positions.get(player.seat, "")

            # Make decision
            decision = ai_engine.decide(
                player=player,
                valid_actions=valid,
                equity=equity,
                community_cards=community,
                pot=game.pot,
                street=game.street.value,
                position=position,
                num_opponents=num_opponents,
            )

            # Wait for think time (emit "thinking" state)
            socketio.emit("ai_thinking", {
                "seat": player.seat,
                "name": player.name,
                "think_time": think_time,
            })
            time.sleep(think_time)

            # Abort if game was reset during think time
            if _game_version != my_version:
                break

            # Capture street BEFORE action (to detect street changes)
            pre_street = game.street.value

            # Execute the action
            result = game.process_action(player.seat, decision.action, decision.amount)

            # Build the emit payload
            action_state = _get_full_state()
            post_street = game.street.value
            street_changed = pre_street != post_street and post_street not in ('showdown', 'hand_over')

            # If next player is human, piggyback advisor
            if (game.phase == GamePhase.PLAYING
                    and game.action_seat >= 0
                    and game.action_seat < len(game.players)):
                next_p = game.players[game.action_seat]
                if next_p.player_type == PlayerType.HUMAN and next_p.hole_cards:
                    try:
                        action_state["_advisor"] = _compute_advisor(next_p.seat)
                    except Exception:
                        pass

            # Single emit per action — the ONLY state push during AI play
            socketio.emit("ai_action", {
                "seat": player.seat,
                "name": player.name,
                "decision": decision.to_dict(),
                "result": result,
                "state": action_state,
                "street_changed": street_changed,
            })

            # If hand ended, stop (no separate state_update — ai_action already has it)
            if game.phase != GamePhase.PLAYING:
                break

            # Pause between AI actions for readability
            # Longer pause when street changed so frontend can show the transition
            time.sleep(0.8 if street_changed else 0.2)


# ──────────────────────────────────────────────
# Routes — Page
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────
# Routes — REST API
# ──────────────────────────────────────────────

@app.route("/api/state")
def api_state():
    return jsonify(_get_full_state())


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    """Configure and start a new game."""
    global game, ai_engine, _game_version
    data = request.json or {}

    _game_version += 1
    game = GameState()

    # Explicitly reset manual deal
    game.manual_deal = False

    # Set blinds
    sb = data.get("small_blind", 5)
    bb = data.get("big_blind", 10)
    game.set_blinds(sb, bb)

    # Blind escalation
    game.auto_escalate = data.get("auto_escalate", False)
    game.escalate_interval = data.get("escalate_interval", 10)
    game.escalate_multiplier = data.get("escalate_multiplier", 1.5)
    game.burn_cards_enabled = settings.get("burn_cards", True)

    # Add players
    players = data.get("players", [])
    if not players:
        # Default: 1 human + 2 AI
        players = [
            {"name": "You", "stack": 1000, "player_type": "human"},
            {"name": "Alice (TAG)", "stack": 1000, "player_type": "ai", "ai_style": "tight_aggressive"},
            {"name": "Bob (LP)", "stack": 1000, "player_type": "ai", "ai_style": "loose_passive"},
        ]

    for p in players:
        game.add_player(
            name=p.get("name", f"Player {len(game.players)+1}"),
            stack=p.get("stack", 1000),
            player_type=p.get("player_type", "human"),
            ai_style=p.get("ai_style", "tight_aggressive"),
            color=p.get("color"),
        )

    # Update AI engine settings
    ai_engine = AIEngine(
        timing_preset=settings.get("timing_preset", "realistic"),
        variance=settings.get("variance", 30) / 100.0,
    )

    full_state = _get_full_state()
    # Push state to all socket clients to clear stale data
    socketio.emit("state_update", full_state)
    return jsonify({"ok": True, "state": full_state})


@app.route("/api/new_hand", methods=["POST"])
def api_new_hand():
    """Start a new hand."""
    try:
        game.burn_cards_enabled = settings.get("burn_cards", True)
        state = game.new_hand()
        full = _get_full_state()

        # If first actor is AI, trigger AI processing
        if (game.phase == GamePhase.PLAYING
                and game.action_seat >= 0
                and game.players[game.action_seat].player_type == PlayerType.AI):
            threading.Thread(target=_run_ai_turn, daemon=True).start()

        return jsonify({"ok": True, "state": full})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/action", methods=["POST"])
def api_action():
    """Process a player action."""
    data = request.json or {}
    seat = data.get("seat")
    action = data.get("action")
    amount = data.get("amount", 0)

    if seat is None or action is None:
        return jsonify({"error": "Missing seat or action"}), 400

    result = game.process_action(seat, action, amount)

    if "error" in result:
        return jsonify(result), 400

    full_state = _get_full_state()
    result["state"] = full_state

    # Broadcast state update
    socketio.emit("state_update", full_state)

    # If next actor is AI, trigger AI processing (it will push advisor when done)
    if (game.phase == GamePhase.PLAYING
            and game.action_seat >= 0
            and game.players[game.action_seat].player_type == PlayerType.AI):
        threading.Thread(target=_run_ai_turn, daemon=True).start()
    elif (game.phase == GamePhase.PLAYING
            and game.action_seat >= 0
            and game.players[game.action_seat].player_type == PlayerType.HUMAN
            and game.players[game.action_seat].hole_cards):
        # Next actor is human — include advisor data in response
        try:
            result["_advisor"] = _compute_advisor(game.action_seat)
        except Exception:
            pass

    return jsonify(result)


@app.route("/api/advisor", methods=["POST"])
def api_advisor():
    """Get advisor recommendations for a human player."""
    data = request.json or {}
    seat = data.get("seat", 0)
    try:
        result = _compute_advisor(seat)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


def _compute_advisor(seat: int) -> dict:
    """Compute advisor data for a given seat. Used by API and socket push."""
    if seat >= len(game.players):
        raise ValueError("Invalid seat")

    player = game.players[seat]
    if not player.hole_cards:
        raise ValueError("Player has no cards")

    community = game.community_cards
    opponents = len([p for p in game.players if p.is_in_hand and p.seat != seat])

    if not community:
        equity = EquityCalculator.preflop_equity(player.hole_cards, opponents)
    else:
        equity = EquityCalculator.monte_carlo(
            player.hole_cards, community, opponents, simulations=5000
        )

    valid = game.get_valid_actions(seat)
    positions = game._get_positions()
    position = positions.get(seat, "")
    to_call = max(0, (game.betting_round.current_bet if game.betting_round else 0) - player.current_bet)

    advice = Advisor.analyze(
        hole_cards=player.hole_cards,
        community=community,
        pot=game.pot,
        to_call=to_call,
        stack=player.stack,
        position=position,
        num_opponents=opponents,
        valid_actions=valid,
        equity=equity,
    )

    return advice.to_dict()


@app.route("/api/deal_card", methods=["POST"])
def api_deal_card():
    """Manually assign a card (cheat mode)."""
    data = request.json or {}
    card_str = data.get("card")
    target = data.get("target")
    seat = data.get("seat")

    if not card_str or not target:
        return jsonify({"error": "Missing card or target"}), 400

    result = game.assign_card(card_str, target, seat)
    if "error" in result:
        return jsonify(result), 400

    return jsonify({"ok": True, "state": _get_full_state()})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    """Undo last action."""
    result = game.undo_action()
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": _get_full_state()})


@app.route("/api/undo_hand", methods=["POST"])
def api_undo_hand():
    """Undo entire current hand."""
    result = game.undo_hand()
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": _get_full_state()})


@app.route("/api/toggle_manual_deal", methods=["POST"])
def api_toggle_manual_deal():
    """Toggle manual deal mode (card picker / cheat mode)."""
    data = request.json or {}
    game.manual_deal = data.get("enabled", not game.manual_deal)
    return jsonify({"ok": True, "manual_deal": game.manual_deal, "state": _get_full_state()})


@app.route("/api/unassign_card", methods=["POST"])
def api_unassign_card():
    """Remove a manually assigned card back to the deck."""
    data = request.json or {}
    card_str = data.get("card")
    target = data.get("target")
    seat = data.get("seat")

    if not card_str:
        return jsonify({"error": "Missing card"}), 400

    from engine.deck import Card
    card = Card.from_short(card_str)

    if target == "player" and seat is not None:
        player = game.players[seat]
        if card in player.hole_cards:
            player.hole_cards.remove(card)
            if game.deck:
                game.deck._cards.append(card)
    elif target == "community":
        if card in game.community_cards:
            game.community_cards.remove(card)
            if game.deck:
                game.deck._cards.append(card)

    return jsonify({"ok": True, "state": _get_full_state()})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Get or update settings."""
    global settings, ai_engine
    if request.method == "POST":
        data = request.json or {}
        for key in data:
            if key in settings:
                settings[key] = data[key]
        # Update AI engine with new settings
        ai_engine = AIEngine(
            timing_preset=settings.get("timing_preset", "realistic"),
            variance=settings.get("variance", 30) / 100.0,
        )
        game.burn_cards_enabled = settings.get("burn_cards", True)
        return jsonify({"ok": True, "settings": settings})
    return jsonify(settings)


@app.route("/api/update_player", methods=["POST"])
def api_update_player():
    """Update a player's settings between hands."""
    data = request.json or {}
    seat = data.get("seat")
    if seat is None or seat >= len(game.players):
        return jsonify({"error": "Invalid seat"}), 400

    if game.phase == GamePhase.PLAYING:
        return jsonify({"error": "Cannot modify players during a hand"}), 400

    p = game.players[seat]
    if "name" in data:
        p.name = data["name"]
    if "player_type" in data:
        p.player_type = PlayerType(data["player_type"])
    if "ai_style" in data:
        p.ai_style = AIStyle(data["ai_style"])
    if "color" in data:
        p.color = data["color"]
    if "stack" in data:
        p.stack = int(data["stack"])

    return jsonify({"ok": True, "state": _get_full_state()})


@app.route("/api/export_history")
def api_export_history():
    """Export hand history as formatted text."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  Texas Hold'em — Hand History Export")
    lines.append(f"  Blinds: {game.small_blind}/{game.big_blind}")
    lines.append(f"  Hands played: {game.hand_number}")
    lines.append("=" * 60)
    lines.append("")

    for hh in game.hand_histories:
        lines.append(f"--- Hand #{hh.hand_number} ---")
        lines.append(f"Community: {' '.join(hh.community_cards) if hh.community_cards else '(none)'}")

        current_street = ""
        for action in hh.actions:
            a = action if isinstance(action, dict) else action.to_dict()
            if a["street"] != current_street:
                current_street = a["street"]
                lines.append(f"  [{current_street.upper()}]")
            amt = f" ${a['amount']}" if a.get("amount", 0) > 0 else ""
            allin = " (ALL-IN)" if a.get("is_all_in") else ""
            lines.append(f"    {a['player_name']} {a['action']}{amt}{allin}")

        if hh.winners:
            for w in hh.winners:
                lines.append(f"  >> {w['name']} wins ${w['amount']} ({w['hand_name']})")
        lines.append("")

    return "\n".join(lines), 200, {"Content-Type": "text/plain; charset=utf-8"}


# ──────────────────────────────────────────────
# WebSocket Events
# ──────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    emit("state_update", _get_full_state())


@socketio.on("request_state")
def handle_request_state():
    emit("state_update", _get_full_state())


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Texas Hold'em Poker Advisor & Simulator")
    print("  Open http://localhost:5000 in your browser")
    print("="*55 + "\n")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)
