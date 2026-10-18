const AUDIO_ENABLED_KEY = 'pokerclaw_sound_enabled';

const SOUND_FILES = {
  cardDeal: '/assets/sfx/card-deal.mp3',
  cardFlip: '/assets/sfx/card-flip.mp3',
  chipClink: '/assets/sfx/chip-clink.mp3',
  betPlaced: '/assets/sfx/bet-placed.mp3',
  fold: '/assets/sfx/fold.mp3',
  raise: '/assets/sfx/raise.mp3',
  check: '/assets/sfx/check.mp3',
  winFanfare: '/assets/sfx/win-fanfare.mp3',
  lose: '/assets/sfx/lose.mp3',
  notification: '/assets/sfx/notification.mp3',
};

const SOUND_VOLUMES = {
  cardDeal: 0.58,
  cardFlip: 0.56,
  chipClink: 0.5,
  betPlaced: 0.58,
  fold: 0.48,
  raise: 0.62,
  check: 0.46,
  winFanfare: 0.68,
  lose: 0.48,
  notification: 0.44,
};

class SoundManager {
  constructor() {
    this.enabled = localStorage.getItem(AUDIO_ENABLED_KEY) !== 'false';
    this.samples = {};

    if (typeof Audio !== 'undefined') {
      Object.entries(SOUND_FILES).forEach(([name, src]) => {
        const sample = new Audio(src);
        sample.preload = 'auto';
        this.samples[name] = sample;
      });
    }
  }

  toggle() {
    this.enabled = !this.enabled;
    localStorage.setItem(AUDIO_ENABLED_KEY, this.enabled);
    return this.enabled;
  }

  isEnabled() { return this.enabled; }

  play(name) {
    if (!this.enabled || !this.samples[name]) return;

    try {
      // A fresh voice allows rapid chip/card sounds to overlap naturally.
      const voice = this.samples[name].cloneNode();
      voice.volume = SOUND_VOLUMES[name] ?? 0.55;
      voice.play().catch(() => { /* browser autoplay policy or audio unavailable */ });
    } catch { /* audio unavailable */ }
  }

  cardDeal() { this.play('cardDeal'); }

  cardFlip() { this.play('cardFlip'); }

  chipClink() { this.play('chipClink'); }

  betPlaced() { this.play('betPlaced'); }

  fold() { this.play('fold'); }

  raise() { this.play('raise'); }

  check() { this.play('check'); }

  winFanfare() { this.play('winFanfare'); }

  lose() { this.play('lose'); }

  notification() { this.play('notification'); }

  actionSound(action) {
    switch (action) {
      case 'fold': this.fold(); break;
      case 'call': this.chipClink(); break;
      case 'bet': this.betPlaced(); break;
      case 'raise':
      case 'all-in':
      case 'all_in': this.raise(); break;
      case 'check': this.check(); break;
      default: break;
    }
  }
}

export const sounds = new SoundManager();
