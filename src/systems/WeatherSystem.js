import Phaser from 'phaser';

const WeatherState = {
  CLEAR: 'clear',
  OVERCAST: 'overcast',
  RAIN: 'rain',
  SUN: 'sun',
};

export class WeatherSystem {
  constructor(scene) {
    this.scene = scene;
    this.state = WeatherState.CLEAR;
    this.targetState = WeatherState.CLEAR;
    this.transition = 0; // 0-1 transition progress

    // Rain particles
    this.rainEmitter = scene.add.particles(0, 0, 'raindrop', {
      x: { min: -100, max: 2020 },
      y: -20,
      speedY: { min: 400, max: 600 },
      speedX: { min: -30, max: -60 },
      scale: { start: 1, end: 0.5 },
      alpha: { start: 0.6, end: 0.2 },
      lifespan: 2000,
      frequency: -1, // Manual control
      quantity: 0,
    });
    this.rainEmitter.setDepth(150);

    // Darkness overlay for rain
    this.overlay = scene.add.rectangle(960, 540, 1920, 1080, 0x000022, 0);
    this.overlay.setDepth(140);
    this.overlay.setScrollFactor(0);

    // Sun glow overlay
    this.sunOverlay = scene.add.rectangle(960, 540, 1920, 1080, 0xffeeaa, 0);
    this.sunOverlay.setDepth(140);
    this.sunOverlay.setScrollFactor(0);

    // Weather zones (trigger areas)
    this.zones = [];
    this.activeZone = null;

    // Auto-change timer
    this.changeTimer = 0;
    this.changeInterval = 15000 + Math.random() * 20000; // 15-35s
  }

  /**
   * Add a weather zone
   */
  addZone(x, y, width, height, weatherState) {
    this.zones.push({
      rect: new Phaser.Geom.Rectangle(x, y, width, height),
      state: weatherState,
    });
  }

  /**
   * Force weather change
   */
  setWeather(state, immediate = false) {
    this.targetState = state;
    if (immediate) {
      this.state = state;
      this.transition = 1;
      this.applyVisuals();
    }
  }

  update(delta, playerX, playerY, player) {
    const dt = delta / 1000;

    // Check weather zones
    let zoneWeather = null;
    for (const zone of this.zones) {
      if (zone.rect.contains(playerX, playerY)) {
        zoneWeather = zone.state;
        break;
      }
    }

    if (zoneWeather) {
      this.targetState = zoneWeather;
    } else {
      // Auto-cycle (for dynamic weather outside zones)
      this.changeTimer += delta;
      if (this.changeTimer >= this.changeInterval) {
        this.changeTimer = 0;
        this.changeInterval = 15000 + Math.random() * 20000;
        this.randomizeWeather();
      }
    }

    // Transition to target state
    if (this.state !== this.targetState) {
      this.transition -= dt * 0.5; // Fade out current
      if (this.transition <= 0) {
        this.state = this.targetState;
        this.transition = 0;
      }
    } else if (this.transition < 1) {
      this.transition = Math.min(1, this.transition + dt * 0.5); // Fade in new
    }

    // Apply effects to player
    if (player && !player.isDead) {
      if (this.state === WeatherState.RAIN && this.transition > 0.5) {
        player.applyRain(dt);
      } else if (this.state === WeatherState.SUN && this.transition > 0.5) {
        player.applySun(dt);
      }
    }

    // Update visuals
    this.applyVisuals();
  }

  applyVisuals() {
    const t = this.transition;

    switch (this.state) {
      case WeatherState.RAIN:
        this.rainEmitter.frequency = Phaser.Math.Linear(200, 20, t);
        this.rainEmitter.quantity = Math.floor(Phaser.Math.Linear(0, 8, t));
        this.overlay.setAlpha(t * 0.15);
        this.sunOverlay.setAlpha(0);
        break;

      case WeatherState.SUN:
        this.rainEmitter.frequency = -1;
        this.rainEmitter.quantity = 0;
        this.overlay.setAlpha(0);
        this.sunOverlay.setAlpha(t * 0.08);
        break;

      case WeatherState.OVERCAST:
        this.rainEmitter.frequency = -1;
        this.rainEmitter.quantity = 0;
        this.overlay.setAlpha(t * 0.08);
        this.sunOverlay.setAlpha(0);
        break;

      case WeatherState.CLEAR:
      default:
        this.rainEmitter.frequency = -1;
        this.rainEmitter.quantity = 0;
        this.overlay.setAlpha(0);
        this.sunOverlay.setAlpha(0);
        break;
    }
  }

  randomizeWeather() {
    const r = Math.random();
    if (r < 0.3) {
      this.targetState = WeatherState.RAIN;
    } else if (r < 0.5) {
      this.targetState = WeatherState.SUN;
    } else if (r < 0.7) {
      this.targetState = WeatherState.OVERCAST;
    } else {
      this.targetState = WeatherState.CLEAR;
    }
  }

  getState() {
    return this.state;
  }

  isRaining() {
    return this.state === WeatherState.RAIN && this.transition > 0.5;
  }

  isSunny() {
    return this.state === WeatherState.SUN && this.transition > 0.5;
  }
}

export { WeatherState };
