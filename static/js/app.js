/**
 * Texas Hold'em — Main Application
 * Alpine.js store + Socket.IO real-time + card picker + advisor
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('pokerApp', () => ({
        // ── Core State ──
        state: {
            phase: 'setup', street: 'preflop', hand_number: 0,
            dealer_seat: 0, small_blind: 5, big_blind: 10, pot: 0,
            community_cards: [], burned_cards: 0, players: [],
            positions: {}, action_seat: -1, current_bet: 0,
            valid_actions: null, can_start_hand: false,
            hand_histories: [], current_actions: [],
            used_cards: [], manual_deal: false,
            hand_history: null,
        },

        // ── UI State ──
        sidebarTab: 'advisor',
        showSetup: true,
        showdown: null,
        advisor: null,
        actionLog: [],
        aiThinkingSeat: -1,
        betAmount: 200,
        socket: null,
        mobileSidebar: false,
        soundEnabled: true,

        // Card picker
        pickerTarget: 'community',

        // Player editor
        editingPlayer: null,
        advisorLoading: false,
        advisorEnabled: true,
        _advisorFetchId: 0,

        // Street tracking for sounds
        _lastStreet: '',
        _lastHandNum: 0,

        // Pass & Play
        hideHands: true,
        passPlayActive: false,
        passPlayCountdown: 3,
        passPlayTimer: null,
        lastHumanSeat: -1,
        autoAdvanceTimer: null,
        gameOverDismissed: false,

        // Settings (local copy, synced to server)
        localSettings: {
            timing_preset: 'realistic',
            variance: 30,
            burn_cards: true,
            auto_escalate: false,
            escalate_interval: 10,
            escalate_multiplier: 1.5,
            pass_play_seconds: 3,
            auto_advance: false,
            auto_advance_delay: 5,
        },

        // Setup modal data
        setupData: {
            small_blind: 100,
            big_blind: 200,
            players: [
                { name: 'You', stack: 10000, player_type: 'human', ai_style: 'random' },
                { name: 'Alice', stack: 10000, player_type: 'ai', ai_style: 'random' },
                { name: 'Bob', stack: 10000, player_type: 'ai', ai_style: 'random' },
            ],
        },
        defaultStack: 10000,

        // ── Computed Properties ──

        get streetDisplay() {
            const m = { preflop:'Pre-Flop', flop:'Flop', turn:'Turn', river:'River', showdown:'Showdown', hand_over:'Hand Over' };
            return m[this.state.street] || this.state.street;
        },

        get humanSeat() {
            const p = this.state.players?.find(p => p.player_type === 'human');
            return p ? p.seat : 0;
        },

        get canAct() {
            return this.state.phase === 'playing'
                && this.state.action_seat >= 0
                && this.state.players?.[this.state.action_seat]?.player_type === 'human';
        },

        get toCallAmount() {
            const raw = this.state.valid_actions?.to_call || 0;
            const stack = this.state.valid_actions?.player_stack ?? Infinity;
            return Math.min(raw, stack);
        },

        get isCallAllIn() {
            const actions = this.state.valid_actions?.actions || [];
            const callAction = actions.find(a => a.action === 'call');
            return callAction?.is_all_in || false;
        },

        get checkCallLabel() {
            if (this.toCallAmount <= 0) return 'Check';
            if (this.isCallAllIn) return `All-In $${this.toCallAmount}`;
            return `Call $${this.toCallAmount}`;
        },

        get canRaise() {
            if (!this.canAct || !this.state.valid_actions) return false;
            return (this.state.valid_actions.actions || []).some(a => a.action === 'bet' || a.action === 'raise');
        },

        get raiseLabel() {
            if (!this.state.valid_actions) return 'Raise';
            const ra = (this.state.valid_actions.actions || []).find(a => a.action === 'bet' || a.action === 'raise');
            if (this.betAmount >= this.raiseMax) return `All-In $${this.raiseMax}`;
            return ra?.action === 'bet' ? `Bet $${this.betAmount}` : `Raise to $${this.betAmount}`;
        },

        get raiseMin() {
            const ra = (this.state.valid_actions?.actions || []).find(a => a.action === 'bet' || a.action === 'raise');
            return ra?.min || this.state.big_blind;
        },

        get raiseMax() {
            const ra = (this.state.valid_actions?.actions || []).find(a => a.action === 'bet' || a.action === 'raise');
            return ra?.max || (this.state.players?.[this.state.action_seat]?.stack || 100);
        },

        get sliderStep() {
            const range = this.raiseMax - this.raiseMin;
            if (range < 100) return 1;
            if (range < 500) return 5;
            if (range < 2000) return 10;
            if (range < 5000) return 25;
            if (range < 20000) return 50;
            if (range < 100000) return 100;
            return 250;
        },

        snapBet(val) {
            // Snap dragged value to clean increment, but keep min/max exact
            if (val <= this.raiseMin) return this.raiseMin;
            if (val >= this.raiseMax) return this.raiseMax;
            const step = this.sliderStep;
            return Math.round(val / step) * step;
        },

        // ── Initialization ──

        init() {
            this.connectSocket();
            this.loadState();
            this.setupKeyboard();
            // Enable sound by default (needs user interaction to start AudioContext)
            if (this.soundEnabled && window.pokerSounds) {
                window.pokerSounds.enabled = true;
            }
        },

        connectSocket() {
            try {
                this.socket = io({ transports: ['websocket', 'polling'] });

                this.socket.on('state_update', (data) => {
                    this.updateState(data);
                });

                this.socket.on('ai_thinking', (data) => {
                    this.aiThinkingSeat = data.seat;
                });

                this.socket.on('ai_action', (data) => {
                    this.aiThinkingSeat = -1;
                    // Sound for AI action
                    const act = data.decision?.action;
                    if (act === 'fold') window.pokerSounds?.fold();
                    else if (act === 'check') window.pokerSounds?.check();
                    else if (act === 'call' || act === 'bet' || act === 'raise') window.pokerSounds?.chipBet();
                    if (data.state) this.updateState(data.state);
                    if (data.result?.showdown || data.result?.winners) {
                        this.showdown = data.result;
                        window.pokerSounds?.win();
                        this.startAutoAdvance();
                    }
                });
            } catch (e) {
                console.warn('Socket connection failed, using REST only:', e);
            }
        },

        async loadState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                this.updateState(data);
                if (data.phase !== 'setup') this.showSetup = false;
            } catch (e) {
                console.error('Failed to load state:', e);
            }
        },

        updateState(data) {
            if (!data) return;
            const prevActionSeat = this.state.action_seat;
            const prevHandNum = this.state.hand_number;
            const prevInHand = (this.state.players || []).filter(p => !p.is_folded && !p.is_sitting_out).length;

            for (const key in data) {
                if (data.hasOwnProperty(key)) {
                    this.state[key] = data[key];
                }
            }

            if (data.current_actions) {
                this.actionLog = data.current_actions;
            }

            const turnChanged = this.state.action_seat !== prevActionSeat;
            const newHand = this.state.hand_number !== prevHandNum;
            const playersChanged = (this.state.players || []).filter(p => !p.is_folded && !p.is_sitting_out).length !== prevInHand;

            // Reset slider on new hand or turn change
            if (turnChanged || newHand) {
                this.betAmount = this.raiseMin;
            }

            if (this.canAct) {
                if (this.betAmount < this.raiseMin) this.betAmount = this.raiseMin;
                if (this.betAmount > this.raiseMax) this.betAmount = this.raiseMax;

                // Check for server-pushed advisor data (piggy-backed on state_update)
                if (data._advisor && this.advisorEnabled) {
                    this.advisor = data._advisor;
                    this.advisorLoading = false;
                } else if (!this.advisorLoading && !this.advisor && this.advisorEnabled) {
                    // Fallback: fetch via HTTP only if no data and not already loading
                    this.fetchAdvisor();
                } else if ((turnChanged || playersChanged) && this.advisorEnabled && !this.advisorLoading) {
                    // Refetch if situation changed but no push data
                    this.fetchAdvisor();
                }
                this.checkPassPlay();
            } else {
                // Show AI thinking status while waiting, clear advisor data
                this.advisor = null;
                this.advisorLoading = false;
                if (this.state.phase !== 'playing') {
                    this.lastHumanSeat = -1;
                }
            }

            if (newHand) {
                this.advisor = null;
                this.advisorLoading = false;
            }

            if (data.street && data.street !== this._lastStreet) {
                if (['flop','turn','river'].includes(data.street)) {
                    window.pokerSounds?.streetReveal();
                }
                this._lastStreet = data.street;
            }
            if (data.hand_number && data.hand_number !== this._lastHandNum) {
                window.pokerSounds?.cardDeal();
                this._lastHandNum = data.hand_number;
            }
        },

        // ── API Methods ──

        async startNewGame() {
            try {
                const res = await fetch('/api/new_game', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.setupData),
                });
                const data = await res.json();
                if (data.ok) {
                    // Hard reset all UI state
                    this.showdown = null;
                    this.advisor = null;
                    this.advisorLoading = false;
                    this._advisorFetchId++;  // Invalidate any in-flight advisor fetches
                    this.actionLog = [];
                    this.aiThinkingSeat = -1;
                    this._lastStreet = '';
                    this._lastHandNum = 0;
                    this.lastHumanSeat = -1;
                    this.passPlayActive = false;
                    this.gameOverDismissed = false;
                    this.cancelAutoAdvance();
                    // Apply server state
                    this.updateState(data.state);
                    this.showSetup = false;
                }
            } catch (e) { console.error('Start game failed:', e); }
        },

        async newHand() {
            if (!this.state.can_start_hand && this.state.phase === 'playing') return;
            try {
                const res = await fetch('/api/new_hand', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    this.updateState(data.state);
                    this.showdown = null;
                    this.advisor = null;
                }
            } catch (e) { console.error('New hand failed:', e); }
        },

        async doAction(action, amount = 0) {
            if (!this.canAct) return;
            const seat = this.state.action_seat;
            try {
                const res = await fetch('/api/action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ seat, action, amount }),
                });
                const data = await res.json();
                if (data.error) { console.warn('Action error:', data.error); return; }
                // Sound effects for actions
                if (action === 'fold') window.pokerSounds?.fold();
                else if (action === 'check') window.pokerSounds?.check();
                else if (action === 'call' || action === 'bet' || action === 'raise') window.pokerSounds?.chipBet();
                if (data.state) this.updateState(data.state);
                // Check for piggy-backed advisor data from action response
                if (data._advisor && this.advisorEnabled) {
                    this.advisor = data._advisor;
                    this.advisorLoading = false;
                }
                if (data.showdown || data.winners) {
                    this.showdown = data;
                    window.pokerSounds?.win();
                    this.startAutoAdvance();
                }
            } catch (e) { console.error('Action failed:', e); }
        },

        doCheckCall() {
            this.toCallAmount > 0 ? this.doAction('call') : this.doAction('check');
        },

        doRaise() {
            if (!this.canRaise) return;
            const ra = (this.state.valid_actions.actions || []).find(a => a.action === 'bet' || a.action === 'raise');
            this.doAction(ra.action, this.betAmount);
        },

        executeRecommendation(rec) {
            if (!this.canAct) return;
            const action = rec.action;
            if (action === 'fold') {
                this.doAction('fold');
            } else if (action === 'check') {
                this.doAction('check');
            } else if (action === 'call') {
                this.doCheckCall();
            } else if (action === 'bet' || action === 'raise') {
                // Use midpoint of recommended bet range, or current betAmount if no range
                if (rec.bet_range) {
                    const mid = this.snapBet(Math.round((rec.bet_range[0] + rec.bet_range[1]) / 2));
                    this.betAmount = Math.max(this.raiseMin, Math.min(mid, this.raiseMax));
                }
                const ra = (this.state.valid_actions?.actions || []).find(a => a.action === 'bet' || a.action === 'raise');
                if (ra) this.doAction(ra.action, this.betAmount);
            }
        },

        async undoAction() {
            try {
                const res = await fetch('/api/undo', { method: 'POST' });
                const data = await res.json();
                if (data.ok) this.updateState(data.state);
            } catch (e) { console.error('Undo failed:', e); }
        },

        async fetchAdvisor() {
            if (!this.canAct || !this.advisorEnabled) {
                if (!this.advisorEnabled) {
                    this.advisor = null;
                }
                this.advisorLoading = false;
                return;
            }
            // Generation counter: ignore responses from stale fetches
            const fetchId = ++this._advisorFetchId;
            this.advisorLoading = true;
            try {
                const res = await fetch('/api/advisor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ seat: this.state.action_seat }),
                });
                const data = await res.json();
                // Drop result if a newer fetch was started while we were waiting
                if (fetchId !== this._advisorFetchId) return;
                if (!data.error) {
                    this.advisor = data;
                }
            } catch (e) {
                if (fetchId !== this._advisorFetchId) return;
                console.error('Advisor failed:', e);
            }
            if (fetchId === this._advisorFetchId) {
                this.advisorLoading = false;
            }
        },

        sliderRecommendStyle() {
            if (!this.advisor?.top_action?.bet_range) return 'display:none';
            const [lo, hi] = this.advisor.top_action.bet_range;
            const min = this.raiseMin;
            const max = this.raiseMax;
            const range = max - min;
            if (range <= 0) return 'display:none';
            const left = Math.max(0, ((lo - min) / range) * 100);
            const right = Math.min(100, ((hi - min) / range) * 100);
            const width = Math.max(2, right - left);
            return `left:${left}%;width:${width}%`;
        },

        setBetPreset(mult) {
            const target = Math.round((this.state.pot || 0) * mult);
            this.betAmount = this.snapBet(Math.max(this.raiseMin, Math.min(target, this.raiseMax)));
        },

        async saveSettings() {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.localSettings),
                });
            } catch (e) { console.error('Settings failed:', e); }
        },

        dismissShowdown() {
            this.showdown = null;
            this.cancelAutoAdvance();
        },

        // ── Auto-Advance ──

        startAutoAdvance() {
            this.cancelAutoAdvance();
            if (!this.localSettings.auto_advance) return;
            const delay = (this.localSettings.auto_advance_delay || 5) * 1000;
            this.autoAdvanceTimer = setTimeout(() => {
                if (this.showdown) {
                    this.dismissShowdown();
                    this.newHand();
                }
            }, delay);
        },

        cancelAutoAdvance() {
            if (this.autoAdvanceTimer) {
                clearTimeout(this.autoAdvanceTimer);
                this.autoAdvanceTimer = null;
            }
        },

        // ── Card Picker ──

        async toggleManualDeal() {
            try {
                const res = await fetch('/api/toggle_manual_deal', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: !this.state.manual_deal }),
                });
                const data = await res.json();
                if (data.ok && data.state) this.updateState(data.state);
            } catch (e) { console.error('Toggle manual deal failed:', e); }
        },

        isCardUsed(shortStr) {
            return (this.state.used_cards || []).includes(shortStr);
        },

        async assignPickerCard(shortStr) {
            const target = this.pickerTarget;
            let apiTarget, seat;

            if (target === 'community') {
                apiTarget = 'community';
                seat = null;
            } else if (target.startsWith('player_')) {
                apiTarget = 'player';
                seat = parseInt(target.split('_')[1]);
            } else {
                return;
            }

            try {
                const body = { card: shortStr, target: apiTarget };
                if (seat !== null) body.seat = seat;

                const res = await fetch('/api/deal_card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (data.ok && data.state) this.updateState(data.state);
                else if (data.error) console.warn('Card assign error:', data.error);
            } catch (e) { console.error('Card assign failed:', e); }
        },

        async unassignCard(shortStr, target, seat) {
            if (!this.state.manual_deal || !shortStr) return;
            try {
                const body = { card: shortStr, target };
                if (seat !== undefined) body.seat = seat;

                const res = await fetch('/api/unassign_card', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (data.ok && data.state) this.updateState(data.state);
            } catch (e) { console.error('Card unassign failed:', e); }
        },

        // ── Setup Helpers ──

        addSetupPlayer() {
            if (this.setupData.players.length >= 10) return;
            const n = this.setupData.players.length + 1;
            this.setupData.players.push({
                name: `Player ${n}`, stack: this.defaultStack || 1000,
                player_type: 'ai', ai_style: 'random',
            });
        },

        removeSetupPlayer(idx) {
            if (this.setupData.players.length <= 2) return;
            this.setupData.players.splice(idx, 1);
        },

        // ── Display Helpers ──

        getLastAction(seat) {
            for (let i = this.actionLog.length - 1; i >= 0; i--) {
                if (this.actionLog[i].seat === seat) return this.actionLog[i].action;
            }
            return '';
        },

        getLastActionDisplay(seat) {
            const a = this.getLastAction(seat);
            const m = { fold:'FOLD', check:'CHECK', call:'CALL', bet:'BET', raise:'RAISE', small_blind:'SB', big_blind:'BB' };
            return m[a] || a.toUpperCase();
        },

        formatAction(entry) {
            const m = { fold:'folds', check:'checks', call:'calls', bet:'bets', raise:'raises to', small_blind:'posts small blind', big_blind:'posts big blind' };
            return m[entry.action] || entry.action;
        },

        formatAIStyle(s) {
            return { loose_passive:'Loose-Passive', tight_aggressive:'Tight-Aggressive', gto:'GTO', random:'Random' }[s] || s;
        },

        getPlayerColor(seat) {
            return this.state.players?.[seat]?.color || 'var(--text-primary)';
        },

        positionTooltip(pos) {
            const t = {
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
            };
            return t[pos] || pos;
        },

        betTypeTooltip(type) {
            const t = {
                'value': 'Value Bet — You have a strong hand and are betting to extract chips from opponents who will call with worse hands.',
                'semi_bluff': 'Semi-Bluff — You have a drawing hand. You win if opponents fold, or if you hit your draw.',
                'bluff': 'Bluff — You have a weak hand but are betting to make opponents fold better hands.',
                'cbet': 'Continuation Bet — Following up on pre-flop aggression with a bet on the flop.',
            };
            return t[type] || type;
        },

        aiStyleTooltip(style) {
            const t = {
                loose_passive: 'Loose-Passive: Plays many hands, mostly calls, rarely raises. Easy to push around.',
                tight_aggressive: 'Tight-Aggressive: Plays fewer hands but bets and raises aggressively. Strong style.',
                gto: 'GTO (Game Theory Optimal): Balanced strategy mixing bets, calls, and folds at theoretically optimal frequencies.',
            };
            return t[style] || style;
        },

        isWinner(seat) {
            return this.showdown?.winners?.some(w => w.seat === seat) || false;
        },

        isWinnerCard(seat, card) {
            if (!this.showdown?.hand_results?.[seat]?.cards) return false;
            return this.showdown.hand_results[seat].cards.some(c => c.short === card.short);
        },

        // ── Pass & Play ──

        shouldShowCards(player) {
            // Always show at showdown / hand over
            if (this.state.street === 'showdown' || this.state.street === 'hand_over') {
                return !player.is_folded && !!player.hole_cards;
            }
            // If hide hands is off, show all revealed cards
            if (!this.hideHands) return !!player.hole_cards;
            // If pass-play countdown is active, hide everything
            if (this.passPlayActive) return false;

            const humans = (this.state.players || []).filter(
                p => p.player_type === 'human' && !p.is_folded && !p.is_sitting_out && p.stack > 0
            );

            // If no humans in hand, show everything (all-AI)
            if (humans.length === 0) return !!player.hole_cards;

            // Single human: always show that human's cards, always hide AI cards
            if (humans.length === 1) {
                if (player.player_type === 'human') return !!player.hole_cards;
                return false; // Hide AI cards
            }

            // Multiple humans (pass-and-play): only show the current actor's cards
            if (this.state.action_seat >= 0 && player.seat === this.state.action_seat && player.player_type === 'human') {
                return !!player.hole_cards;
            }
            return false;
        },

        startPassPlayCountdown() {
            this.passPlayActive = true;
            this.passPlayCountdown = this.localSettings.pass_play_seconds || 3;
            window.pokerSounds?.tick();
            this.passPlayTimer = setInterval(() => {
                this.passPlayCountdown--;
                window.pokerSounds?.tick();
                if (this.passPlayCountdown <= 0) {
                    this.dismissPassPlay();
                }
            }, 1000);
        },

        dismissPassPlay() {
            this.passPlayActive = false;
            if (this.passPlayTimer) {
                clearInterval(this.passPlayTimer);
                this.passPlayTimer = null;
            }
        },

        checkPassPlay() {
            if (!this.hideHands || !this.canAct) return;
            const currentSeat = this.state.action_seat;
            if (currentSeat !== this.lastHumanSeat && this.lastHumanSeat >= 0) {
                this.startPassPlayCountdown();
            }
            this.lastHumanSeat = currentSeat;
        },

        // ── Hand History Navigation ──

        get historyList() {
            return (this.state.hand_histories || []).slice().reverse();
        },

        // ── Player Editing ──

        openPlayerEditor(seat) {
            if (this.state.phase === 'playing') return; // Can't edit during a hand
            const p = this.state.players?.[seat];
            if (!p) return;
            this.editingPlayer = {
                seat: p.seat,
                name: p.name,
                player_type: p.player_type,
                ai_style: p.ai_style,
                stack: p.stack,
                color: p.color,
            };
        },

        async savePlayerEdit() {
            if (!this.editingPlayer) return;
            try {
                const res = await fetch('/api/update_player', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.editingPlayer),
                });
                const data = await res.json();
                if (data.ok && data.state) this.updateState(data.state);
                this.editingPlayer = null;
            } catch (e) { console.error('Player edit failed:', e); }
        },

        cancelPlayerEdit() {
            this.editingPlayer = null;
        },

        // ── History Export ──

        async copyHistory() {
            try {
                const res = await fetch('/api/export_history');
                const text = await res.text();
                await navigator.clipboard.writeText(text);
                // Brief visual feedback — flash the copy button
                const btn = document.querySelector('[title*="Copy hand history"]');
                if (btn) {
                    const orig = btn.textContent;
                    btn.textContent = '✓ Copied';
                    setTimeout(() => btn.textContent = orig, 1500);
                }
            } catch (e) {
                console.error('Copy failed:', e);
            }
        },

        async downloadHistory() {
            try {
                const res = await fetch('/api/export_history');
                const text = await res.text();
                const blob = new Blob([text], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `holdem_history_${new Date().toISOString().slice(0,10)}.txt`;
                a.click();
                URL.revokeObjectURL(url);
            } catch (e) {
                console.error('Download failed:', e);
            }
        },

        // ── Sound Toggle ──

        toggleSound() {
            this.soundEnabled = window.pokerSounds?.toggle() || false;
        },

        // ── Keyboard ──

        setupKeyboard() {
            // Keyboard events now handled via @keydown.window on #app div
        },

        handleKey(e) {
            if (['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return;
            switch (e.key.toLowerCase()) {
                case 'f': if (this.canAct) this.doAction('fold'); break;
                case 'c': if (this.canAct) this.doCheckCall(); break;
                case 'r': if (this.canRaise) this.doRaise(); break;
                case 'n':
                    if (this.showdown) this.dismissShowdown();
                    this.newHand();
                    break;
                case 'z': this.undoAction(); break;
                case 'm': this.toggleSound(); break;
            }
        },
    }));
});
