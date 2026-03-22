/**
 * Jest tests for poker-logic.js — pure logic extracted from app.js
 *
 * Covers: computed properties, display helpers, state management,
 * card visibility, setup validation, and advisor refresh logic.
 */

const PokerLogic = require('../../static/js/poker-logic');

// ── Helper Factories ──

function makeState(overrides = {}) {
    return {
        phase: 'playing',
        street: 'preflop',
        hand_number: 1,
        dealer_seat: 0,
        small_blind: 5,
        big_blind: 10,
        pot: 0,
        community_cards: [],
        players: [
            { seat: 0, name: 'You', player_type: 'human', stack: 500, is_folded: false, is_sitting_out: false, hole_cards: ['Ah', 'Kh'] },
            { seat: 1, name: 'Alice', player_type: 'ai', stack: 500, is_folded: false, is_sitting_out: false, hole_cards: ['??', '??'] },
        ],
        action_seat: 0,
        current_bet: 0,
        valid_actions: null,
        ...overrides,
    };
}

function makeValidActions(overrides = {}) {
    return {
        to_call: 0,
        player_stack: 500,
        actions: [
            { action: 'fold' },
            { action: 'check' },
            { action: 'bet', min: 10, max: 500 },
        ],
        ...overrides,
    };
}

// ═══════════════════════════════════════════════
// Street Display
// ═══════════════════════════════════════════════

describe('streetDisplay', () => {
    test('maps known streets to display names', () => {
        expect(PokerLogic.streetDisplay('preflop')).toBe('Pre-Flop');
        expect(PokerLogic.streetDisplay('flop')).toBe('Flop');
        expect(PokerLogic.streetDisplay('turn')).toBe('Turn');
        expect(PokerLogic.streetDisplay('river')).toBe('River');
        expect(PokerLogic.streetDisplay('showdown')).toBe('Showdown');
        expect(PokerLogic.streetDisplay('hand_over')).toBe('Hand Over');
    });

    test('returns raw value for unknown streets', () => {
        expect(PokerLogic.streetDisplay('unknown')).toBe('unknown');
    });
});

// ═══════════════════════════════════════════════
// canAct
// ═══════════════════════════════════════════════

describe('canAct', () => {
    test('true when playing and human is acting', () => {
        expect(PokerLogic.canAct(makeState())).toBe(true);
    });

    test('false when phase is not playing', () => {
        expect(PokerLogic.canAct(makeState({ phase: 'setup' }))).toBe(false);
    });

    test('false when action_seat is negative', () => {
        expect(PokerLogic.canAct(makeState({ action_seat: -1 }))).toBe(false);
    });

    test('false when action_seat is AI player', () => {
        expect(PokerLogic.canAct(makeState({ action_seat: 1 }))).toBe(false);
    });

    test('false when no players array', () => {
        expect(PokerLogic.canAct(makeState({ players: null }))).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// Call / Check / Raise Labels
// ═══════════════════════════════════════════════

describe('toCallAmount', () => {
    test('returns 0 when no to_call', () => {
        expect(PokerLogic.toCallAmount(makeValidActions())).toBe(0);
    });

    test('returns to_call when stack is sufficient', () => {
        expect(PokerLogic.toCallAmount(makeValidActions({ to_call: 100 }))).toBe(100);
    });

    test('caps at player stack when to_call exceeds stack', () => {
        expect(PokerLogic.toCallAmount(makeValidActions({ to_call: 1000, player_stack: 200 }))).toBe(200);
    });

    test('returns to_call when player_stack is undefined (Infinity fallback)', () => {
        const va = { to_call: 50, actions: [] };
        expect(PokerLogic.toCallAmount(va)).toBe(50);
    });
});

describe('checkCallLabel', () => {
    test('returns Check when nothing to call', () => {
        expect(PokerLogic.checkCallLabel(makeValidActions())).toBe('Check');
    });

    test('returns Call with amount', () => {
        expect(PokerLogic.checkCallLabel(makeValidActions({ to_call: 50 }))).toBe('Call $50');
    });

    test('returns All-In when call is all-in', () => {
        const va = makeValidActions({
            to_call: 500,
            actions: [{ action: 'fold' }, { action: 'call', is_all_in: true }],
        });
        expect(PokerLogic.checkCallLabel(va)).toBe('All-In $500');
    });
});

describe('canRaise', () => {
    test('true when human can act and bet action available', () => {
        const state = makeState({ valid_actions: makeValidActions() });
        expect(PokerLogic.canRaise(state)).toBe(true);
    });

    test('false when not human turn', () => {
        const state = makeState({ action_seat: 1, valid_actions: makeValidActions() });
        expect(PokerLogic.canRaise(state)).toBe(false);
    });

    test('false when no bet/raise in valid actions', () => {
        const va = makeValidActions({ actions: [{ action: 'fold' }, { action: 'check' }] });
        const state = makeState({ valid_actions: va });
        expect(PokerLogic.canRaise(state)).toBe(false);
    });
});

describe('raiseLabel', () => {
    test('returns Bet label for bet action', () => {
        const va = makeValidActions();
        expect(PokerLogic.raiseLabel(va, 50, 500)).toBe('Bet $50');
    });

    test('returns Raise to label for raise action', () => {
        const va = makeValidActions({ actions: [{ action: 'fold' }, { action: 'raise', min: 20, max: 500 }] });
        expect(PokerLogic.raiseLabel(va, 100, 500)).toBe('Raise to $100');
    });

    test('returns All-In when bet equals max', () => {
        const va = makeValidActions();
        expect(PokerLogic.raiseLabel(va, 500, 500)).toBe('All-In $500');
    });

    test('returns Raise when no valid actions', () => {
        expect(PokerLogic.raiseLabel(null, 50, 500)).toBe('Raise');
    });
});

// ═══════════════════════════════════════════════
// Raise Min / Max
// ═══════════════════════════════════════════════

describe('raiseMin / raiseMax', () => {
    test('raiseMin returns bet min from valid actions', () => {
        expect(PokerLogic.raiseMin(makeValidActions(), 10)).toBe(10);
    });

    test('raiseMin falls back to big blind', () => {
        const va = makeValidActions({ actions: [{ action: 'fold' }] });
        expect(PokerLogic.raiseMin(va, 25)).toBe(25);
    });

    test('raiseMax returns bet max from valid actions', () => {
        const va = makeValidActions();
        const state = makeState();
        expect(PokerLogic.raiseMax(va, state)).toBe(500);
    });

    test('raiseMax falls back to player stack', () => {
        const va = makeValidActions({ actions: [{ action: 'fold' }] });
        const state = makeState();
        expect(PokerLogic.raiseMax(va, state)).toBe(500);
    });
});

// ═══════════════════════════════════════════════
// Slider Step & Snap Bet
// ═══════════════════════════════════════════════

describe('sliderStep', () => {
    test('step 1 for tiny ranges', () => {
        expect(PokerLogic.sliderStep(10, 50)).toBe(1);
    });

    test('step 5 for small ranges', () => {
        expect(PokerLogic.sliderStep(10, 300)).toBe(5);
    });

    test('step 10 for medium ranges', () => {
        expect(PokerLogic.sliderStep(10, 1500)).toBe(10);
    });

    test('step 25 for larger ranges', () => {
        expect(PokerLogic.sliderStep(10, 4000)).toBe(25);
    });

    test('step 50 for large ranges', () => {
        expect(PokerLogic.sliderStep(100, 15000)).toBe(50);
    });

    test('step 100 for very large ranges', () => {
        expect(PokerLogic.sliderStep(100, 50000)).toBe(100);
    });

    test('step 250 for huge ranges', () => {
        expect(PokerLogic.sliderStep(100, 200000)).toBe(250);
    });
});

describe('snapBet', () => {
    test('snaps to min when below', () => {
        expect(PokerLogic.snapBet(5, 10, 500, 10)).toBe(10);
    });

    test('snaps to max when above', () => {
        expect(PokerLogic.snapBet(600, 10, 500, 10)).toBe(500);
    });

    test('rounds to nearest step', () => {
        expect(PokerLogic.snapBet(47, 10, 500, 10)).toBe(50);
        expect(PokerLogic.snapBet(43, 10, 500, 10)).toBe(40);
    });

    test('exact step values pass through', () => {
        expect(PokerLogic.snapBet(100, 10, 500, 10)).toBe(100);
    });
});

describe('setBetPreset', () => {
    test('half pot preset', () => {
        const result = PokerLogic.setBetPreset(200, 0.5, 10, 500, 10);
        expect(result).toBe(100);
    });

    test('full pot preset', () => {
        const result = PokerLogic.setBetPreset(200, 1.0, 10, 500, 10);
        expect(result).toBe(200);
    });

    test('clamps to min', () => {
        const result = PokerLogic.setBetPreset(10, 0.5, 50, 500, 10);
        expect(result).toBe(50);
    });

    test('clamps to max', () => {
        const result = PokerLogic.setBetPreset(1000, 2.0, 10, 500, 10);
        expect(result).toBe(500);
    });
});

// ═══════════════════════════════════════════════
// Display Helpers
// ═══════════════════════════════════════════════

describe('getLastAction', () => {
    const log = [
        { seat: 0, action: 'call' },
        { seat: 1, action: 'raise' },
        { seat: 0, action: 'check' },
    ];

    test('returns last action for seat', () => {
        expect(PokerLogic.getLastAction(log, 0)).toBe('check');
        expect(PokerLogic.getLastAction(log, 1)).toBe('raise');
    });

    test('returns empty string for unknown seat', () => {
        expect(PokerLogic.getLastAction(log, 5)).toBe('');
    });

    test('returns empty string for empty log', () => {
        expect(PokerLogic.getLastAction([], 0)).toBe('');
    });
});

describe('getLastActionDisplay', () => {
    test('maps known actions to display', () => {
        const log = [{ seat: 0, action: 'small_blind' }];
        expect(PokerLogic.getLastActionDisplay(log, 0)).toBe('SB');
    });

    test('uppercases unknown actions', () => {
        const log = [{ seat: 0, action: 'allin' }];
        expect(PokerLogic.getLastActionDisplay(log, 0)).toBe('ALLIN');
    });
});

describe('formatAction', () => {
    test('maps known actions', () => {
        expect(PokerLogic.formatAction({ action: 'fold' })).toBe('folds');
        expect(PokerLogic.formatAction({ action: 'raise' })).toBe('raises to');
        expect(PokerLogic.formatAction({ action: 'big_blind' })).toBe('posts big blind');
    });

    test('returns raw for unknown', () => {
        expect(PokerLogic.formatAction({ action: 'mystery' })).toBe('mystery');
    });
});

describe('formatAIStyle', () => {
    test('maps known styles', () => {
        expect(PokerLogic.formatAIStyle('tight_aggressive')).toBe('Tight-Aggressive');
        expect(PokerLogic.formatAIStyle('gto')).toBe('GTO');
    });

    test('returns raw for unknown', () => {
        expect(PokerLogic.formatAIStyle('chaotic')).toBe('chaotic');
    });
});

describe('positionTooltip / betTypeTooltip / aiStyleTooltip', () => {
    test('returns tooltip for known positions', () => {
        expect(PokerLogic.positionTooltip('BTN')).toContain('Button');
        expect(PokerLogic.positionTooltip('UTG')).toContain('Under The Gun');
    });

    test('returns raw for unknown position', () => {
        expect(PokerLogic.positionTooltip('XYZ')).toBe('XYZ');
    });

    test('returns tooltip for bet types', () => {
        expect(PokerLogic.betTypeTooltip('value')).toContain('Value Bet');
        expect(PokerLogic.betTypeTooltip('bluff')).toContain('Bluff');
    });

    test('returns tooltip for AI styles', () => {
        expect(PokerLogic.aiStyleTooltip('gto')).toContain('GTO');
    });
});

// ═══════════════════════════════════════════════
// Winner Detection
// ═══════════════════════════════════════════════

describe('isWinner / isWinnerCard', () => {
    const showdown = {
        winners: [{ seat: 0, amount: 100 }],
        hand_results: {
            0: { cards: [{ short: 'Ah' }, { short: 'Kh' }, { short: 'Qh' }, { short: 'Jh' }, { short: 'Th' }] },
        },
    };

    test('isWinner returns true for winning seat', () => {
        expect(PokerLogic.isWinner(showdown, 0)).toBe(true);
    });

    test('isWinner returns false for non-winning seat', () => {
        expect(PokerLogic.isWinner(showdown, 1)).toBe(false);
    });

    test('isWinner handles null showdown', () => {
        expect(PokerLogic.isWinner(null, 0)).toBe(false);
    });

    test('isWinnerCard returns true for card in winning hand', () => {
        expect(PokerLogic.isWinnerCard(showdown, 0, { short: 'Ah' })).toBe(true);
    });

    test('isWinnerCard returns false for card not in winning hand', () => {
        expect(PokerLogic.isWinnerCard(showdown, 0, { short: '2c' })).toBe(false);
    });

    test('isWinnerCard handles missing seat data', () => {
        expect(PokerLogic.isWinnerCard(showdown, 5, { short: 'Ah' })).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// Slider Recommend Style
// ═══════════════════════════════════════════════

describe('sliderRecommendStyle', () => {
    test('returns display:none when no advisor', () => {
        expect(PokerLogic.sliderRecommendStyle(null, 10, 500)).toBe('display:none');
    });

    test('returns display:none when no bet_range', () => {
        const advisor = { top_action: { action: 'call' } };
        expect(PokerLogic.sliderRecommendStyle(advisor, 10, 500)).toBe('display:none');
    });

    test('returns display:none when range is zero', () => {
        const advisor = { top_action: { bet_range: [100, 200] } };
        expect(PokerLogic.sliderRecommendStyle(advisor, 100, 100)).toBe('display:none');
    });

    test('calculates correct position for bet range', () => {
        const advisor = { top_action: { bet_range: [100, 300] } };
        const style = PokerLogic.sliderRecommendStyle(advisor, 0, 500);
        expect(style).toContain('left:20%');
        expect(style).toContain('width:40%');
    });
});

// ═══════════════════════════════════════════════
// Card Visibility (shouldShowCards)
// ═══════════════════════════════════════════════

describe('shouldShowCards', () => {
    const humanPlayer = { seat: 0, player_type: 'human', is_folded: false, is_sitting_out: false, stack: 500, hole_cards: ['Ah', 'Kh'] };
    const aiPlayer = { seat: 1, player_type: 'ai', is_folded: false, is_sitting_out: false, stack: 500, hole_cards: ['??', '??'] };
    const foldedPlayer = { ...humanPlayer, is_folded: true };

    test('always shows non-folded cards at showdown', () => {
        const state = makeState({ street: 'showdown' });
        expect(PokerLogic.shouldShowCards(humanPlayer, state, true, false)).toBe(true);
        expect(PokerLogic.shouldShowCards(aiPlayer, state, true, false)).toBe(true);
    });

    test('hides folded player at showdown', () => {
        const state = makeState({ street: 'showdown' });
        expect(PokerLogic.shouldShowCards(foldedPlayer, state, true, false)).toBe(false);
    });

    test('shows all cards when hideHands is off', () => {
        const state = makeState();
        expect(PokerLogic.shouldShowCards(humanPlayer, state, false, false)).toBe(true);
        expect(PokerLogic.shouldShowCards(aiPlayer, state, false, false)).toBe(true);
    });

    test('hides all during pass-play countdown', () => {
        const state = makeState();
        expect(PokerLogic.shouldShowCards(humanPlayer, state, true, true)).toBe(false);
    });

    test('single human: shows own cards, hides AI', () => {
        const state = makeState();
        expect(PokerLogic.shouldShowCards(humanPlayer, state, true, false)).toBe(true);
        expect(PokerLogic.shouldShowCards(aiPlayer, state, true, false)).toBe(false);
    });

    test('multiple humans: only shows acting player', () => {
        const human2 = { seat: 2, player_type: 'human', is_folded: false, is_sitting_out: false, stack: 500, hole_cards: ['Qs', 'Js'] };
        const state = makeState({
            action_seat: 0,
            players: [humanPlayer, aiPlayer, human2],
        });
        expect(PokerLogic.shouldShowCards(humanPlayer, state, true, false)).toBe(true);
        expect(PokerLogic.shouldShowCards(human2, state, true, false)).toBe(false);
    });

    test('all-AI game shows all cards', () => {
        const ai2 = { seat: 0, player_type: 'ai', is_folded: false, is_sitting_out: false, stack: 500, hole_cards: ['Td', 'Tc'] };
        const state = makeState({ players: [ai2, aiPlayer] });
        expect(PokerLogic.shouldShowCards(ai2, state, true, false)).toBe(true);
    });
});

// ═══════════════════════════════════════════════
// Setup Helpers
// ═══════════════════════════════════════════════

describe('setup helpers', () => {
    test('canAddPlayer allows up to 10', () => {
        expect(PokerLogic.canAddPlayer(new Array(9))).toBe(true);
        expect(PokerLogic.canAddPlayer(new Array(10))).toBe(false);
    });

    test('canRemovePlayer requires at least 2', () => {
        expect(PokerLogic.canRemovePlayer(new Array(3))).toBe(true);
        expect(PokerLogic.canRemovePlayer(new Array(2))).toBe(false);
    });

    test('makeNewPlayer creates correct defaults', () => {
        const p = PokerLogic.makeNewPlayer(3, 5000);
        expect(p.name).toBe('Player 4');
        expect(p.stack).toBe(5000);
        expect(p.player_type).toBe('ai');
        expect(p.ai_style).toBe('random');
    });

    test('makeNewPlayer defaults to 1000 stack', () => {
        const p = PokerLogic.makeNewPlayer(0, null);
        expect(p.stack).toBe(1000);
    });
});

// ═══════════════════════════════════════════════
// State Management — Stale Event Detection
// ═══════════════════════════════════════════════

describe('isStaleEvent', () => {
    test('stale when event seq < last seq', () => {
        expect(PokerLogic.isStaleEvent(5, 10)).toBe(true);
    });

    test('not stale when event seq >= last seq', () => {
        expect(PokerLogic.isStaleEvent(10, 10)).toBe(false);
        expect(PokerLogic.isStaleEvent(15, 10)).toBe(false);
    });

    test('not stale when event seq is falsy (no seq)', () => {
        expect(PokerLogic.isStaleEvent(0, 10)).toBe(false);
        expect(PokerLogic.isStaleEvent(null, 10)).toBe(false);
        expect(PokerLogic.isStaleEvent(undefined, 10)).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// State Management — Change Detection
// ═══════════════════════════════════════════════

describe('detectChanges', () => {
    test('detects turn change', () => {
        const prev = makeState({ action_seat: 0 });
        const data = { action_seat: 1 };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.turnChanged).toBe(true);
        expect(changes.newHand).toBe(false);
    });

    test('detects new hand', () => {
        const prev = makeState({ hand_number: 1 });
        const data = { hand_number: 2 };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.newHand).toBe(true);
    });

    test('detects street change', () => {
        const prev = makeState({ street: 'preflop' });
        const data = { street: 'flop' };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.streetChanged).toBe(true);
    });

    test('no street change when data has no street field', () => {
        const prev = makeState({ street: 'preflop' });
        const data = { action_seat: 0 };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.streetChanged).toBe(false);
    });

    test('detects player count change (fold)', () => {
        const prev = makeState({
            players: [
                { seat: 0, is_folded: false, is_sitting_out: false },
                { seat: 1, is_folded: false, is_sitting_out: false },
                { seat: 2, is_folded: false, is_sitting_out: false },
            ],
        });
        const data = {
            players: [
                { seat: 0, is_folded: false, is_sitting_out: false },
                { seat: 1, is_folded: true, is_sitting_out: false },
                { seat: 2, is_folded: false, is_sitting_out: false },
            ],
        };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.playersChanged).toBe(true);
    });

    test('no changes when nothing changed', () => {
        const prev = makeState();
        const data = { pot: 100 };
        const changes = PokerLogic.detectChanges(prev, data);
        expect(changes.turnChanged).toBe(false);
        expect(changes.newHand).toBe(false);
        expect(changes.streetChanged).toBe(false);
        expect(changes.playersChanged).toBe(false);
    });
});

// ═══════════════════════════════════════════════
// Advisor Action Logic
// ═══════════════════════════════════════════════

describe('advisorAction', () => {
    const base = {
        canAct: true,
        advisorEnabled: true,
        advisorLoading: false,
        hasAdvisor: false,
        piggybackedAdvisor: null,
        turnChanged: false,
        streetChanged: false,
        playersChanged: false,
        newHand: false,
    };

    test('clears when cannot act', () => {
        expect(PokerLogic.advisorAction({ ...base, canAct: false })).toBe('clear');
    });

    test('clears on new hand', () => {
        expect(PokerLogic.advisorAction({ ...base, newHand: true })).toBe('clear');
    });

    test('uses piggybacked data when available', () => {
        expect(PokerLogic.advisorAction({ ...base, piggybackedAdvisor: { equity: 0.6 } })).toBe('use_piggybacked');
    });

    test('fetches new on turn change', () => {
        expect(PokerLogic.advisorAction({ ...base, turnChanged: true })).toBe('fetch_new');
    });

    test('fetches new on street change', () => {
        expect(PokerLogic.advisorAction({ ...base, streetChanged: true })).toBe('fetch_new');
    });

    test('fetches new on players changed', () => {
        expect(PokerLogic.advisorAction({ ...base, playersChanged: true })).toBe('fetch_new');
    });

    test('clears on turn change when advisor disabled', () => {
        expect(PokerLogic.advisorAction({ ...base, turnChanged: true, advisorEnabled: false })).toBe('clear');
    });

    test('fetches as fallback when no advisor and not loading', () => {
        expect(PokerLogic.advisorAction({ ...base })).toBe('fetch_new');
    });

    test('keeps when advisor exists and nothing changed', () => {
        expect(PokerLogic.advisorAction({ ...base, hasAdvisor: true })).toBe('keep');
    });
});

// ═══════════════════════════════════════════════
// History List
// ═══════════════════════════════════════════════

describe('historyList', () => {
    test('reverses hand histories', () => {
        const histories = [{ hand_number: 1 }, { hand_number: 2 }, { hand_number: 3 }];
        const result = PokerLogic.historyList(histories);
        expect(result[0].hand_number).toBe(3);
        expect(result[2].hand_number).toBe(1);
    });

    test('handles null/undefined', () => {
        expect(PokerLogic.historyList(null)).toEqual([]);
        expect(PokerLogic.historyList(undefined)).toEqual([]);
    });

    test('does not mutate original', () => {
        const histories = [{ hand_number: 1 }, { hand_number: 2 }];
        PokerLogic.historyList(histories);
        expect(histories[0].hand_number).toBe(1);
    });
});
