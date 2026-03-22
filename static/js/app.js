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
        soundVolume: 30,
        cardTheme: localStorage.getItem('cardTheme') || 'classic',

        // Card picker
        pickerTarget: 'community',

        // Player editor
        editingPlayer: null,
        advisorLoading: false,
        advisorEnabled: true,
        _advisorFetchId: 0,
        _advisorAbort: null,
        _socketConnected: false,
        _wasDisconnected: false,

        // Street tracking for sounds
        _lastStreet: '',
        _lastHandNum: 0,
        _lastSeq: 0,
        _lastPot: 0,
        _potPulse: false,

        // Pass & Play
        hideHands: true,
        passPlayActive: false,
        passPlayCountdown: 3,
        passPlayTimer: null,
        lastHumanSeat: -1,
        autoAdvanceTimer: null,
        gameOverDismissed: false,

        // Hand Replayer
        replayer: null,         // { hand, stepIndex, playing, speed, intervalId }
        replayerState: null,    // Computed replay state from buildReplayState()

        // Preflop Range Chart
        rangeOpen: false,
        rangePosition: 'BTN',
        rangePositions: [],
        rangeGrid: null,
        rangeData: null,        // Cached server response
        rangeCurrentHand: null, // [row, col] of current hand on grid

        // Chip Animations
        chipAnimations: true,
        _prevPlayerBets: {},   // Track previous bets to detect changes

        // Tutorial (scripted 10-hand mode)
        tutorial: {
            active: false,
            complete: false,
            handIndex: 0,
            totalHands: 10,
            title: null,
            intro: null,       // {title, body} shown before hand
            outro: null,       // {title, body} shown after hand
            guided: null,      // {action, tip} current guided action
            showIntro: false,
            showOutro: false,
            showComplete: false,
        },

        // Settings (local copy, synced to server)
        localSettings: {
            difficulty: 'medium',
            timing_preset: 'realistic',
            variance: 30,
            advisor_sims: 1000,
            burn_cards: true,
            auto_escalate: false,
            escalate_interval: 10,
            escalate_multiplier: 1.5,
            pass_play_seconds: 3,
            auto_advance: true,
            auto_advance_delay: 5,
        },

        // Setup modal data
        setupData: {
            small_blind: 100,
            big_blind: 200,
            players: [
                { name: 'You', stack: 10000, player_type: 'human', ai_style: 'random', adaptive: false },
                { name: 'Alice', stack: 10000, player_type: 'ai', ai_style: 'random', adaptive: false },
                { name: 'Bob', stack: 10000, player_type: 'ai', ai_style: 'random', adaptive: false },
            ],
        },
        defaultStack: 10000,

        // ── Computed Properties ──

        get streetDisplay() {
            return PokerLogic.streetDisplay(this.state.street);
        },

        get humanSeat() {
            const p = this.state.players?.find(p => p.player_type === 'human');
            return p ? p.seat : 0;
        },

        get canAct() {
            return PokerLogic.canAct(this.state);
        },

        get toCallAmount() {
            return PokerLogic.toCallAmount(this.state.valid_actions);
        },

        get isCallAllIn() {
            return PokerLogic.isCallAllIn(this.state.valid_actions);
        },

        get checkCallLabel() {
            return PokerLogic.checkCallLabel(this.state.valid_actions);
        },

        get canRaise() {
            return PokerLogic.canRaise(this.state);
        },

        get raiseLabel() {
            return PokerLogic.raiseLabel(this.state.valid_actions, this.betAmount, this.raiseMax);
        },

        get raiseMin() {
            return PokerLogic.raiseMin(this.state.valid_actions, this.state.big_blind);
        },

        get raiseMax() {
            return PokerLogic.raiseMax(this.state.valid_actions, this.state);
        },

        get sliderStep() {
            return PokerLogic.sliderStep(this.raiseMin, this.raiseMax);
        },

        snapBet(val) {
            return PokerLogic.snapBet(val, this.raiseMin, this.raiseMax, this.sliderStep);
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
                this.socket = io({
                    transports: ['websocket', 'polling'],
                    reconnection: true,
                    reconnectionAttempts: Infinity,
                    reconnectionDelay: 1000,
                    reconnectionDelayMax: 5000,
                });

                // ── Connection lifecycle ──
                this.socket.on('connect', () => {
                    console.log('[socket] connected');
                    this._socketConnected = true;
                    // Re-fetch full state after reconnection to sync
                    if (this._wasDisconnected) {
                        console.log('[socket] reconnected — re-syncing state');
                        this.loadState();
                        this._wasDisconnected = false;
                    }
                });

                this.socket.on('disconnect', (reason) => {
                    console.warn('[socket] disconnected:', reason);
                    this._socketConnected = false;
                    this._wasDisconnected = true;
                });

                this.socket.on('connect_error', (err) => {
                    console.warn('[socket] connection error:', err.message);
                    this._socketConnected = false;
                });

                this.socket.on('state_update', (data) => {
                    // Ignore stale socket updates that arrive after newer HTTP responses
                    if (data._seq && data._seq < this._lastSeq) return;
                    this.updateState(data);
                });

                this.socket.on('ai_thinking', (data) => {
                    this.aiThinkingSeat = data.seat;
                });

                this.socket.on('ai_action', (data) => {
                    // Ignore stale events from a previous game
                    if (data.state?._seq && data.state._seq < this._lastSeq) return;
                    // Tutorial bot actions come via HTTP response, not socket
                    if (this.tutorial.active) return;
                    this.aiThinkingSeat = -1;
                    // Sound for AI action
                    const act = data.decision?.action;
                    if (act === 'fold') window.pokerSounds?.fold();
                    else if (act === 'check') window.pokerSounds?.check();
                    else if (act === 'call' || act === 'bet' || act === 'raise') window.pokerSounds?.chipBet();

                    if (data.state) {
                        this.updateState(data.state);
                    }

                    if (data.result?.showdown || data.result?.winners) {
                        this.showdown = data.result;
                        window.pokerSounds?.win();
                        // Chip win animations
                        (data.result.winners || []).forEach(w => {
                            setTimeout(() => this.spawnWinChips(w.seat, w.amount), 300);
                        });
                        this.startAutoAdvance();
                    }
                });

                // Street reveal: server sends this AFTER a delay when flop/turn/river is dealt
                this.socket.on('street_reveal', (data) => {
                    // Ignore stale events from a previous game
                    if (data.state?._seq && data.state._seq < this._lastSeq) return;
                    if (this.tutorial.active) return;
                    window.pokerSounds?.streetReveal();
                    if (data.state) {
                        this.updateState(data.state);
                    }
                    // Show next AI's thinking indicator immediately to avoid "waiting" flash
                    if (data.next_thinking) {
                        this.aiThinkingSeat = data.next_thinking.seat;
                    }
                });

                // Advisor data pushed separately from ai_action to avoid blocking
                this.socket.on('advisor_update', (data) => {
                    if (this.advisorEnabled && this.canAct && !data.error) {
                        this.advisor = data;
                        // Cancel any in-flight HTTP advisor fetch — socket push won
                        this._advisorFetchId++;
                    }
                    this.advisorLoading = false;
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
            if (data._seq) this._lastSeq = data._seq;
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
            const streetChanged = data.street && data.street !== this._lastStreet;

            // Reset slider on new hand or turn change
            if (turnChanged || newHand) {
                this.betAmount = this.raiseMin;
            }

            if (this.canAct) {
                // It's human's turn — ensure AI thinking indicator is cleared
                this.aiThinkingSeat = -1;
                if (this.betAmount < this.raiseMin) this.betAmount = this.raiseMin;
                if (this.betAmount > this.raiseMax) this.betAmount = this.raiseMax;

                // Check for server-pushed advisor data (piggy-backed on state_update)
                if (data._advisor && this.advisorEnabled) {
                    this.advisor = data._advisor;
                    this.advisorLoading = false;
                } else if (turnChanged || streetChanged || playersChanged || newHand) {
                    // Situation changed — clear stale advisor and request fresh data
                    // Always fetch regardless of advisorLoading (prior loading is stale)
                    this.advisor = null;
                    if (this.advisorEnabled) {
                        this.fetchAdvisor();
                    }
                } else if (!this.advisor && !this.advisorLoading && this.advisorEnabled) {
                    // No advisor yet and not loading — fetch as fallback
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

            // Chip animations (bet → pot)
            this._checkChipAnimations(data);

            // Pot pulse animation when pot value changes
            if (data.pot !== undefined && data.pot !== this._lastPot && data.pot > 0) {
                this._potPulse = false;
                requestAnimationFrame(() => { this._potPulse = true; });
                this._lastPot = data.pot;
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

            // Update range chart current hand highlight
            if (this.rangeOpen && this.rangeGrid) {
                this._updateRangeCurrentHand();
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
                    // Always clear showdown overlay
                    this.showdown = null;
                    // Only apply HTTP state if AI hasn't already pushed newer state
                    // via socket while we were awaiting the response
                    if (!data.state?._seq || data.state._seq >= this._lastSeq) {
                        this.advisor = null;
                        this.advisorLoading = false;
                        this._advisorFetchId++;
                        this.aiThinkingSeat = -1;
                        this.updateState(data.state);
                    }
                }
            } catch (e) { console.error('New hand failed:', e); }
        },

        async doAction(action, amount = 0) {
            if (!this.canAct) return;
            // Tutorial: only allow the guided action
            if (this.tutorial.active && this.tutorial.guided) {
                const ga = this.tutorial.guided.action;
                if (action !== ga && !(action === 'bet' && ga === 'raise') && !(action === 'raise' && ga === 'bet')) return;
            }
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
                    (data.winners || []).forEach(w => {
                        setTimeout(() => this.spawnWinChips(w.seat, w.amount), 300);
                    });
                    if (!this.tutorial.active) this.startAutoAdvance();
                }
                // Tutorial: update guided action and show outro
                if (this.tutorial.active) {
                    if (data.guided) this.tutorial.guided = data.guided;
                    else this.tutorial.guided = null;
                    if (data.outro) {
                        this.tutorial.outro = data.outro;
                        // Delay showing outro to let showdown display first
                        setTimeout(() => { this.tutorial.showOutro = true; }, 1500);
                    }
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
            // Tutorial: only allow if it matches the guided action
            if (this.tutorial.active && this.tutorial.guided) {
                const ga = this.tutorial.guided.action;
                const ra = rec.action;
                if (ra !== ga && !(ra === 'bet' && ga === 'raise') && !(ra === 'raise' && ga === 'bet')) return;
            }
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
            // Cancel any in-flight advisor request
            if (this._advisorAbort) {
                this._advisorAbort.abort();
                this._advisorAbort = null;
            }
            // Generation counter: ignore responses from stale fetches
            const fetchId = ++this._advisorFetchId;
            const controller = new AbortController();
            this._advisorAbort = controller;
            this.advisorLoading = true;
            try {
                const res = await fetch('/api/advisor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ seat: this.state.action_seat }),
                    signal: controller.signal,
                });
                const data = await res.json();
                // Drop result if a newer fetch was started while we were waiting
                if (fetchId !== this._advisorFetchId) return;
                if (!data.error) {
                    this.advisor = data;
                }
            } catch (e) {
                if (e.name === 'AbortError') return;  // Cancelled — expected
                if (fetchId !== this._advisorFetchId) return;
                console.error('Advisor failed:', e);
            }
            if (fetchId === this._advisorFetchId) {
                this.advisorLoading = false;
                this._advisorAbort = null;
            }
        },

        sliderRecommendStyle() {
            return PokerLogic.sliderRecommendStyle(this.advisor, this.raiseMin, this.raiseMax);
        },

        setBetPreset(mult) {
            this.betAmount = PokerLogic.setBetPreset(this.state.pot, mult, this.raiseMin, this.raiseMax, this.sliderStep);
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
            if (!PokerLogic.canAddPlayer(this.setupData.players)) return;
            this.setupData.players.push(PokerLogic.makeNewPlayer(this.setupData.players.length, this.defaultStack));
        },

        removeSetupPlayer(idx) {
            if (!PokerLogic.canRemovePlayer(this.setupData.players)) return;
            this.setupData.players.splice(idx, 1);
        },

        // ── Display Helpers ──

        getLastAction(seat) {
            return PokerLogic.getLastAction(this.actionLog, seat);
        },

        getLastActionDisplay(seat) {
            return PokerLogic.getLastActionDisplay(this.actionLog, seat);
        },

        formatAction(entry) {
            return PokerLogic.formatAction(entry);
        },

        formatAIStyle(s) {
            return PokerLogic.formatAIStyle(s);
        },

        getPlayerColor(seat) {
            return this.state.players?.[seat]?.color || 'var(--text-primary)';
        },

        positionTooltip(pos) {
            return PokerLogic.positionTooltip(pos);
        },

        betTypeTooltip(type) {
            return PokerLogic.betTypeTooltip(type);
        },

        aiStyleTooltip(style) {
            return PokerLogic.aiStyleTooltip(style);
        },

        isWinner(seat) {
            return PokerLogic.isWinner(this.showdown, seat);
        },

        isWinnerCard(seat, card) {
            return PokerLogic.isWinnerCard(this.showdown, seat, card);
        },

        // ── Pass & Play ──

        shouldShowCards(player) {
            return PokerLogic.shouldShowCards(player, this.state, this.hideHands, this.passPlayActive);
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

        // ── Hand Replayer ──

        startReplay(handNumber) {
            const hand = (this.state.hand_histories || []).find(h => h.hand_number === handNumber);
            if (!hand || !hand.players) return;
            this.stopReplay();
            this.replayer = { hand, stepIndex: 0, playing: false, speed: 1, intervalId: null };
            this._updateReplayState();
            this.sidebarTab = 'replay';
        },

        stopReplay() {
            if (this.replayer?.intervalId) clearInterval(this.replayer.intervalId);
            this.replayer = null;
            this.replayerState = null;
        },

        replayStep(delta) {
            if (!this.replayer) return;
            const max = this.replayer.hand.actions.length;  // Final step = showdown
            this.replayer.stepIndex = Math.max(0, Math.min(max, this.replayer.stepIndex + delta));
            this._updateReplayState();
        },

        replayGoTo(step) {
            if (!this.replayer) return;
            this.replayer.stepIndex = step;
            this._updateReplayState();
        },

        replayPlayPause() {
            if (!this.replayer) return;
            if (this.replayer.playing) {
                clearInterval(this.replayer.intervalId);
                this.replayer.intervalId = null;
                this.replayer.playing = false;
            } else {
                // If at end, restart from beginning
                if (this.replayer.stepIndex >= this.replayer.hand.actions.length) {
                    this.replayer.stepIndex = 0;
                }
                this.replayer.playing = true;
                const tick = () => {
                    if (this.replayer.stepIndex >= this.replayer.hand.actions.length) {
                        clearInterval(this.replayer.intervalId);
                        this.replayer.intervalId = null;
                        this.replayer.playing = false;
                        return;
                    }
                    this.replayer.stepIndex++;
                    this._updateReplayState();
                };
                this.replayer.intervalId = setInterval(tick, 1000 / this.replayer.speed);
            }
        },

        replaySetSpeed(speed) {
            if (!this.replayer) return;
            this.replayer.speed = speed;
            // If currently playing, restart interval at new speed
            if (this.replayer.playing && this.replayer.intervalId) {
                clearInterval(this.replayer.intervalId);
                const tick = () => {
                    if (this.replayer.stepIndex >= this.replayer.hand.actions.length) {
                        clearInterval(this.replayer.intervalId);
                        this.replayer.intervalId = null;
                        this.replayer.playing = false;
                        return;
                    }
                    this.replayer.stepIndex++;
                    this._updateReplayState();
                };
                this.replayer.intervalId = setInterval(tick, 1000 / speed);
            }
        },

        _updateReplayState() {
            if (!this.replayer) return;
            this.replayerState = PokerLogic.buildReplayState(
                this.replayer.hand, this.replayer.stepIndex
            );
        },

        // ── Preflop Range Chart ──

        async fetchRanges() {
            if (this.rangeData) {
                this.updateRangeGrid();
                return;
            }
            try {
                const res = await fetch('/api/preflop_ranges');
                this.rangeData = await res.json();
                this.rangePositions = this.rangeData.positions || [];
                if (!this.rangePositions.includes(this.rangePosition)) {
                    this.rangePosition = this.rangePositions[0] || 'BTN';
                }
                this.updateRangeGrid();
            } catch (e) { console.error('Failed to fetch ranges:', e); }
        },

        updateRangeGrid() {
            if (!this.rangeData?.ranges) return;
            this.rangeGrid = this.rangeData.ranges[this.rangePosition] || null;
            this._updateRangeCurrentHand();
        },

        _updateRangeCurrentHand() {
            // Highlight current hand on the range grid
            const humanSeat = this.humanSeat;
            const player = this.state.players?.[humanSeat];
            if (!player?.hole_cards?.length || player.hole_cards.length < 2) {
                this.rangeCurrentHand = null;
                return;
            }
            const c1 = player.hole_cards[0];
            const c2 = player.hole_cards[1];
            if (!c1?.rank_display || !c2?.rank_display) {
                this.rangeCurrentHand = null;
                return;
            }
            // Map T/10 to T for grid lookup
            const r1 = c1.rank_display === '10' ? 'T' : c1.rank_display;
            const r2 = c2.rank_display === '10' ? 'T' : c2.rank_display;
            const suited = c1.suit === c2.suit;
            // Use PokerLogic if available, otherwise manual grid position calc
            const ranks = ['A','K','Q','J','T','9','8','7','6','5','4','3','2'];
            const i1 = ranks.indexOf(r1);
            const i2 = ranks.indexOf(r2);
            if (i1 < 0 || i2 < 0) { this.rangeCurrentHand = null; return; }
            if (i1 === i2) {
                this.rangeCurrentHand = [i1, i2]; // Pair
            } else if (suited) {
                this.rangeCurrentHand = [Math.min(i1, i2), Math.max(i1, i2)]; // Suited above diagonal
            } else {
                this.rangeCurrentHand = [Math.max(i1, i2), Math.min(i1, i2)]; // Offsuit below diagonal
            }
        },

        // ── Tutorial (Scripted 10-Hand Mode) ──

        async startTutorial() {
            try {
                const res = await fetch('/api/tutorial/start', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    this.showSetup = false;
                    this.advisorEnabled = true;
                    this.tutorial.active = true;
                    this.tutorial.complete = false;
                    this.tutorial.handIndex = 0;
                    this.tutorial.intro = data.intro;
                    this.tutorial.showIntro = true;
                    this.tutorial.showOutro = false;
                    this.tutorial.showComplete = false;
                    this.updateState(data.state);
                }
            } catch (e) { console.error('Tutorial start failed:', e); }
        },

        async tutorialDeal() {
            this.tutorial.showIntro = false;
            try {
                const res = await fetch('/api/tutorial/deal', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    this.showdown = null;
                    this.advisor = null;
                    this.aiThinkingSeat = -1;
                    this.updateState(data.state);
                    if (data.guided) {
                        this.tutorial.guided = data.guided;
                    }
                    if (data.tutorial) {
                        this.tutorial.handIndex = data.tutorial.hand_index;
                        this.tutorial.title = data.tutorial.title;
                        this.tutorial.totalHands = data.tutorial.total_hands;
                    }
                    // Fetch advisor for the current state
                    if (this.canAct && this.advisorEnabled) {
                        this.fetchAdvisor();
                    }
                }
            } catch (e) { console.error('Tutorial deal failed:', e); }
        },

        async tutorialNext() {
            this.tutorial.showOutro = false;
            try {
                const res = await fetch('/api/tutorial/next', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    if (data.complete) {
                        this.tutorial.complete = true;
                        this.tutorial.showComplete = true;
                    } else {
                        this.tutorial.intro = data.intro;
                        this.tutorial.showIntro = true;
                        this.tutorial.guided = null;
                        if (data.tutorial) {
                            this.tutorial.handIndex = data.tutorial.hand_index;
                            this.tutorial.title = data.tutorial.title;
                        }
                    }
                }
            } catch (e) { console.error('Tutorial next failed:', e); }
        },

        async tutorialSkip() {
            this.tutorial.active = false;
            this.tutorial.showIntro = false;
            this.tutorial.showOutro = false;
            this.tutorial.showComplete = false;
            this.tutorial.guided = null;
            try {
                await fetch('/api/tutorial/skip', { method: 'POST' });
            } catch (e) {}
            this.showSetup = true;
        },

        // ── Chip Animations ──

        spawnChipToPot(seat, amount) {
            if (!this.chipAnimations) return;
            const seatEl = document.querySelector(`.player-seat[data-seat="${seat}"]`);
            const potEl = document.querySelector('.community-pot');
            const layer = document.querySelector('.chip-animation-layer');
            if (!seatEl || !potEl || !layer) return;

            const seatRect = seatEl.getBoundingClientRect();
            const potRect = potEl.getBoundingClientRect();

            const chip = document.createElement('div');
            chip.className = 'flying-chip';
            chip.textContent = '🪙';
            chip.style.left = (seatRect.left + seatRect.width / 2 - 10) + 'px';
            chip.style.top = (seatRect.top + seatRect.height / 2 - 10) + 'px';

            if (amount > 0) {
                const amtLabel = document.createElement('span');
                amtLabel.className = 'flying-chip-amount';
                amtLabel.textContent = '$' + amount;
                chip.appendChild(amtLabel);
            }

            layer.appendChild(chip);

            // Trigger animation after paint
            requestAnimationFrame(() => {
                chip.style.left = (potRect.left + potRect.width / 2 - 10) + 'px';
                chip.style.top = (potRect.top + potRect.height / 2 - 10) + 'px';
                setTimeout(() => {
                    chip.classList.add('arrived');
                    setTimeout(() => chip.remove(), 200);
                }, 400);
            });
        },

        spawnWinChips(seat, amount) {
            if (!this.chipAnimations) return;
            const seatEl = document.querySelector(`.player-seat[data-seat="${seat}"]`);
            const potEl = document.querySelector('.community-pot');
            const layer = document.querySelector('.chip-animation-layer');
            if (!seatEl || !potEl || !layer) return;

            const potRect = potEl.getBoundingClientRect();
            const seatRect = seatEl.getBoundingClientRect();

            // Spawn 3 chips for visual effect
            for (let i = 0; i < 3; i++) {
                setTimeout(() => {
                    const chip = document.createElement('div');
                    chip.className = 'flying-chip win-chip';
                    chip.textContent = '🪙';
                    chip.style.left = (potRect.left + potRect.width / 2 - 10 + (i - 1) * 8) + 'px';
                    chip.style.top = (potRect.top + potRect.height / 2 - 10) + 'px';

                    if (i === 1) {
                        const amtLabel = document.createElement('span');
                        amtLabel.className = 'flying-chip-amount';
                        amtLabel.textContent = '+$' + amount;
                        chip.appendChild(amtLabel);
                    }

                    layer.appendChild(chip);
                    requestAnimationFrame(() => {
                        chip.style.left = (seatRect.left + seatRect.width / 2 - 10) + 'px';
                        chip.style.top = (seatRect.top + seatRect.height / 2 - 10) + 'px';
                        setTimeout(() => {
                            chip.classList.add('arrived');
                            setTimeout(() => chip.remove(), 200);
                        }, 500);
                    });
                }, i * 80);
            }
        },

        _checkChipAnimations(data) {
            if (!this.chipAnimations || !data.players) return;
            const players = data.players;
            for (const p of players) {
                const prevBet = this._prevPlayerBets[p.seat] || 0;
                if (p.current_bet > prevBet && p.current_bet > 0) {
                    this.spawnChipToPot(p.seat, p.current_bet - prevBet);
                }
            }
            // Update tracking
            this._prevPlayerBets = {};
            for (const p of players) {
                this._prevPlayerBets[p.seat] = p.current_bet;
            }
        },

        // ── Hand History Navigation ──

        get historyList() {
            return PokerLogic.historyList(this.state.hand_histories);
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
                adaptive: p.adaptive || false,
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
