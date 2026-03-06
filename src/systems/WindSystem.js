import Phaser from 'phaser';

/**
 * Dynamic wind system.
 * Wind direction and intensity shift over time.
 * Each form has different wind sensitivity.
 */
export class WindSystem {
  constructor(scene) {
    this.scene = scene;

    // Wind state
    this.direction = { x: 0, y: 0 };  // Normalized direction
    this.intensity = 0;                 // 0-1 strength
    this.baseForce = 400;               // Max force in pixels/s²

    // Target values for smooth transitions
    this.targetDir = { x: 0, y: 0 };
    this.targetIntensity = 0;

    // Transition speed
    this.lerpSpeed = 0.02;

    // Auto-change timer
    this.changeTimer = 0;
    this.changeInterval = 4000 + Math.random() * 6000; // 4-10s between shifts

    // Wind sensitivity per form (multiplier)
    this.formSensitivity = {
      plane: 1.0,
      boat: 0.3,
      frog: 0.5,
      crane: 0.15,
    };

    // Particles for visual indicator
    this.particles = null;
    this.setupParticles();

    // Wind zones (override areas)
    this.zones = [];
    this.activeZone = null;
  }

  setupParticles() {
    // Leaf/dust particles showing wind direction
    this.particles = this.scene.add.particles(0, 0, 'glow-particle', {
      x: { min: 0, max: 1920 },
      y: { min: 0, max: 1080 },
      speedX: 0,
      speedY: 0,
      scale: { start: 0.5, end: 0.1 },
      alpha: { start: 0.3, end: 0 },
      tint: [0xccddaa, 0xaacc88, 0xddccaa],
      lifespan: 2000,
      frequency: 200,
      quantity: 1,
      blendMode: 'NORMAL',
    });
    this.particles.setDepth(50);
  }

  /**
   * Add a wind zone (area with fixed wind override)
   */
  addZone(x, y, width, height, dirX, dirY, intensity) {
    this.zones.push({
      rect: new Phaser.Geom.Rectangle(x, y, width, height),
      direction: { x: dirX, y: dirY },
      intensity,
    });
  }

  /**
   * Set wind manually (for scripted events)
   */
  setWind(dirX, dirY, intensity, immediate = false) {
    this.targetDir.x = dirX;
    this.targetDir.y = dirY;
    this.targetIntensity = intensity;

    if (immediate) {
      this.direction.x = dirX;
      this.direction.y = dirY;
      this.intensity = intensity;
    }
  }

  /**
   * Main update
   */
  update(delta, playerX, playerY) {
    const dt = delta / 1000;

    // Check if player is in a wind zone
    this.activeZone = null;
    for (const zone of this.zones) {
      if (zone.rect.contains(playerX, playerY)) {
        this.activeZone = zone;
        break;
      }
    }

    if (this.activeZone) {
      // Override with zone wind
      this.direction.x = Phaser.Math.Linear(this.direction.x, this.activeZone.direction.x, this.lerpSpeed * 3);
      this.direction.y = Phaser.Math.Linear(this.direction.y, this.activeZone.direction.y, this.lerpSpeed * 3);
      this.intensity = Phaser.Math.Linear(this.intensity, this.activeZone.intensity, this.lerpSpeed * 3);
    } else {
      // Auto-shift wind periodically
      this.changeTimer += delta;
      if (this.changeTimer >= this.changeInterval) {
        this.changeTimer = 0;
        this.changeInterval = 4000 + Math.random() * 6000;
        this.randomizeTarget();
      }

      // Smooth lerp to target
      this.direction.x = Phaser.Math.Linear(this.direction.x, this.targetDir.x, this.lerpSpeed);
      this.direction.y = Phaser.Math.Linear(this.direction.y, this.targetDir.y, this.lerpSpeed);
      this.intensity = Phaser.Math.Linear(this.intensity, this.targetIntensity, this.lerpSpeed);
    }

    // Update wind particles
    if (this.particles) {
      const force = this.getForce();
      this.particles.setParticleSpeed(force.x * 0.5, force.y * 0.3);
      this.particles.frequency = Math.max(50, 300 - this.intensity * 250);
    }
  }

  randomizeTarget() {
    // Mostly horizontal wind, occasional updraft/downdraft
    const type = Math.random();
    if (type < 0.3) {
      // Headwind (left)
      this.targetDir = { x: -1, y: 0 };
      this.targetIntensity = 0.3 + Math.random() * 0.4;
    } else if (type < 0.6) {
      // Tailwind (right)
      this.targetDir = { x: 1, y: 0 };
      this.targetIntensity = 0.2 + Math.random() * 0.3;
    } else if (type < 0.75) {
      // Updraft
      this.targetDir = { x: Math.random() * 0.4 - 0.2, y: -1 };
      this.targetIntensity = 0.2 + Math.random() * 0.3;
    } else if (type < 0.85) {
      // Downdraft
      this.targetDir = { x: Math.random() * 0.4 - 0.2, y: 0.8 };
      this.targetIntensity = 0.15 + Math.random() * 0.25;
    } else {
      // Calm
      this.targetDir = { x: 0, y: 0 };
      this.targetIntensity = 0;
    }
  }

  /**
   * Get raw wind force vector (without form sensitivity)
   */
  getForce() {
    return {
      x: this.direction.x * this.intensity * this.baseForce,
      y: this.direction.y * this.intensity * this.baseForce,
    };
  }

  /**
   * Get wind force adjusted for a specific form
   */
  getForceForForm(form) {
    const sensitivity = this.formSensitivity[form] || 1;
    const force = this.getForce();
    return {
      x: force.x * sensitivity,
      y: force.y * sensitivity,
    };
  }

  /**
   * Get wind info for HUD display
   */
  getInfo() {
    return {
      dirX: this.direction.x,
      dirY: this.direction.y,
      intensity: this.intensity,
      angle: Math.atan2(this.direction.y, this.direction.x) * (180 / Math.PI),
    };
  }
}
