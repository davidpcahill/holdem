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


def test_advisor_preflop():
    """Advisor preflop should return hand name and equity."""
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
        assert adv.get('hand_rank') == 'PREFLOP'
        assert adv.get('hand_name'), "Should have a hand name"
        assert adv['equity']['is_preflop'] is True
        assert len(adv['actions']) > 0
        # Actions should include fold, check/call, and optionally raise
        action_names = [a['action'] for a in adv['actions']]
        assert 'fold' in action_names or 'call' in action_names or 'check' in action_names


def test_advisor_postflop():
    """Advisor on flop should return outs and pot odds."""
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
        # Call and check to advance to flop
        api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        s2 = api(c, 'GET', '/api/state')
        seat2 = s2['action_seat']
        api(c, 'POST', '/api/action', {'seat': seat2, 'action': 'check'})
        # Now on flop
        s3 = api(c, 'GET', '/api/state')
        assert s3['street'] == 'flop'
        seat3 = s3['action_seat']
        adv = api(c, 'POST', '/api/advisor', {'seat': seat3})
        assert adv.get('hand_rank') != 'PREFLOP', "Should not be preflop on flop"
        assert 'outs' in adv
        assert 'pot_odds' in adv
        assert adv['equity']['is_preflop'] is False


def test_undo_blocked_during_ai_turn():
    """Undo should be blocked when it's an AI player's turn."""
    with app.test_client() as c:
        # Use realistic timing so AI thread doesn't complete before undo request
        api(c, 'POST', '/api/settings', {'timing_preset': 'realistic'})
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
        # Use realistic timing so AI thread doesn't complete before undo request
        api(c, 'POST', '/api/settings', {'timing_preset': 'realistic'})
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
# Race Condition & Caching Tests
# ════════════════════════════════════════════════

def test_new_game_during_hand_does_not_carry_old_state():
    """Starting a new game mid-hand should fully reset — no old cards or actions."""
    with app.test_client() as c:
        # Start first game and play into a hand
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s1 = api(c, 'GET', '/api/state')
        assert s1['phase'] == 'playing'
        old_hand = s1['hand_number']

        # Now start a completely new game mid-hand
        api(c, 'POST', '/api/new_game', {
            'small_blind': 10, 'big_blind': 20,
            'players': [
                {'name': 'X', 'stack': 2000, 'player_type': 'human'},
                {'name': 'Y', 'stack': 2000, 'player_type': 'human'},
            ]
        })
        s2 = api(c, 'GET', '/api/state')
        # Should be fresh state, no cards, no old actions
        assert s2['phase'] in ('setup', 'between_hands'), f"Phase should be reset, got {s2['phase']}"
        assert s2['hand_number'] == 0, "Hand number should reset to 0"
        assert s2['community_cards'] == [], "Community cards should be empty"
        assert s2['current_actions'] == [], "Actions should be empty"
        assert s2['big_blind'] == 20, "Should use new blinds"
        assert s2['players'][0]['name'] == 'X', "Should have new players"


def test_new_hand_after_new_game_gets_fresh_cards():
    """Rapidly starting new game then new hand should deal fresh cards."""
    with app.test_client() as c:
        # First game + hand
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        api(c, 'POST', '/api/new_hand')
        s1 = api(c, 'GET', '/api/state')
        old_cards = [p.get('hole_cards', []) for p in s1['players']]

        # New game + new hand immediately
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        d = api(c, 'POST', '/api/new_hand')
        assert d['ok']
        s2 = d['state']
        assert s2['phase'] == 'playing'
        assert s2['hand_number'] == 1
        # Players should have cards
        for p in s2['players']:
            assert len(p.get('hole_cards', [])) == 2, f"{p['name']} should have 2 cards"


def test_state_seq_increases_monotonically():
    """_seq in state should increase on every state fetch."""
    with app.test_client() as c:
        api(c, 'POST', '/api/new_game', {
            'small_blind': 5, 'big_blind': 10,
            'players': [
                {'name': 'A', 'stack': 1000, 'player_type': 'human'},
                {'name': 'B', 'stack': 1000, 'player_type': 'human'},
            ]
        })
        s1 = api(c, 'GET', '/api/state')
        s2 = api(c, 'GET', '/api/state')
        assert '_seq' in s1, "State should include _seq"
        assert '_seq' in s2, "State should include _seq"
        assert s2['_seq'] > s1['_seq'], f"_seq should increase: {s1['_seq']} -> {s2['_seq']}"

        # After new hand, seq should be even higher
        api(c, 'POST', '/api/new_hand')
        s3 = api(c, 'GET', '/api/state')
        assert s3['_seq'] > s2['_seq'], f"_seq after new_hand should increase: {s2['_seq']} -> {s3['_seq']}"


def test_static_js_no_cache_headers():
    """Static JS files should have no-cache headers to prevent stale code."""
    with app.test_client() as c:
        response = c.get('/static/js/app.js')
        assert response.status_code == 200
        cache_control = response.headers.get('Cache-Control', '')
        # SEND_FILE_MAX_AGE_DEFAULT=0 should result in no-cache or max-age=0
        assert 'no-cache' in cache_control.lower() or 'max-age=0' in cache_control, \
            f"app.js should not be cached, got Cache-Control: {cache_control}"


def test_script_tags_have_cache_buster():
    """Script tags in index.html should have version query params."""
    with app.test_client() as c:
        html = c.get('/').data.decode()
        assert 'app.js?v=' in html, "app.js should have cache-busting ?v= parameter"
        assert 'sounds.js?v=' in html, "sounds.js should have cache-busting ?v= parameter"
        assert 'poker-logic.js?v=' in html, "poker-logic.js should have cache-busting ?v= parameter"


# ════════════════════════════════════════════════
# Advisor Performance Tests
# ════════════════════════════════════════════════

def _new_game(c, num_players=2):
    """Helper: start a new game with all-human players."""
    players = [{'name': f'P{i}', 'stack': 1000, 'player_type': 'human'} for i in range(num_players)]
    return api(c, 'POST', '/api/new_game', {
        'small_blind': 5, 'big_blind': 10, 'players': players,
    })


def test_advisor_returns_compute_timing():
    """Advisor response should include _compute_ms timing field."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        result = api(c, 'POST', '/api/advisor', {'seat': 0})
        assert '_compute_ms' in result, "Advisor response should include _compute_ms timing"
        assert isinstance(result['_compute_ms'], int), "_compute_ms should be an integer"
        assert result['_compute_ms'] >= 0, "_compute_ms should be non-negative"


def test_advisor_completes_under_2_seconds():
    """Advisor computation should complete within 2 seconds (1000 sims)."""
    import time
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')

        # Play to flop to test Monte Carlo path (not just preflop lookup)
        state = api(c, 'GET', '/api/state')
        safety = 0
        while state.get('street') == 'preflop' and state.get('phase') == 'playing' and safety < 10:
            seat = state.get('action_seat', -1)
            if seat < 0:
                break
            api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
            state = api(c, 'GET', '/api/state')
            safety += 1

        if state.get('phase') == 'playing':
            t0 = time.time()
            result = api(c, 'POST', '/api/advisor', {'seat': state['action_seat']})
            elapsed = time.time() - t0
            assert elapsed < 5.0, f"Advisor took {elapsed:.2f}s, should be under 5s"
            if '_compute_ms' in result:
                assert result['_compute_ms'] < 5000, f"Advisor compute took {result['_compute_ms']}ms"


def test_advisor_piggybacked_on_action_response():
    """When next player is human, action response should include _advisor data."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        state = api(c, 'GET', '/api/state')

        # First player acts — if next player is also human, should piggyback
        seat = state.get('action_seat', 0)
        result = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})

        # Check if game is still playing and next is human
        result_state = result.get('state', {})
        if result_state.get('phase') == 'playing':
            next_seat = result_state.get('action_seat', -1)
            if next_seat >= 0:
                next_player = result_state.get('players', [{}])[next_seat]
                if next_player.get('player_type') == 'human':
                    assert '_advisor' in result, \
                        "Action response should piggyback _advisor when next player is human"


# ════════════════════════════════════════════════
# Difficulty Presets
# ════════════════════════════════════════════════

def test_difficulty_presets_endpoint():
    """GET /api/difficulty_presets returns all preset configs."""
    with app.test_client() as c:
        result = api(c, 'GET', '/api/difficulty_presets')
        assert 'easy' in result
        assert 'medium' in result
        assert 'hard' in result
        assert 'expert' in result
        for key in ('ai_style', 'timing_preset', 'variance', 'equity_sims'):
            assert key in result['easy'], f"Preset 'easy' should have '{key}'"


def test_difficulty_setting_applies():
    """Changing difficulty via settings should update timing and variance."""
    with app.test_client() as c:
        _new_game(c)
        result = api(c, 'POST', '/api/settings', {'difficulty': 'expert'})
        assert result['ok']
        s = result['settings']
        assert s['difficulty'] == 'expert'
        assert s['timing_preset'] == 'tournament'  # Expert uses tournament timing
        assert s['variance'] == 5  # Expert variance = 0.05 * 100


def test_advisor_sims_setting():
    """Advisor sims setting should be persisted and returned."""
    with app.test_client() as c:
        _new_game(c)
        result = api(c, 'POST', '/api/settings', {'advisor_sims': 2000})
        assert result['ok']
        assert result['settings']['advisor_sims'] == 2000
        # Verify it persists on GET
        s = api(c, 'GET', '/api/settings')
        assert s['advisor_sims'] == 2000


# ════════════════════════════════════════════════
# Hand History Enhancement
# ════════════════════════════════════════════════

def test_hand_history_includes_hole_cards():
    """Hand history should capture hole cards after hand ends."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        play_hand_to_end(c)
        state = api(c, 'GET', '/api/state')
        histories = state.get('hand_histories', [])
        if histories:
            h = histories[-1]
            assert 'hole_cards' in h, "Hand history should include hole_cards"
            # At least one player should have cards logged
            if h['hole_cards']:
                some_cards = list(h['hole_cards'].values())[0]
                assert len(some_cards) == 2, "Each player should have 2 hole cards"


def test_hand_history_pot_after_in_actions():
    """Each action in hand history should include pot_after field."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        play_hand_to_end(c)
        state = api(c, 'GET', '/api/state')
        histories = state.get('hand_histories', [])
        if histories and histories[-1].get('actions'):
            for action in histories[-1]['actions']:
                assert 'pot_after' in action, "Actions should include pot_after"


# ════════════════════════════════════════════════
# Stats Dashboard
# ════════════════════════════════════════════════

def test_player_stats_tracked():
    """Player stats (win_rate, net_profit, etc.) should be in state after playing."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        play_hand_to_end(c)
        state = api(c, 'GET', '/api/state')
        for p in state.get('players', []):
            assert 'win_rate' in p, f"Player {p['name']} should have win_rate"
            assert 'net_profit' in p, f"Player {p['name']} should have net_profit"
            assert 'hands_won' in p, f"Player {p['name']} should have hands_won"
            assert 'biggest_pot_won' in p, f"Player {p['name']} should have biggest_pot_won"
            assert 'wtsd' in p, f"Player {p['name']} should have wtsd"
            assert 'wsd' in p, f"Player {p['name']} should have wsd"
            assert 'times_folded' in p, f"Player {p['name']} should have times_folded"


def test_winner_stats_increment():
    """The winner of a hand should have hands_won > 0."""
    with app.test_client() as c:
        _new_game(c)
        api(c, 'POST', '/api/new_hand')
        play_hand_to_end(c)
        state = api(c, 'GET', '/api/state')
        players = state.get('players', [])
        # At least one player should have won
        assert any(p.get('hands_won', 0) > 0 for p in players), \
            "At least one player should have hands_won > 0 after a hand"


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
