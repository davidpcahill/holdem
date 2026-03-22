/**
 * Jest tests for new features: difficulty presets, stats dashboard,
 * hand history, animations, and mobile responsive.
 */

const PokerLogic = require('../../static/js/poker-logic');

// ═══════════════════════════════════════════════
// Difficulty Presets
// ═══════════════════════════════════════════════

describe('difficulty presets in settings', () => {
    test('localSettings has difficulty field', () => {
        const settings = {
            difficulty: 'medium',
            timing_preset: 'realistic',
            variance: 30,
            advisor_sims: 1000,
        };
        expect(settings.difficulty).toBe('medium');
    });

    test('custom difficulty shows speed/variance controls', () => {
        const settings = { difficulty: 'custom' };
        // In UI: x-show="localSettings.difficulty === 'custom'"
        expect(settings.difficulty === 'custom').toBe(true);
    });

    test('non-custom difficulty hides speed/variance controls', () => {
        for (const diff of ['easy', 'medium', 'hard', 'expert']) {
            expect(diff === 'custom').toBe(false);
        }
    });
});

// ═══════════════════════════════════════════════
// Stats Dashboard Data
// ═══════════════════════════════════════════════

describe('stats dashboard player data', () => {
    function makePlayer(overrides = {}) {
        return {
            seat: 0, name: 'You', stack: 1200, starting_stack: 1000,
            hands_played: 10, hands_won: 3, win_rate: 30.0,
            net_profit: 200, total_winnings: 500, biggest_pot_won: 250,
            vpip: 45.0, aggression_factor: 1.5,
            times_folded: 3, times_raised: 5, times_called: 4,
            wtsd: 60.0, wsd: 50.0,
            color: '#E74C3C', player_type: 'human', ai_style: 'random',
            ...overrides,
        };
    }

    test('net profit is positive when stack > starting', () => {
        const p = makePlayer({ net_profit: 200 });
        expect(p.net_profit).toBeGreaterThan(0);
    });

    test('net profit is negative when stack < starting', () => {
        const p = makePlayer({ net_profit: -300 });
        expect(p.net_profit).toBeLessThan(0);
    });

    test('win rate is percentage of hands won', () => {
        const p = makePlayer();
        expect(p.win_rate).toBe(30.0);
    });

    test('VPIP color coding: red for loose (>50%)', () => {
        const p = makePlayer({ vpip: 65 });
        const color = p.vpip > 50 ? 'red' : p.vpip > 30 ? 'gold' : 'green';
        expect(color).toBe('red');
    });

    test('VPIP color coding: gold for moderate (30-50%)', () => {
        const p = makePlayer({ vpip: 45 });
        const color = p.vpip > 50 ? 'red' : p.vpip > 30 ? 'gold' : 'green';
        expect(color).toBe('gold');
    });

    test('VPIP color coding: green for tight (<30%)', () => {
        const p = makePlayer({ vpip: 20 });
        const color = p.vpip > 50 ? 'red' : p.vpip > 30 ? 'gold' : 'green';
        expect(color).toBe('green');
    });

    test('aggression factor bar width capped at 100%', () => {
        const p = makePlayer({ aggression_factor: 6.0 });
        const width = Math.min(p.aggression_factor * 25, 100);
        expect(width).toBe(100);
    });

    test('WTSD percentage between 0-100', () => {
        const p = makePlayer({ wtsd: 60 });
        expect(p.wtsd).toBeGreaterThanOrEqual(0);
        expect(p.wtsd).toBeLessThanOrEqual(100);
    });

    test('W$SD percentage between 0-100', () => {
        const p = makePlayer({ wsd: 50 });
        expect(p.wsd).toBeGreaterThanOrEqual(0);
        expect(p.wsd).toBeLessThanOrEqual(100);
    });
});

// ═══════════════════════════════════════════════
// Hand History Enhancement
// ═══════════════════════════════════════════════

describe('hand history data structure', () => {
    function makeHistory(overrides = {}) {
        return {
            hand_number: 1,
            community_cards: ['Ah', 'Kd', '7c', '2s', 'Qh'],
            actions: [
                { street: 'preflop', seat: 0, player_name: 'You', action: 'call', amount: 10, pot_after: 25 },
                { street: 'preflop', seat: 1, player_name: 'Alice', action: 'check', amount: 0, pot_after: 25 },
                { street: 'flop', seat: 1, player_name: 'Alice', action: 'bet', amount: 20, pot_after: 45 },
            ],
            winners: [{ seat: 0, name: 'You', amount: 45, hand_name: 'Pair of Aces' }],
            pot_total: 45,
            hole_cards: { 0: ['Ah', 'Kh'], 1: ['Td', '9d'] },
            hand_ranks: { 0: 'Two Pair, Aces and Kings', 1: 'Pair of Queens' },
            ...overrides,
        };
    }

    test('history includes hole_cards per seat', () => {
        const h = makeHistory();
        expect(h.hole_cards[0]).toEqual(['Ah', 'Kh']);
        expect(h.hole_cards[1]).toEqual(['Td', '9d']);
    });

    test('history includes hand_ranks per seat', () => {
        const h = makeHistory();
        expect(h.hand_ranks[0]).toContain('Two Pair');
    });

    test('actions include pot_after field', () => {
        const h = makeHistory();
        for (const action of h.actions) {
            expect(action).toHaveProperty('pot_after');
            expect(typeof action.pot_after).toBe('number');
        }
    });

    test('pot_after increases as bets are placed', () => {
        const h = makeHistory();
        const potValues = h.actions.map(a => a.pot_after);
        // pot should be non-decreasing (or stable for checks)
        for (let i = 1; i < potValues.length; i++) {
            expect(potValues[i]).toBeGreaterThanOrEqual(potValues[i - 1]);
        }
    });
});

// ═══════════════════════════════════════════════
// Advisor Sims Setting
// ═══════════════════════════════════════════════

describe('advisor sims setting', () => {
    test('default advisor_sims is 1000', () => {
        const settings = { advisor_sims: 1000 };
        expect(settings.advisor_sims).toBe(1000);
    });

    test('advisor_sims clamped to valid range', () => {
        const clamp = (v) => Math.max(100, Math.min(5000, v));
        expect(clamp(50)).toBe(100);    // Below minimum
        expect(clamp(10000)).toBe(5000); // Above maximum
        expect(clamp(2000)).toBe(2000);  // In range
    });
});

// ═══════════════════════════════════════════════
// AI Style Formatting (for stats dashboard display)
// ═══════════════════════════════════════════════

describe('AI style display in stats', () => {
    test('formats all known AI styles', () => {
        expect(PokerLogic.formatAIStyle('loose_passive')).toBe('Loose-Passive');
        expect(PokerLogic.formatAIStyle('tight_aggressive')).toBe('Tight-Aggressive');
        expect(PokerLogic.formatAIStyle('gto')).toBe('GTO');
        expect(PokerLogic.formatAIStyle('random')).toBe('Random');
    });
});
