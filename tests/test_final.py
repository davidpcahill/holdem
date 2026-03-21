"""Final integration test covering all new features."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

def api(c, method, path, json=None):
    if method == 'GET':
        return c.get(path).get_json()
    return c.post(path, json=json or {}).get_json()

with app.test_client() as c:
    # === 1. Full showdown with hand_results ===
    api(c, 'POST', '/api/new_game', {
        'small_blind': 5, 'big_blind': 10,
        'players': [
            {'name': 'Alice', 'stack': 500, 'player_type': 'human'},
            {'name': 'Bob', 'stack': 500, 'player_type': 'human'},
        ]
    })
    api(c, 'POST', '/api/new_hand')
    
    state = api(c, 'GET', '/api/state')
    result = None
    for _ in range(20):
        if state.get('phase') != 'playing':
            break
        seat = state['action_seat']
        va = state.get('valid_actions', {}).get('actions', [])
        if any(a['action'] == 'check' for a in va):
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'check'})
        else:
            d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'call'})
        state = d.get('state', state)
        if d.get('showdown'):
            result = d
            break
    
    assert result and result.get('showdown'), 'No showdown reached'
    assert 'hand_results' in result
    hr = result['hand_results']
    assert len(hr) >= 2
    for seat_str, h in hr.items():
        assert 'rank_name' in h
        assert 'cards' in h
    print(f"Showdown hand_results: {len(hr)} players")
    for seat_str, h in hr.items():
        print(f"  Seat {seat_str}: {h['rank_name']} ({h['name']})")
    for w in result['winners']:
        assert w['amount'] > 0
        print(f"  Winner: {w['name']} +${w['amount']}")

    # === 2. Cards revealed at hand_over ===
    state = api(c, 'GET', '/api/state')
    assert state['street'] == 'hand_over'
    revealed = [p for p in state['players'] if p.get('hole_cards')]
    assert len(revealed) >= 2, f'Only {len(revealed)} players revealed'
    print(f"Cards revealed at hand_over: {len(revealed)} players - OK")
    
    # === 3. Busted player ===
    api(c, 'POST', '/api/new_game', {
        'small_blind': 5, 'big_blind': 10,
        'players': [
            {'name': 'Rich', 'stack': 1000, 'player_type': 'human'},
            {'name': 'Broke', 'stack': 0, 'player_type': 'human'},
            {'name': 'Mid', 'stack': 500, 'player_type': 'human'},
        ]
    })
    api(c, 'POST', '/api/new_hand')
    state = api(c, 'GET', '/api/state')
    assert state['players'][1]['is_folded'] == True
    print("Busted player auto-folded: OK")
    
    # Quick fold to end hand
    for _ in range(10):
        if state.get('phase') != 'playing': break
        seat = state['action_seat']
        d = api(c, 'POST', '/api/action', {'seat': seat, 'action': 'fold'})
        state = d.get('state', state)
    
    # === 4. Export includes blind actions ===
    text = c.get('/api/export_history').data.decode()
    assert 'small_blind' in text
    assert 'Hand #' in text
    print("Export with blind actions: OK")
    
    # === 5. HTML + JS completeness ===
    html = c.get('/').data.decode()
    html_features = [
        'hand_results', 'rank_name', 'auto_advance', 'auto_advance_delay',
        'copyHistory', 'downloadHistory', 'sounds.js',
        'editingPlayer', 'openPlayerEditor', 'passPlayActive',
        'hideHands', 'shouldShowCards', 'sidebar-open',
    ]
    missing = [f for f in html_features if f not in html]
    assert not missing, f'Missing from HTML: {missing}'
    
    # Check JS has auto-advance methods
    js = c.get('/static/js/app.js').data.decode()
    js_features = ['startAutoAdvance', 'cancelAutoAdvance', 'autoAdvanceTimer']
    missing_js = [f for f in js_features if f not in js]
    assert not missing_js, f'Missing from JS: {missing_js}'
    
    print(f"HTML: {len(html_features)} features present")
    print(f"JS: {len(js_features)} features present")
    
    print()
    print("=== ALL FINAL TESTS PASSED ===")
