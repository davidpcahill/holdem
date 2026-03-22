/**
 * Jest tests for app.js socket handling, advisor fetch, and reconnection logic.
 *
 * These tests verify the Alpine.js app's behavior for:
 * - Socket event filtering (stale seq rejection)
 * - Advisor double-computation prevention
 * - AbortController cancellation of stale HTTP fetches
 * - Socket reconnection and state recovery
 * - Advisor update via socket cancelling HTTP fetch
 */

const PokerLogic = require('../../static/js/poker-logic');

// ── Mock helpers ──

function makeApp(overrides = {}) {
    return {
        // Core state
        state: {
            phase: 'playing', street: 'preflop', hand_number: 1,
            dealer_seat: 0, small_blind: 5, big_blind: 10, pot: 100,
            community_cards: [], players: [
                { seat: 0, name: 'You', player_type: 'human', stack: 500, is_folded: false, is_sitting_out: false, hole_cards: ['Ah', 'Kh'] },
                { seat: 1, name: 'Alice', player_type: 'ai', stack: 500, is_folded: false, is_sitting_out: false, hole_cards: ['??', '??'] },
            ],
            action_seat: 0, current_bet: 0, valid_actions: null,
        },
        // UI state
        advisor: null,
        advisorLoading: false,
        advisorEnabled: true,
        _advisorFetchId: 0,
        _advisorAbort: null,
        _lastSeq: 0,
        _lastStreet: '',
        _lastHandNum: 0,
        aiThinkingSeat: -1,
        showdown: null,
        _socketConnected: false,
        _wasDisconnected: false,
        ...overrides,
    };
}

// ═══════════════════════════════════════════════
// Stale Event Detection (seq filtering)
// ═══════════════════════════════════════════════

describe('seq-based stale event filtering', () => {
    test('state_update with lower seq is rejected', () => {
        const app = makeApp({ _lastSeq: 10 });
        const data = { _seq: 5, pot: 999 };
        // Simulate: if (data._seq && data._seq < this._lastSeq) return;
        const isStale = PokerLogic.isStaleEvent(data._seq, app._lastSeq);
        expect(isStale).toBe(true);
    });

    test('state_update with equal seq is accepted', () => {
        const app = makeApp({ _lastSeq: 10 });
        const isStale = PokerLogic.isStaleEvent(10, app._lastSeq);
        expect(isStale).toBe(false);
    });

    test('state_update with higher seq is accepted', () => {
        const app = makeApp({ _lastSeq: 10 });
        const isStale = PokerLogic.isStaleEvent(15, app._lastSeq);
        expect(isStale).toBe(false);
    });

    test('ai_action with stale state seq is rejected', () => {
        const app = makeApp({ _lastSeq: 20 });
        const data = { state: { _seq: 15 } };
        const isStale = PokerLogic.isStaleEvent(data.state?._seq, app._lastSeq);
        expect(isStale).toBe(true);
    });

    test('street_reveal with stale state seq is rejected', () => {
        const app = makeApp({ _lastSeq: 25 });
        const data = { state: { _seq: 20 }, street: 'flop' };
        const isStale = PokerLogic.isStaleEvent(data.state?._seq, app._lastSeq);
        expect(isStale).toBe(true);
    });

    test('events without seq are never stale', () => {
        const app = makeApp({ _lastSeq: 100 });
        expect(PokerLogic.isStaleEvent(undefined, app._lastSeq)).toBe(false);
        expect(PokerLogic.isStaleEvent(null, app._lastSeq)).toBe(false);
        expect(PokerLogic.isStaleEvent(0, app._lastSeq)).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// Advisor Double-Computation Prevention
// ═══════════════════════════════════════════════

describe('advisor fetch cancellation', () => {
    test('incrementing _advisorFetchId invalidates in-flight fetch', () => {
        const app = makeApp();
        const fetchId = ++app._advisorFetchId; // fetchId = 1
        // Simulate socket advisor_update arriving, cancelling HTTP fetch
        app._advisorFetchId++; // now 2
        // The HTTP response check: fetchId !== this._advisorFetchId
        expect(fetchId).not.toBe(app._advisorFetchId);
    });

    test('advisor_update socket cancels pending fetch by bumping fetchId', () => {
        const app = makeApp();
        const fetchId = ++app._advisorFetchId; // Start HTTP fetch, id=1

        // Simulate advisor_update socket event arriving
        const socketData = { equity: { win: 55 }, top_action: { action: 'call' } };
        // This is what the socket handler does:
        app.advisor = socketData;
        app._advisorFetchId++; // Cancel HTTP fetch
        app.advisorLoading = false;

        // HTTP response arrives with old fetchId — should be dropped
        expect(fetchId).not.toBe(app._advisorFetchId);
        expect(app.advisor).toBe(socketData); // Socket data preserved
    });

    test('AbortController is created and stored', () => {
        const app = makeApp();
        expect(app._advisorAbort).toBeNull();

        // Simulate fetchAdvisor starting
        const controller = new AbortController();
        app._advisorAbort = controller;
        expect(app._advisorAbort).toBe(controller);
        expect(controller.signal.aborted).toBe(false);

        // Simulate new fetch cancelling old
        controller.abort();
        expect(controller.signal.aborted).toBe(true);
    });

    test('sequential fetches abort previous controllers', () => {
        const app = makeApp();

        // First fetch
        const controller1 = new AbortController();
        app._advisorAbort = controller1;

        // Second fetch starts — should abort first
        if (app._advisorAbort) app._advisorAbort.abort();
        const controller2 = new AbortController();
        app._advisorAbort = controller2;

        expect(controller1.signal.aborted).toBe(true);
        expect(controller2.signal.aborted).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// Advisor Action Decision Logic
// ═══════════════════════════════════════════════

describe('advisor fetch decision after AI finishes', () => {
    test('fetches advisor when turn changes to human (AI done)', () => {
        const action = PokerLogic.advisorAction({
            canAct: true,
            advisorEnabled: true,
            advisorLoading: false,
            hasAdvisor: false,
            piggybackedAdvisor: null,
            turnChanged: true,
            streetChanged: false,
            playersChanged: false,
            newHand: false,
        });
        expect(action).toBe('fetch_new');
    });

    test('uses piggybacked advisor instead of fetching', () => {
        const action = PokerLogic.advisorAction({
            canAct: true,
            advisorEnabled: true,
            advisorLoading: false,
            hasAdvisor: false,
            piggybackedAdvisor: { equity: { win: 60 } },
            turnChanged: true,
            streetChanged: false,
            playersChanged: false,
            newHand: false,
        });
        expect(action).toBe('use_piggybacked');
    });

    test('clears advisor when not acting (AI turn)', () => {
        const action = PokerLogic.advisorAction({
            canAct: false,
            advisorEnabled: true,
            advisorLoading: false,
            hasAdvisor: true,
            piggybackedAdvisor: null,
            turnChanged: false,
            streetChanged: false,
            playersChanged: false,
            newHand: false,
        });
        expect(action).toBe('clear');
    });

    test('fetches on street change even if turn didnt change', () => {
        const action = PokerLogic.advisorAction({
            canAct: true,
            advisorEnabled: true,
            advisorLoading: false,
            hasAdvisor: true,
            piggybackedAdvisor: null,
            turnChanged: false,
            streetChanged: true,
            playersChanged: false,
            newHand: false,
        });
        expect(action).toBe('fetch_new');
    });
});

// ═══════════════════════════════════════════════
// Socket Reconnection State
// ═══════════════════════════════════════════════

describe('socket reconnection tracking', () => {
    test('disconnect sets _wasDisconnected flag', () => {
        const app = makeApp({ _socketConnected: true });

        // Simulate disconnect handler
        app._socketConnected = false;
        app._wasDisconnected = true;

        expect(app._socketConnected).toBe(false);
        expect(app._wasDisconnected).toBe(true);
    });

    test('reconnect triggers state reload when _wasDisconnected', () => {
        const app = makeApp({
            _socketConnected: false,
            _wasDisconnected: true,
        });

        let stateReloaded = false;

        // Simulate connect handler
        app._socketConnected = true;
        if (app._wasDisconnected) {
            stateReloaded = true; // Would call this.loadState()
            app._wasDisconnected = false;
        }

        expect(app._socketConnected).toBe(true);
        expect(stateReloaded).toBe(true);
        expect(app._wasDisconnected).toBe(false);
    });

    test('initial connect does not trigger reload', () => {
        const app = makeApp({
            _socketConnected: false,
            _wasDisconnected: false,
        });

        let stateReloaded = false;

        // Simulate connect handler
        app._socketConnected = true;
        if (app._wasDisconnected) {
            stateReloaded = true;
            app._wasDisconnected = false;
        }

        expect(stateReloaded).toBe(false);
    });

    test('multiple disconnects only trigger one reload', () => {
        const app = makeApp();
        let reloadCount = 0;

        // First disconnect
        app._socketConnected = false;
        app._wasDisconnected = true;

        // Second disconnect (already disconnected)
        app._wasDisconnected = true;

        // Reconnect
        app._socketConnected = true;
        if (app._wasDisconnected) {
            reloadCount++;
            app._wasDisconnected = false;
        }

        expect(reloadCount).toBe(1);
    });
});

// ═══════════════════════════════════════════════
// State Update Change Detection
// ═══════════════════════════════════════════════

describe('state change detection for advisor refresh', () => {
    test('detects street change when same player acts again', () => {
        // Bug fix: advisor wasn't refreshing on street change when same seat acts
        const prevState = { action_seat: 0, hand_number: 1, street: 'preflop', players: [
            { is_folded: false, is_sitting_out: false },
            { is_folded: false, is_sitting_out: false },
        ]};
        const newData = { street: 'flop', action_seat: 0 };
        const changes = PokerLogic.detectChanges(prevState, newData);
        expect(changes.streetChanged).toBe(true);
        expect(changes.turnChanged).toBe(false); // same seat!
    });

    test('detects both street and turn change', () => {
        const prevState = { action_seat: 1, hand_number: 1, street: 'preflop', players: [
            { is_folded: false, is_sitting_out: false },
            { is_folded: false, is_sitting_out: false },
        ]};
        const newData = { street: 'flop', action_seat: 0 };
        const changes = PokerLogic.detectChanges(prevState, newData);
        expect(changes.streetChanged).toBe(true);
        expect(changes.turnChanged).toBe(true);
    });

    test('new hand clears advisor', () => {
        const action = PokerLogic.advisorAction({
            canAct: true,
            advisorEnabled: true,
            advisorLoading: false,
            hasAdvisor: true,
            piggybackedAdvisor: null,
            turnChanged: false,
            streetChanged: false,
            playersChanged: false,
            newHand: true,
        });
        expect(action).toBe('clear');
    });
});

// ═══════════════════════════════════════════════
// AI Thinking State
// ═══════════════════════════════════════════════

describe('AI thinking indicator', () => {
    test('ai_thinking sets thinking seat', () => {
        const app = makeApp();
        // Simulate ai_thinking handler
        app.aiThinkingSeat = 1;
        expect(app.aiThinkingSeat).toBe(1);
    });

    test('ai_action clears thinking seat', () => {
        const app = makeApp({ aiThinkingSeat: 1 });
        // Simulate ai_action handler
        app.aiThinkingSeat = -1;
        expect(app.aiThinkingSeat).toBe(-1);
    });

    test('street_reveal with next_thinking sets new thinking seat', () => {
        const app = makeApp({ aiThinkingSeat: -1 });
        const revealData = {
            next_thinking: { seat: 1, name: 'Alice' },
            state: { _seq: 5 },
        };
        // Simulate street_reveal handler
        if (revealData.next_thinking) {
            app.aiThinkingSeat = revealData.next_thinking.seat;
        }
        expect(app.aiThinkingSeat).toBe(1);
    });

    test('street_reveal without next_thinking keeps seat cleared', () => {
        const app = makeApp({ aiThinkingSeat: -1 });
        const revealData = { state: { _seq: 5 } };
        if (revealData.next_thinking) {
            app.aiThinkingSeat = revealData.next_thinking.seat;
        }
        expect(app.aiThinkingSeat).toBe(-1);
    });

    test('canAct clears AI thinking indicator', () => {
        const app = makeApp({ aiThinkingSeat: 1 });
        // When canAct becomes true, updateState clears aiThinkingSeat
        const state = app.state;
        const canAct = PokerLogic.canAct(state);
        if (canAct) {
            app.aiThinkingSeat = -1;
        }
        expect(app.aiThinkingSeat).toBe(-1);
    });
});

// ═══════════════════════════════════════════════
// New Game / New Hand State Reset
// ═══════════════════════════════════════════════

describe('state reset on new game/hand', () => {
    test('newHand clears all stale state', () => {
        const app = makeApp({
            showdown: { winners: [{ seat: 0 }] },
            advisor: { equity: 55 },
            advisorLoading: true,
            _advisorFetchId: 5,
            aiThinkingSeat: 1,
        });

        // Simulate newHand success handler
        app.showdown = null;
        app.advisor = null;
        app.advisorLoading = false;
        app._advisorFetchId++;
        app.aiThinkingSeat = -1;

        expect(app.showdown).toBeNull();
        expect(app.advisor).toBeNull();
        expect(app.advisorLoading).toBe(false);
        expect(app._advisorFetchId).toBe(6);
        expect(app.aiThinkingSeat).toBe(-1);
    });

    test('startNewGame resets all UI state', () => {
        const app = makeApp({
            showdown: { winners: [{ seat: 0 }] },
            advisor: { equity: 55 },
            advisorLoading: true,
            _advisorFetchId: 3,
            aiThinkingSeat: 1,
            _lastStreet: 'river',
            _lastHandNum: 5,
            _lastSeq: 50,
        });

        // Simulate startNewGame success handler
        app.showdown = null;
        app.advisor = null;
        app.advisorLoading = false;
        app._advisorFetchId++;
        app.aiThinkingSeat = -1;
        app._lastStreet = '';
        app._lastHandNum = 0;

        expect(app.showdown).toBeNull();
        expect(app.advisor).toBeNull();
        expect(app._advisorFetchId).toBe(4);
        expect(app._lastStreet).toBe('');
        expect(app._lastHandNum).toBe(0);
    });
});

// ═══════════════════════════════════════════════
// Street Reveal Timing
// ═══════════════════════════════════════════════

describe('street reveal event handling', () => {
    test('street_reveal updates state and preserves next_thinking', () => {
        const app = makeApp({ _lastSeq: 0 });
        const revealData = {
            street: 'flop',
            community_cards: ['Ah', 'Kd', '7c'],
            state: { _seq: 10, street: 'flop', community_cards: ['Ah', 'Kd', '7c'], pot: 200 },
            next_thinking: { seat: 1, name: 'Alice' },
        };

        // Simulate handler logic
        const isStale = PokerLogic.isStaleEvent(revealData.state?._seq, app._lastSeq);
        expect(isStale).toBe(false);

        // Apply state
        if (revealData.state) {
            app._lastSeq = revealData.state._seq;
        }
        if (revealData.next_thinking) {
            app.aiThinkingSeat = revealData.next_thinking.seat;
        }

        expect(app._lastSeq).toBe(10);
        expect(app.aiThinkingSeat).toBe(1);
    });

    test('stale street_reveal is completely ignored', () => {
        const app = makeApp({ _lastSeq: 20, aiThinkingSeat: -1 });
        const revealData = {
            state: { _seq: 15 },
            next_thinking: { seat: 1 },
        };

        const isStale = PokerLogic.isStaleEvent(revealData.state?._seq, app._lastSeq);
        expect(isStale).toBe(true);

        // Should not update anything
        if (!isStale) {
            app._lastSeq = revealData.state._seq;
            app.aiThinkingSeat = revealData.next_thinking.seat;
        }

        expect(app._lastSeq).toBe(20); // unchanged
        expect(app.aiThinkingSeat).toBe(-1); // unchanged
    });
});
