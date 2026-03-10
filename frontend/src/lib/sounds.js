const AUDIO_ENABLED_KEY = 'pokerclaw_sound_enabled';

class SoundManager {
  constructor() {
    this.ctx = null;
    this.enabled = localStorage.getItem(AUDIO_ENABLED_KEY) !== 'false';
  }

  getCtx() {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  toggle() {
    this.enabled = !this.enabled;
    localStorage.setItem(AUDIO_ENABLED_KEY, this.enabled);
    return this.enabled;
  }

  isEnabled() { return this.enabled; }

  tone(freq, duration, type = 'sine', vol = 0.3) {
    if (!this.enabled) return;
    try {
      const ctx = this.getCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = type;
      gain.gain.setValueAtTime(vol, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + duration);
    } catch { /* audio not available */ }
  }

  noise(duration, vol = 0.1) {
    if (!this.enabled) return;
    try {
      const ctx = this.getCtx();
      const bufferSize = ctx.sampleRate * duration;
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * 0.5;
      const src = ctx.createBufferSource();
      const gain = ctx.createGain();
      const filter = ctx.createBiquadFilter();
      filter.type = 'highpass';
      filter.frequency.value = 4000;
      src.buffer = buffer;
      src.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);
      gain.gain.setValueAtTime(vol, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      src.start();
    } catch { /* audio not available */ }
  }

  cardDeal() {
    this.noise(0.06, 0.12);
    this.tone(900, 0.06, 'triangle', 0.15);
    setTimeout(() => this.tone(700, 0.04, 'triangle', 0.1), 25);
  }

  cardFlip() {
    this.noise(0.04, 0.08);
    this.tone(1300, 0.05, 'square', 0.08);
    setTimeout(() => this.tone(1500, 0.04, 'square', 0.06), 15);
  }

  chipClink() {
    this.tone(3200, 0.06, 'sine', 0.12);
    setTimeout(() => this.tone(4000, 0.05, 'sine', 0.08), 30);
    setTimeout(() => this.tone(3500, 0.04, 'sine', 0.06), 60);
  }

  betPlaced() {
    this.tone(1600, 0.1, 'sine', 0.18);
    setTimeout(() => {
      this.tone(2000, 0.08, 'sine', 0.14);
      this.chipClink();
    }, 50);
  }

  fold() {
    this.tone(350, 0.18, 'sine', 0.1);
    setTimeout(() => this.tone(250, 0.22, 'sine', 0.06), 80);
  }

  raise() {
    this.tone(700, 0.06, 'triangle', 0.2);
    setTimeout(() => this.tone(1000, 0.08, 'triangle', 0.18), 40);
    setTimeout(() => this.tone(1200, 0.05, 'triangle', 0.12), 80);
  }

  winFanfare() {
    const notes = [523, 659, 784, 1047];
    notes.forEach((freq, i) => {
      setTimeout(() => this.tone(freq, 0.35, 'sine', 0.22 - i * 0.02), i * 120);
    });
    setTimeout(() => this.tone(1047, 0.5, 'sine', 0.25), 500);
  }

  lose() {
    this.tone(440, 0.2, 'sine', 0.12);
    setTimeout(() => this.tone(370, 0.25, 'sine', 0.1), 120);
    setTimeout(() => this.tone(311, 0.35, 'sine', 0.06), 250);
  }

  notification() {
    this.tone(880, 0.08, 'sine', 0.18);
    setTimeout(() => this.tone(1100, 0.06, 'sine', 0.14), 50);
  }

  // Play action sound based on action type
  actionSound(action) {
    switch (action) {
      case 'fold': this.fold(); break;
      case 'call': this.chipClink(); break;
      case 'raise': this.raise(); break;
      default: break;
    }
  }
}

export const sounds = new SoundManager();
