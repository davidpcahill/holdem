/**
 * Sound effects for Texas Hold'em
 * 
 * All sounds synthesized via Web Audio API — no external files.
 * Toggle on/off. Muted by default.
 */

class PokerSounds {
    constructor() {
        this.enabled = false;
        this.ctx = null;
        this.volume = 0.3;
    }

    _ensureCtx() {
        if (!this.ctx) {
            try {
                this.ctx = new (window.AudioContext || window.webkitAudioContext)();
            } catch (e) {
                return false;
            }
        }
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
        return true;
    }

    toggle() {
        this.enabled = !this.enabled;
        if (this.enabled) this._ensureCtx();
        return this.enabled;
    }

    // Short click for card dealing
    cardDeal() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.04);
        gain.gain.setValueAtTime(this.volume * 0.4, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.06);
    }

    // Chip stacking sound for bets/calls
    chipBet() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        // Multiple short bursts like chips clinking
        for (let i = 0; i < 3; i++) {
            const t = ctx.currentTime + i * 0.03;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const filter = ctx.createBiquadFilter();
            osc.connect(filter);
            filter.connect(gain);
            gain.connect(ctx.destination);
            filter.type = 'highpass';
            filter.frequency.value = 2000;
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(3000 + i * 500, t);
            osc.frequency.exponentialRampToValueAtTime(1000, t + 0.03);
            gain.gain.setValueAtTime(this.volume * 0.25, t);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
            osc.start(t);
            osc.stop(t + 0.05);
        }
    }

    // Soft thud for check
    check() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(200, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(100, ctx.currentTime + 0.08);
        gain.gain.setValueAtTime(this.volume * 0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.1);
    }

    // Fold — soft swish
    fold() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const bufSize = ctx.sampleRate * 0.1;
        const buf = ctx.createBuffer(1, bufSize, ctx.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < bufSize; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / bufSize);
        }
        const source = ctx.createBufferSource();
        const gain = ctx.createGain();
        const filter = ctx.createBiquadFilter();
        source.buffer = buf;
        source.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        filter.type = 'bandpass';
        filter.frequency.value = 4000;
        filter.Q.value = 0.5;
        gain.gain.setValueAtTime(this.volume * 0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
        source.start(ctx.currentTime);
    }

    // Win fanfare — ascending tone
    win() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const notes = [523, 659, 784]; // C5, E5, G5
        notes.forEach((freq, i) => {
            const t = ctx.currentTime + i * 0.12;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, t);
            gain.gain.linearRampToValueAtTime(this.volume * 0.3, t + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.25);
            osc.start(t);
            osc.stop(t + 0.25);
        });
    }

    // Timer tick for pass-and-play countdown
    tick() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = 1000;
        gain.gain.setValueAtTime(this.volume * 0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.05);
    }

    // Street reveal — deeper tone
    streetReveal() {
        if (!this.enabled || !this._ensureCtx()) return;
        const ctx = this.ctx;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(400, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(250, ctx.currentTime + 0.15);
        gain.gain.setValueAtTime(this.volume * 0.25, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.2);
    }
}

// Global singleton
window.pokerSounds = new PokerSounds();
