/**
 * Texas Hold'em — Pure Logic Module
 *
 * Extracted from app.js for testability. Contains all pure functions
 * and state machine logic with no DOM or network dependencies.
 *
 * Used by app.js in the browser (via <script> tag) and by Jest tests (via require).
 */

const PokerLogic = {
    // ── Display Maps ──

    STREET_DISPLAY: {
        preflop: 'Pre-Flop', flop: 'Flop', turn: 'Turn',
        river: 'River', showdown: 'Showdown', hand_over: 'Hand Over',
    },

    ACTION_DISPLAY: {
        fold: 'FOLD', check: 'CHECK', call: 'CALL',
        bet: 'BET', raise: 'RAISE', small_blind: 'SB', big_blind: 'BB',
    },

    ACTION_FORMAT: {
        fold: 'folds', check: 'checks', call: 'calls',
        bet: 'bets', raise: 'raises to', small_blind: 'posts small blind',
        big_blind: 'posts big blind',
    },

    AI_STYLE_FORMAT: {
        loose_passive: 'Loose-Passive', tight_aggressive: 'Tight-Aggressive',
        gto: 'GTO', random: 'Random',
    },

    POSITION_TOOLTIPS: {
        'BTN': 'Button — Acts last post-flop. Best position at the table.',
        'BTN/SB': 'Button / Small Blind — In heads-up play, the dealer posts the small blind.',
        'SB': 'Small Blind — Posts half the minimum bet. First to act post-flop.',
        'BB': 'Big Blind — Posts the full minimum bet. Last to act pre-flop (gets an option).',
        'UTG': 'Under The Gun — First to act pre-flop. The tightest position.',
        'UTG+1': 'Under The Gun +1 — Second earliest position.',
        'MP': 'Middle Position — Moderate positional advantage.',
        'MP+1': 'Middle Position +1',
        'MP+2': 'Middle Position +2',
        'HJ': 'Hijack — Two seats before the button. Good for stealing blinds.',
        'CO': 'Cutoff — One seat before the button. Very strong late position.',
    },

    BET_TYPE_TOOLTIPS: {
        'value': 'Value Bet — You have a strong hand and are betting to extract chips from opponents who will call with worse hands.',
        'semi_bluff': 'Semi-Bluff — You have a drawing hand. You win if opponents fold, or if you hit your draw.',
        'bluff': 'Bluff — You have a weak hand but are betting to make opponents fold better hands.',
        'cbet': 'Continuation Bet — Following up on pre-flop aggression with a bet on the flop.',
    },

    AI_STYLE_TOOLTIPS: {
        loose_passive: 'Loose-Passive: Plays many hands, mostly calls, rarely raises. Easy to push around.',
        tight_aggressive: 'Tight-Aggressive: Plays fewer hands but bets and raises aggressively. Strong style.',
        gto: 'GTO (Game Theory Optimal): Balanced strategy mixing bets, calls, and folds at theoretically optimal frequencies.',
    },

    // ── Computed Properties ──

    streetDisplay(street) {
        return PokerLogic.STREET_DISPLAY[street] || street;
    },

    canAct(state) {
        return state.phase === 'playing'
            && state.action_seat >= 0
            && state.players?.[state.action_seat]?.player_type === 'human';
    },

    getValidAction(validActions, ...actionNames) {
        const actions = validActions?.actions || [];
        return actions.find(a => actionNames.includes(a.action));
    },

    toCallAmount(validActions) {
        const raw = validActions?.to_call || 0;
        const stack = validActions?.player_stack ?? Infinity;
        return Math.min(raw, stack);
    },

    isCallAllIn(validActions) {
        const callAction = PokerLogic.getValidAction(validActions, 'call');
        return callAction?.is_all_in || false;
    },

    checkCallLabel(validActions) {
        const tca = PokerLogic.toCallAmount(validActions);
        if (tca <= 0) return 'Check';
        if (PokerLogic.isCallAllIn(validActions)) return `All-In $${tca}`;
        return `Call $${tca}`;
    },

    canRaise(state) {
        if (!PokerLogic.canAct(state) || !state.valid_actions) return false;
        return !!(PokerLogic.getValidAction(state.valid_actions, 'bet', 'raise'));
    },

    raiseMin(validActions, bigBlind) {
        const ra = PokerLogic.getValidAction(validActions, 'bet', 'raise');
        return ra?.min || bigBlind;
    },

    raiseMax(validActions, state) {
        const ra = PokerLogic.getValidAction(validActions, 'bet', 'raise');
        return ra?.max || (state.players?.[state.action_seat]?.stack || 100);
    },

    raiseLabel(validActions, betAmount, raiseMax) {
        if (!validActions) return 'Raise';
        const ra = PokerLogic.getValidAction(validActions, 'bet', 'raise');
        if (!ra) return 'Raise';
        if (betAmount >= raiseMax) return `All-In $${raiseMax}`;
        return ra.action === 'bet' ? `Bet $${betAmount}` : `Raise to $${betAmount}`;
    },

    sliderStep(raiseMin, raiseMax) {
        const range = raiseMax - raiseMin;
        if (range < 100) return 1;
        if (range < 500) return 5;
        if (range < 2000) return 10;
        if (range < 5000) return 25;
        if (range < 20000) return 50;
        if (range < 100000) return 100;
        return 250;
    },

    snapBet(val, raiseMin, raiseMax, step) {
        if (val <= raiseMin) return raiseMin;
        if (val >= raiseMax) return raiseMax;
        return Math.round(val / step) * step;
    },

    setBetPreset(pot, mult, raiseMin, raiseMax, step) {
        const target = Math.round((pot || 0) * mult);
        return PokerLogic.snapBet(Math.max(raiseMin, Math.min(target, raiseMax)), raiseMin, raiseMax, step);
    },

    // ── Display Helpers ──

    getLastAction(actionLog, seat) {
        for (let i = actionLog.length - 1; i >= 0; i--) {
            if (actionLog[i].seat === seat) return actionLog[i].action;
        }
        return '';
    },

    getLastActionDisplay(actionLog, seat) {
        const a = PokerLogic.getLastAction(actionLog, seat);
        return PokerLogic.ACTION_DISPLAY[a] || a.toUpperCase();
    },

    formatAction(entry) {
        return PokerLogic.ACTION_FORMAT[entry.action] || entry.action;
    },

    formatAIStyle(s) {
        return PokerLogic.AI_STYLE_FORMAT[s] || s;
    },

    positionTooltip(pos) {
        return PokerLogic.POSITION_TOOLTIPS[pos] || pos;
    },

    betTypeTooltip(type) {
        return PokerLogic.BET_TYPE_TOOLTIPS[type] || type;
    },

    aiStyleTooltip(style) {
        return PokerLogic.AI_STYLE_TOOLTIPS[style] || style;
    },

    isWinner(showdown, seat) {
        return showdown?.winners?.some(w => w.seat === seat) || false;
    },

    isWinnerCard(showdown, seat, card) {
        if (!showdown?.hand_results?.[seat]?.cards) return false;
        return showdown.hand_results[seat].cards.some(c => c.short === card.short);
    },

    sliderRecommendStyle(advisor, raiseMin, raiseMax) {
        if (!advisor?.top_action?.bet_range) return 'display:none';
        const [lo, hi] = advisor.top_action.bet_range;
        const range = raiseMax - raiseMin;
        if (range <= 0) return 'display:none';
        const left = Math.max(0, ((lo - raiseMin) / range) * 100);
        const right = Math.min(100, ((hi - raiseMin) / range) * 100);
        const width = Math.max(2, right - left);
        return `left:${left}%;width:${width}%`;
    },

    // ── Card Visibility (Pass & Play) ──

    shouldShowCards(player, state, hideHands, passPlayActive) {
        // Always show at showdown / hand over
        if (state.street === 'showdown' || state.street === 'hand_over') {
            return !player.is_folded && !!player.hole_cards;
        }
        // If hide hands is off, show all revealed cards
        if (!hideHands) return !!player.hole_cards;
        // If pass-play countdown is active, hide everything
        if (passPlayActive) return false;

        const humans = (state.players || []).filter(
            p => p.player_type === 'human' && !p.is_folded && !p.is_sitting_out && p.stack > 0
        );

        // If no humans in hand, show everything (all-AI)
        if (humans.length === 0) return !!player.hole_cards;

        // Single human: always show that human's cards, always hide AI cards
        if (humans.length === 1) {
            if (player.player_type === 'human') return !!player.hole_cards;
            return false;
        }

        // Multiple humans (pass-and-play): only show the current actor's cards
        if (state.action_seat >= 0 && player.seat === state.action_seat && player.player_type === 'human') {
            return !!player.hole_cards;
        }
        return false;
    },

    // ── Setup Helpers ──

    canAddPlayer(players) {
        return players.length < 10;
    },

    canRemovePlayer(players) {
        return players.length > 2;
    },

    makeNewPlayer(existingCount, defaultStack) {
        return {
            name: `Player ${existingCount + 1}`,
            stack: defaultStack || 1000,
            player_type: 'ai',
            ai_style: 'random',
            adaptive: false,
        };
    },

    // ── State Management ──

    /**
     * Determine if a seq-stamped event is stale.
     * Returns true if the event should be ignored.
     */
    isStaleEvent(eventSeq, lastSeq) {
        return !!(eventSeq && eventSeq < lastSeq);
    },

    /**
     * Detect what changed between previous and new state.
     * Returns { turnChanged, newHand, playersChanged, streetChanged }.
     */
    detectChanges(prevState, newData) {
        const prevActionSeat = prevState.action_seat;
        const prevHandNum = prevState.hand_number;
        const prevInHand = (prevState.players || []).filter(
            p => !p.is_folded && !p.is_sitting_out
        ).length;

        const mergedState = { ...prevState };
        for (const key in newData) {
            if (newData.hasOwnProperty(key)) {
                mergedState[key] = newData[key];
            }
        }

        const newInHand = (mergedState.players || []).filter(
            p => !p.is_folded && !p.is_sitting_out
        ).length;

        return {
            turnChanged: mergedState.action_seat !== prevActionSeat,
            newHand: mergedState.hand_number !== prevHandNum,
            playersChanged: newInHand !== prevInHand,
            streetChanged: !!(newData.street && newData.street !== prevState.street),
        };
    },

    /**
     * Determine advisor action needed after state update.
     * Returns: 'use_piggybacked' | 'fetch_new' | 'keep' | 'clear'
     */
    advisorAction(opts) {
        const { canAct, advisorEnabled, advisorLoading, hasAdvisor,
                piggybackedAdvisor, turnChanged, streetChanged,
                playersChanged, newHand } = opts;

        if (!canAct) return 'clear';
        if (newHand) return 'clear';

        if (piggybackedAdvisor && advisorEnabled) return 'use_piggybacked';

        if (turnChanged || streetChanged || playersChanged) {
            if (advisorEnabled && !advisorLoading) return 'fetch_new';
            return 'clear';
        }

        if (!hasAdvisor && !advisorLoading && advisorEnabled) return 'fetch_new';

        return 'keep';
    },

    // ── History ──

    historyList(handHistories) {
        return (handHistories || []).slice().reverse();
    },

    // ── Hand Replayer ──

    /**
     * Build the visual state at a given step index for hand replay.
     * Step 0 = initial state (blinds not yet posted).
     * Each subsequent step applies one action from hand.actions.
     *
     * @param {Object} hand - HandHistory dict with players, actions, community_cards, hole_cards, winners
     * @param {number} stepIndex - 0..hand.actions.length (inclusive, last = final state)
     * @returns {Object} { players, communityCards, pot, street, currentAction, isShowdown }
     */
    buildReplayState(hand, stepIndex) {
        if (!hand || !hand.players) return null;

        // Clone player starting state
        const players = hand.players.map(p => ({
            seat: p.seat,
            name: p.name,
            stack: p.stack,
            current_bet: 0,
            is_folded: false,
            is_all_in: false,
            hole_cards: [],    // Hidden until showdown
            color: p.color || null,
        }));

        const bySeat = {};
        players.forEach(p => { bySeat[p.seat] = p; });

        let pot = 0;
        let street = 'preflop';
        let currentAction = null;
        let prevStreet = 'preflop';

        // Apply actions up to stepIndex
        const actions = hand.actions || [];
        const limit = Math.min(stepIndex, actions.length);
        for (let i = 0; i < limit; i++) {
            const a = actions[i];
            const p = bySeat[a.seat];

            // When street changes, sweep bets into pot
            if (a.street !== prevStreet) {
                players.forEach(pl => { pl.current_bet = 0; });
                prevStreet = a.street;
            }
            street = a.street;

            if (!p) continue;

            if (a.action === 'fold') {
                p.is_folded = true;
            } else if (a.action === 'check') {
                // No chip movement
            } else {
                // call, bet, raise, small_blind, big_blind
                const amt = a.amount || 0;
                p.stack -= (amt - p.current_bet);
                p.current_bet = amt;
                if (p.stack <= 0) {
                    p.stack = 0;
                    p.is_all_in = true;
                }
            }

            if (a.is_all_in) p.is_all_in = true;
            pot = a.pot_after || pot;
            currentAction = a;
        }

        // Determine community cards visible at this street
        const allComm = hand.community_cards || [];
        let communityCards = [];
        if (street === 'flop' || street === 'turn' || street === 'river' || street === 'showdown') {
            communityCards = allComm.slice(0, 3);  // Flop
        }
        if (street === 'turn' || street === 'river' || street === 'showdown') {
            communityCards = allComm.slice(0, 4);  // + Turn
        }
        if (street === 'river' || street === 'showdown') {
            communityCards = allComm.slice(0, 5);  // + River
        }

        // At final step or showdown, reveal hole cards and show winners
        const isShowdown = stepIndex >= actions.length;
        if (isShowdown && hand.hole_cards) {
            for (const [seat, cards] of Object.entries(hand.hole_cards)) {
                const p = bySeat[parseInt(seat)];
                if (p) p.hole_cards = cards;
            }
            communityCards = allComm.slice(0, 5);
        }

        return {
            players,
            communityCards,
            pot,
            street,
            currentAction,
            isShowdown,
            winners: isShowdown ? (hand.winners || []) : [],
            handRanks: isShowdown ? (hand.hand_ranks || {}) : {},
            stepIndex: limit,
            totalSteps: actions.length,
        };
    },
};

// Export for both browser and Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PokerLogic;
} else if (typeof window !== 'undefined') {
    window.PokerLogic = PokerLogic;
}
