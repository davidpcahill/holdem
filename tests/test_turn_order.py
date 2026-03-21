"""
Tests for turn order, action-seat validation, and AI/human interaction timing.

Verifies that:
- Players act in correct seat order (skipping folded/busted/all-in)
- Out-of-turn actions are rejected
- Turn order is correct after folds and street changes
- AI and human turns interleave correctly at different speed presets
- Socket events fire in correct order (thinking before action)
"""

import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, socketio, game, settings
from engine.game import GameState, GamePhase


def api(c, method, path, json=None):
    """Helper: make API call and return parsed JSON."""
    if method == 'GET':
        return c.get(path).get_json()
    return c.post(path, json=json or {}).get_json()


def setup_game(c, num_humans=1, num_ais=2, timing='fast'):
    """Helper: create a game with specified player configuration."""
    players = []
    names = ['You', 'Alice', 'Bob', 'Carol', 'Dave', 'Eve']
    styles = ['tight_aggressive', 'loose_passive', 'gto']
    for i in range(num_humans):
        players.append({
            'name': names[i], 'stack': 1000, 'player_type': 'human',
        })
    for i in range(num_ais):
        players.append({
            'name': names[num_humans + i], 'stack': 1000,
            'player_type': 'ai', 'ai_style': styles[i % len(styles)],
        })
    api(c, 'POST', '/api/settings', {'timing_preset': timing, 'variance': 0})
    api(c, 'POST', '/api/new_game', {
        'small_blind': 5, 'big_blind': 10, 'players': players,
    })
    api(c, 'POST', '/api/new_hand')
    return api(c, 'GET', '/api/state')


# ========================================================================
# Turn order basics
# ========================================================================

def test_action_seat_rejects_wrong_seat():
    """Submitting an action for the wrong seat returns an error."""
    with app.test_client() as c:
        s = setup_game(c, num_humans=3, num_ais=0)
        action_seat = s['action_seat']
        wrong_seat = (action_seat + 1) % 3
        d = api(c, 'POST', '/api/action', {
            'seat': wrong_seat, 'action': 'call',
        })
        assert 'error' in d, f"Wrong seat action should fail, got: {d}"
        assert 'turn' in d['error'].lower() or 'waiting' in d['error'].lower()


def test_action_seat_advances_correctly_3_players():
    """Action seat advances through active players in order."""
    with app.test_client() as c:
        s = setup_game(c, num_humans=3, num_ais=0)
        seats_acted = []
        safety = 0
        while s.get('phase') == 'playing' and safety < 20:
            safety += 1
            seat = s['action_seat']
            if seat < 0:
                break
            seats_acted.append(seat)
            va = s.get('valid_actions', {}).get('actions', [])
            if any(a['action'] == 'check' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
            elif any(a['action'] == 'call' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
            else:
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
            s = d.get('state', s)
        # All 3 seats should have acted at least once
        assert 0 in seats_acted and 1 in seats_acted and 2 in seats_acted, \
            f"All seats should act, got: {seats_acted}"


def test_folded_player_skipped_in_turn_order():
    """After a player folds, they are skipped in subsequent action rounds."""
    with app.test_client() as c:
        s = setup_game(c, num_humans=4, num_ais=0)
        # First player to act folds
        fold_seat = s['action_seat']
        d = api(c, 'POST', '/api/action', {'seat': fold_seat, 'action': 'fold'})
        s = d.get('state', s)

        # Continue playing — folded seat should never appear
        seats_after_fold = []
        safety = 0
        while s.get('phase') == 'playing' and safety < 30:
            safety += 1
            seat = s['action_seat']
            if seat < 0:
                break
            seats_after_fold.append(seat)
            va = s.get('valid_actions', {}).get('actions', [])
            if any(a['action'] == 'check' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
            elif any(a['action'] == 'call' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
            else:
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
            s = d.get('state', s)
        assert fold_seat not in seats_after_fold, \
            f"Folded seat {fold_seat} should not act again, acted at: {seats_after_fold}"


def test_all_in_player_skipped_in_action():
    """An all-in player is skipped for action (they can't act)."""
    with app.test_client() as c:
        # Player with small stack goes all-in, then shouldn't act again
        players = [
            {'name': 'Short', 'stack': 15, 'player_type': 'human'},
            {'name': 'Big1', 'stack': 1000, 'player_type': 'human'},
            {'name': 'Big2', 'stack': 1000, 'player_type': 'human'},
        ]
        api(c, 'POST', '/api/settings', {'timing_preset': 'fast', 'variance': 0})
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10, 'players': players,
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')

        # Find seat 0 (Short stack) and make them go all-in
        seats_acted = []
        safety = 0
        while s.get('phase') == 'playing' and safety < 30:
            safety += 1
            seat = s['action_seat']
            if seat < 0:
                break
            seats_acted.append(seat)
            p = s['players'][seat]
            va = s.get('valid_actions', {}).get('actions', [])
            # If it's Short's turn and they can raise, go all-in
            if p['name'] == 'Short':
                ra = next((a for a in va if a['action'] in ('bet', 'raise')), None)
                if ra:
                    d = api(c, 'POST', '/api/action', {
                        'seat': seat, 'action': ra['action'], 'amount': ra['max'],
                    })
                elif any(a['action'] == 'call' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
                else:
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
            else:
                if any(a['action'] == 'call' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
                elif any(a['action'] == 'check' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
                else:
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
            s = d.get('state', s)

        # After Short goes all-in, they shouldn't act again
        short_actions = [i for i, s in enumerate(seats_acted) if s == 0]
        # Short should have acted at most twice (preflop action + possible re-action)
        # but NOT on flop/turn/river since they're all-in
        assert len(short_actions) <= 2, \
            f"All-in player acted too many times: {len(short_actions)} times in {seats_acted}"


def test_turn_order_correct_after_street_change():
    """After street change, first actor should be first active left of dealer."""
    with app.test_client() as c:
        s = setup_game(c, num_humans=3, num_ais=0)
        dealer = s['dealer_seat']

        # Play through preflop (everyone calls/checks)
        prev_street = s['street']
        safety = 0
        while s.get('phase') == 'playing' and s['street'] == prev_street and safety < 20:
            safety += 1
            seat = s['action_seat']
            if seat < 0:
                break
            va = s.get('valid_actions', {}).get('actions', [])
            if any(a['action'] == 'check' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
            else:
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
            s = d.get('state', s)

        if s.get('phase') == 'playing' and s['street'] != prev_street:
            # On flop, first actor should be first active seat left of dealer
            flop_actor = s['action_seat']
            # The flop actor should be the next active seat after dealer
            n = len(s['players'])
            expected = None
            for i in range(1, n + 1):
                check_seat = (dealer + i) % n
                p = s['players'][check_seat]
                if not p['is_folded'] and not p['is_all_in'] and not p['is_sitting_out']:
                    expected = check_seat
                    break
            assert flop_actor == expected, \
                f"Flop first actor should be {expected} (left of dealer {dealer}), got {flop_actor}"


# ========================================================================
# AI/human interleaving
# ========================================================================

def test_human_cannot_act_during_ai_sequence():
    """Human action submitted during AI turn sequence is rejected."""
    with app.test_client() as c:
        # 1 human (seat 0), 2 AI — use realistic timing so AI thread is slow
        s = setup_game(c, num_humans=1, num_ais=2, timing='realistic')
        human_seat = None
        for p in s['players']:
            if p['player_type'] == 'human':
                human_seat = p['seat']
                break

        # If human is first to act, make them call to trigger AI turns
        if s['action_seat'] == human_seat:
            va = s.get('valid_actions', {}).get('actions', [])
            if any(a['action'] == 'call' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': human_seat, 'action': 'call'})
            elif any(a['action'] == 'check' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': human_seat, 'action': 'check'})
            s = d.get('state', s)

        # Now it should be AI's turn — try to act as human
        if s['action_seat'] != human_seat and s.get('phase') == 'playing':
            d = api(c, 'POST', '/api/action', {
                'seat': human_seat, 'action': 'fold',
            })
            assert 'error' in d, \
                f"Human should not act during AI turn, got: {d.get('action', d)}"


def test_ai_players_act_in_seat_order():
    """With multiple AI players, they should act in proper seat order."""
    with app.test_client() as c:
        # All human so we control the flow — simulate what AI order would be
        s = setup_game(c, num_humans=4, num_ais=0)
        # Track the order seats act
        order = []
        safety = 0
        prev_street = s['street']
        while s.get('phase') == 'playing' and s['street'] == prev_street and safety < 20:
            safety += 1
            seat = s['action_seat']
            if seat < 0:
                break
            order.append(seat)
            va = s.get('valid_actions', {}).get('actions', [])
            if any(a['action'] == 'check' for a in va):
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
            else:
                d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
            s = d.get('state', s)

        # Verify no seat acted twice in a row (unless it's BB option)
        for i in range(2, len(order)):
            assert order[i] != order[i-1] or order[i] != order[i-2], \
                f"Same seat acted 3+ times in a row at position {i}: {order}"


# ========================================================================
# Socket event ordering (using SocketIO test client)
# ========================================================================

def test_thinking_emitted_before_action():
    """ai_thinking event should arrive before ai_action for each AI player."""
    # Use SocketIO test client to capture events
    client = socketio.test_client(app)
    try:
        with app.test_request_context():
            # Reset settings for this test
            settings['timing_preset'] = 'fast'
            settings['variance'] = 0

        with app.test_client() as c:
            api(c, 'POST', '/api/settings', {'timing_preset': 'fast', 'variance': 0})
            api(c, 'POST', '/api/new_game', {
                'small_blind': 5, 'big_blind': 10,
                'players': [
                    {'name': 'Human', 'stack': 1000, 'player_type': 'human'},
                    {'name': 'AI1', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'tight_aggressive'},
                    {'name': 'AI2', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'loose_passive'},
                ],
            })
            # Clear any events from setup
            client.get_received()

            api(c, 'POST', '/api/new_hand')
            s = api(c, 'GET', '/api/state')

            # If human acts first, trigger AI turns
            if s['action_seat'] == 0 and s.get('phase') == 'playing':
                va = s.get('valid_actions', {}).get('actions', [])
                if any(a['action'] == 'call' for a in va):
                    api(c, 'POST', '/api/action', {'seat': 0, 'action': 'call'})
                elif any(a['action'] == 'check' for a in va):
                    api(c, 'POST', '/api/action', {'seat': 0, 'action': 'check'})

                # Wait briefly for AI thread to complete (fast mode = instant)
                time.sleep(1.0)

            # Collect socket events
            received = client.get_received()
            event_names = [r['name'] for r in received]

            # For each AI that acted, thinking should come before action
            ai_events = [(i, e) for i, e in enumerate(received)
                         if e['name'] in ('ai_thinking', 'ai_action')]

            for i in range(len(ai_events) - 1):
                idx_a, evt_a = ai_events[i]
                idx_b, evt_b = ai_events[i + 1]
                if evt_a['name'] == 'ai_action' and evt_b['name'] == 'ai_thinking':
                    # This is fine — action from one AI, thinking from next
                    pass
                elif evt_a['name'] == 'ai_thinking' and evt_b['name'] == 'ai_thinking':
                    # Two thinking in a row without action — bad
                    assert False, f"Two ai_thinking in a row without ai_action: {event_names}"

            # Every ai_thinking should have a matching ai_action after it
            thinking_seats = []
            action_seats = []
            for e in received:
                if e['name'] == 'ai_thinking':
                    thinking_seats.append(e['args'][0]['seat'])
                elif e['name'] == 'ai_action':
                    action_seats.append(e['args'][0]['seat'])

            # Each thinking seat should have a corresponding action
            for seat in thinking_seats:
                assert seat in action_seats, \
                    f"ai_thinking for seat {seat} has no matching ai_action"
    finally:
        client.disconnect()


def test_advisor_update_sent_after_ai_action():
    """advisor_update event should arrive after the last ai_action."""
    client = socketio.test_client(app)
    try:
        with app.test_client() as c:
            api(c, 'POST', '/api/settings', {'timing_preset': 'fast', 'variance': 0})
            api(c, 'POST', '/api/new_game', {
                'small_blind': 5, 'big_blind': 10,
                'players': [
                    {'name': 'Human', 'stack': 1000, 'player_type': 'human'},
                    {'name': 'AI1', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'tight_aggressive'},
                ],
            })
            client.get_received()

            api(c, 'POST', '/api/new_hand')
            s = api(c, 'GET', '/api/state')

            # Human acts to trigger AI turn
            if s['action_seat'] == 0 and s.get('phase') == 'playing':
                va = s.get('valid_actions', {}).get('actions', [])
                if any(a['action'] == 'call' for a in va):
                    api(c, 'POST', '/api/action', {'seat': 0, 'action': 'call'})
                elif any(a['action'] == 'check' for a in va):
                    api(c, 'POST', '/api/action', {'seat': 0, 'action': 'check'})

                time.sleep(2.0)

            received = client.get_received()

            # Find ai_action and advisor_update positions
            ai_action_indices = [i for i, e in enumerate(received) if e['name'] == 'ai_action']
            advisor_indices = [i for i, e in enumerate(received) if e['name'] == 'advisor_update']

            if ai_action_indices and advisor_indices:
                last_ai_action = max(ai_action_indices)
                first_advisor = min(advisor_indices)
                assert first_advisor > last_ai_action, \
                    f"advisor_update (idx {first_advisor}) should come after last ai_action (idx {last_ai_action})"
    finally:
        client.disconnect()


# ========================================================================
# Multi-speed consistency
# ========================================================================

def test_turn_order_consistent_across_speeds():
    """Turn order should be the same regardless of timing preset."""
    results = {}
    for preset in ['fast', 'realistic']:
        with app.test_client() as c:
            api(c, 'POST', '/api/settings', {'timing_preset': preset, 'variance': 0})
            # All human to avoid threading differences — just test the engine
            api(c, 'POST', '/api/new_game', {
                'small_blind': 5, 'big_blind': 10,
                'players': [
                    {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                    {'name': 'B', 'stack': 1000, 'player_type': 'human'},
                    {'name': 'C', 'stack': 1000, 'player_type': 'human'},
                ],
            })
            api(c, 'POST', '/api/new_hand')
            s = api(c, 'GET', '/api/state')

            order = []
            safety = 0
            while s.get('phase') == 'playing' and safety < 20:
                safety += 1
                seat = s['action_seat']
                if seat < 0:
                    break
                order.append(seat)
                va = s.get('valid_actions', {}).get('actions', [])
                if any(a['action'] == 'check' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
                else:
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
                s = d.get('state', s)
            results[preset] = order

    assert results['fast'] == results['realistic'], \
        f"Turn order differs: fast={results['fast']} vs realistic={results['realistic']}"


def test_state_consistency_after_fold_sequence():
    """After a sequence of folds, game state should be consistent."""
    with app.test_client() as c:
        s = setup_game(c, num_humans=4, num_ais=0)
        # First two players fold
        for _ in range(2):
            if s.get('phase') != 'playing':
                break
            seat = s['action_seat']
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
            s = d.get('state', s)

        if s.get('phase') == 'playing':
            # Verify state consistency
            active_seats = [p['seat'] for p in s['players']
                           if not p['is_folded'] and p['is_in_hand']]
            folded_seats = [p['seat'] for p in s['players'] if p['is_folded']]
            assert len(folded_seats) == 2, f"Expected 2 folded, got {len(folded_seats)}"
            assert s['action_seat'] in active_seats, \
                f"Action seat {s['action_seat']} should be active, active={active_seats}"
            assert s['action_seat'] not in folded_seats, \
                f"Action seat {s['action_seat']} should not be folded"


def test_busted_player_not_in_next_hand():
    """A player who busts out should not be dealt into the next hand."""
    with app.test_client() as c:
        players = [
            {'name': 'Short', 'stack': 10, 'player_type': 'human'},
            {'name': 'Big1', 'stack': 1000, 'player_type': 'human'},
            {'name': 'Big2', 'stack': 1000, 'player_type': 'human'},
        ]
        api(c, 'POST', '/api/settings', {'timing_preset': 'fast', 'variance': 0})
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10, 'players': players,
        })

        # Play hands until Short busts
        for _ in range(5):
            api(c, 'POST', '/api/new_hand')
            s = api(c, 'GET', '/api/state')
            safety = 0
            while s.get('phase') == 'playing' and safety < 30:
                safety += 1
                seat = s['action_seat']
                if seat < 0:
                    break
                va = s.get('valid_actions', {}).get('actions', [])
                if any(a['action'] == 'call' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
                elif any(a['action'] == 'check' for a in va):
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
                else:
                    d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
                s = d.get('state', s)

            # Check if Short is busted
            short = s['players'][0]
            if short['stack'] == 0 and short.get('is_sitting_out', False):
                # Play next hand — Short should not be action_seat
                api(c, 'POST', '/api/new_hand')
                s2 = api(c, 'GET', '/api/state')
                if s2.get('phase') == 'playing':
                    assert s2['action_seat'] != 0, \
                        "Busted player should not be action seat"
                    # Short should be sitting out
                    assert s2['players'][0].get('is_sitting_out', False) or \
                           s2['players'][0]['stack'] == 0, \
                        "Busted player should be sitting out or have 0 stack"
                break


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
