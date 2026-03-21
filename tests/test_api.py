"""
Integration tests for the Flask API layer.

Uses all-human players since AI background threads don't run in
Flask's test client. Tests every endpoint and feature.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app


def api(c, method, path, json=None):
    """Helper: make API call and return parsed JSON."""
    if method == 'GET':
        return c.get(path).get_json()
    return c.post(path, json=json or {}).get_json()


def play_hand_to_end(c):
    """Play a hand to completion using check/call/fold."""
    state = api(c, 'GET', '/api/state')
    safety = 0
    result = None
    while state.get('phase') == 'playing' and safety < 30:
        safety += 1
        seat = state.get('action_seat', -1)
        if seat < 0:
            break
        va = state.get('valid_actions', {}).get('actions', [])
        if any(a['action'] == 'check' for a in va):
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
        elif any(a['action'] == 'call' for a in va):
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        else:
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
        state = d.get('state', state)
        if d.get('showdown') or d.get('winners'):
            result = d
            break
    return result


# ════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════

def test_new_game_and_state():
    with app.test_client() as c:
        d = api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        assert d['ok']
        s = d['state']
        # New game without dealing is still in setup/between_hands
        assert s['phase'] in ('setup', 'between_hands')
        assert len(s['players']) == 2
        assert s['small_blind'] == 5
        assert s['big_blind'] == 10
        assert s['can_start_hand'] is True


def test_new_hand_deals_and_posts_blinds():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        d = api(c, 'POST', '/api/new_hand')
        assert d['ok']
        s = d['state']
        assert s['phase'] == 'playing'
        assert s['pot'] == 15  # 5 + 10
        assert s['hand_number'] == 1
        # Players should have cards (revealed since viewer_seat is None)
        assert any(p.get('hole_cards') for p in s['players'])
        # Blinds should be logged
        actions = s['current_actions']
        assert len(actions) >= 2
        assert actions[0]['action'] == 'small_blind'
        assert actions[1]['action'] == 'big_blind'


def test_full_hand_lifecycle():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        result = play_hand_to_end(c)
        assert result is not None
        assert 'winners' in result
        assert len(result['winners']) >= 1


def test_multiple_hands_with_history():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        for _ in range(3):
            api(c, 'POST', '/api/new_hand')
            play_hand_to_end(c)

        s = api(c, 'GET', '/api/state')
        assert len(s['hand_histories']) == 3
        for hh in s['hand_histories']:
            assert len(hh['actions']) >= 3  # SB, BB, at least one action
            assert len(hh['winners']) >= 1


def test_fold_action():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        seat = s['action_seat']
        d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
        assert 'winners' in d
        # Non-folder should win
        winner_seat = d['winners'][0]['seat']
        assert winner_seat != seat


def test_raise_action():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        seat = s['action_seat']
        d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'raise', 'amount': 30})
        assert 'error' not in d
        s2 = d.get('state', api(c, 'GET', '/api/state'))
        assert s2['pot'] > 15


def test_advisor():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        seat = s['action_seat']
        adv = api(c, 'POST', '/api/advisor', {'seat': seat})
        assert 'equity' in adv
        assert adv['equity']['win'] > 0
        assert len(adv['actions']) > 0
        assert 'hand_name' in adv


def test_undo():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        seat = s['action_seat']
        stack_before = s['players'][seat]['stack']
        pot_before = s['pot']

        api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        d = api(c, 'POST', '/api/undo')
        assert d['ok']
        s2 = api(c, 'GET', '/api/state')
        assert s2['players'][seat]['stack'] == stack_before
        assert s2['pot'] == pot_before


def test_manual_deal():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/toggle_manual_deal', {'enabled': True})
        api(c, 'POST', '/api/new_hand')

        # No cards dealt
        s = api(c, 'GET', '/api/state')
        assert s['manual_deal'] is True
        assert len(s['used_cards']) == 0  # No auto-dealt cards (blinds are chips not cards)

        # Assign cards
        api(c, 'POST', '/api/deal_card', {'card': 'As', 'target': 'player', 'seat': 0})
        api(c, 'POST', '/api/deal_card', {'card': 'Kh', 'target': 'player', 'seat': 0})
        s = api(c, 'GET', '/api/state')
        assert 'As' in s['used_cards']
        assert 'Kh' in s['used_cards']

        # Unassign
        api(c, 'POST', '/api/unassign_card', {'card': 'As', 'target': 'player', 'seat': 0})
        s = api(c, 'GET', '/api/state')
        assert 'As' not in s['used_cards']


def test_export_history():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        play_hand_to_end(c)

        r = app.test_client().get('/api/export_history')
        # Need same client for state
        with app.test_client() as c2:
            pass
        # Use original client
        text = c.get('/api/export_history').data.decode()
        assert 'Hand History Export' in text
        assert 'Hand #1' in text
        assert 'small_blind' in text


def test_settings():
    with app.test_client() as c:
        d = api(c, 'POST', '/api/settings', {'variance': 80, 'timing_preset': 'fast'})
        assert d['ok']
        s = api(c, 'GET', '/api/settings')
        assert s['variance'] == 80
        assert s['timing_preset'] == 'fast'


def test_player_edit():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'gto'},
            ]
        })
        d = api(c, 'POST', '/api/update_player', {
            'seat': 1, 'name': 'Edited', 'ai_style': 'loose_passive', 'color': '#112233'
        })
        assert d['ok']
        p = d['state']['players'][1]
        assert p['name'] == 'Edited'
        assert p['ai_style'] == 'loose_passive'
        assert p['color'] == '#112233'


def test_player_edit_blocked_during_hand():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        d = api(c, 'POST', '/api/update_player', {'seat': 0, 'name': 'X'})
        assert 'error' in d


def test_html_features():
    with app.test_client() as c:
        html = c.get('/').data.decode()
        features = [
            'sounds.js', 'toggleSound', 'editingPlayer', 'openPlayerEditor',
            'passPlayActive', 'hideHands', 'assignPickerCard', 'historyList',
            'sidebar-open', 'shouldShowCards', 'copyHistory', 'downloadHistory',
            'positionTooltip', 'formatAIStyle', 'advisorEnabled',
        ]
        missing = [f for f in features if f not in html]
        assert not missing, f'Missing HTML features: {missing}'


def test_state_completeness():
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 500, 'player_type': 'human'},
                {'name': 'B', 'stack': 500, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        required = ['phase', 'street', 'hand_number', 'pot', 'community_cards',
                     'players', 'positions', 'action_seat', 'used_cards',
                     'manual_deal', 'settings', 'hand_histories', 'current_actions']
        missing = [k for k in required if k not in s]
        assert not missing, f'Missing state keys: {missing}'
        # Actions must be dicts
        for a in s.get('current_actions', []):
            assert isinstance(a, dict), f'Action not dict: {type(a)}'


def test_undo_blocked_during_ai_turn():
    """Undo should be blocked when it's an AI player's turn."""
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'tight_aggressive'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        # In heads-up, dealer(seat 0) is SB and acts first preflop
        # seat 0 is human, seat 1 is AI
        seat = s['action_seat']
        # Human calls
        api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        # Now it's AI's turn (BB check/option)
        # Try to undo — should be blocked
        d = c.post('/api/undo', json={}).get_json()
        assert 'error' in d, f"Undo should be blocked during AI turn, got: {d}"


def test_undo_hand_blocked_during_ai_turn():
    """Undo hand should be blocked when it's an AI player's turn."""
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'ai', 'ai_style': 'tight_aggressive'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s = api(c, 'GET', '/api/state')
        seat = s['action_seat']
        api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        # Now it's AI's turn — undo hand should be blocked
        d = c.post('/api/undo_hand', json={}).get_json()
        assert 'error' in d, f"Undo hand should be blocked during AI turn, got: {d}"


# ════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════

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
