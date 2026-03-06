import Phaser from 'phaser';

/**
 * Player states for the paper plane
 */
const State = {
  GROUNDED: 'grounded',
  AIRBORNE: 'airborne',
  GLIDING: 'gliding',
  TRANSFORMING: 'transforming',
  DEAD: 'dead',
};

const Form = {
  PLANE: 'plane',
  BOAT: 'boat',
};

export class Player {
  constructor(scene, x, y) {
    this.scene = scene;
    this.state = State.AIRBORNE;
    this.form = Form.PLANE;
    this.facing = 1; // 1 = right, -1 = left

    // --- Sprite setup ---
    this.sprite = scene.physics.add.sprite(x, y, 'plane');
    this.sprite.setCollideWorldBounds(true);
    this.sprite.body.setSize(48, 24);
    this.sprite.body.setOffset(8, 12);
    this.sprite.setDepth(100);

    // --- Movement tuning ---
    this.config = {
      // Ground movement
      groundSpeed: 280,
      groundAccel: 1200,
      groundDrag: 800,
      groundFriction: 0.92,

      // Air movement
      airSpeed: 320,
      airAccel: 600,
      airDrag: 200,

      // Jump / Glide
      jumpForce: -380,
      glideGravity: 150,    // Reduced gravity when gliding
      normalGravity: 600,
      glideDrag: 0.995,      // Horizontal drag while gliding
      maxFallSpeed: 500,
      glideMaxFall: 120,    // Max fall speed when gliding (floaty)

      // Boat
      boatSpeed: 200,
      boatBuoyancy: -100,   // Slight upward force on water surface
    };

    // --- State tracking ---
    this.isGliding = false;
    this.canJump = false;
    this.wetness = 0;         // 0-1, increases in rain, decreases in sun
    this.transformTimer = 0;
    this.transformDuration = 0;
    this.fireflies = 0;
    this.isOnWater = false;
    this.isDead = false;
    this.invulnerable = false;
    this.invulnerableTimer = 0;

    // Firefly glow effect
    this.glow = scene.add.pointlight(x, y, 0xffdd44, 30, 0.3, 0.05);
    this.glow.setDepth(99);

    // Wind particle trail
    this.trail = scene.add.particles(0, 0, 'glow-particle', {
      follow: this.sprite,
      followOffset: { x: -20 * this.facing, y: 0 },
      speed: { min: 10, max: 30 },
      scale: { start: 0.8, end: 0 },
      alpha: { start: 0.4, end: 0 },
      lifespan: 400,
      frequency: 80,
      blendMode: 'ADD',
      quantity: 1,
    });
    this.trail.setDepth(98);
  }

  /**
   * Main update loop
   */
  update(delta, cursors, windSystem) {
    if (this.isDead) return;

    const dt = delta / 1000;
    const body = this.sprite.body;
    const onGround = body.blocked.down || body.touching.down;

    // Update invulnerability
    if (this.invulnerable) {
      this.invulnerableTimer -= delta;
      this.sprite.setAlpha(Math.sin(Date.now() / 50) > 0 ? 1 : 0.4);
      if (this.invulnerableTimer <= 0) {
        this.invulnerable = false;
        this.sprite.setAlpha(1);
      }
    }

    // Update transform timer
    if (this.form !== Form.PLANE && this.transformTimer > 0) {
      this.transformTimer -= delta;
      if (this.transformTimer <= 0) {
        this.revertToPlane();
      }
    }

    // State transitions
    if (onGround && this.state === State.AIRBORNE) {
      this.state = State.GROUNDED;
      this.isGliding = false;
    } else if (!onGround && this.state === State.GROUNDED) {
      this.state = State.AIRBORNE;
    }

    this.canJump = onGround;

    // Apply wetness effect
    const wetMult = 1 - (this.wetness * 0.35); // Up to 35% slower when fully wet

    // Handle input based on state/form
    if (this.form === Form.BOAT && this.isOnWater) {
      this.updateBoatMovement(cursors, windSystem, wetMult);
    } else if (this.state === State.GROUNDED) {
      this.updateGroundMovement(cursors, windSystem, wetMult);
    } else {
      this.updateAirMovement(cursors, windSystem, wetMult);
    }

    // Apply wind force
    if (windSystem) {
      const windForce = windSystem.getForceForForm(this.form);
      body.velocity.x += windForce.x * dt;
      body.velocity.y += windForce.y * dt;
    }

    // Clamp fall speed
    const maxFall = this.isGliding
      ? this.config.glideMaxFall * wetMult
      : this.config.maxFallSpeed;
    if (body.velocity.y > maxFall) {
      body.velocity.y = maxFall;
    }

    // Update sprite flip based on facing
    this.sprite.setFlipX(this.facing === -1);

    // Update sprite rotation for visual flair
    if (this.state === State.AIRBORNE && this.form === Form.PLANE) {
      const targetAngle = Phaser.Math.Clamp(body.velocity.y / 8, -25, 35);
      this.sprite.angle = Phaser.Math.Linear(this.sprite.angle, targetAngle * this.facing, 0.1);
    } else {
      this.sprite.angle = Phaser.Math.Linear(this.sprite.angle, 0, 0.2);
    }

    // Update glow position
    this.glow.x = this.sprite.x;
    this.glow.y = this.sprite.y;

    // Glow brightness based on fireflies and transform timer
    if (this.form !== Form.PLANE && this.transformDuration > 0) {
      const pct = this.transformTimer / this.transformDuration;
      this.glow.intensity = 0.1 + pct * 0.4;
      this.glow.radius = 20 + pct * 30;
    } else {
      this.glow.intensity = 0.2 + Math.sin(Date.now() / 500) * 0.05;
      this.glow.radius = 30;
    }
  }

  updateGroundMovement(cursors, windSystem, wetMult) {
    const body = this.sprite.body;
    const cfg = this.config;

    if (cursors.left.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, -cfg.groundSpeed * wetMult, 0.15);
      this.facing = -1;
    } else if (cursors.right.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, cfg.groundSpeed * wetMult, 0.15);
      this.facing = 1;
    } else {
      body.velocity.x *= cfg.groundFriction;
      if (Math.abs(body.velocity.x) < 10) body.velocity.x = 0;
    }

    // Jump
    if (cursors.space.isDown && this.canJump) {
      body.velocity.y = cfg.jumpForce * wetMult;
      this.state = State.AIRBORNE;
      this.canJump = false;
    }
  }

  updateAirMovement(cursors, windSystem, wetMult) {
    const body = this.sprite.body;
    const cfg = this.config;

    // Horizontal movement (less control in air)
    if (cursors.left.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, -cfg.airSpeed * wetMult, 0.08);
      this.facing = -1;
    } else if (cursors.right.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, cfg.airSpeed * wetMult, 0.08);
      this.facing = 1;
    } else {
      body.velocity.x *= 0.99; // Slight air drag
    }

    // Glide (hold space in air)
    if (cursors.space.isDown && body.velocity.y > 0) {
      this.isGliding = true;
      // Reduce gravity for floaty glide
      body.setGravityY(cfg.glideGravity - cfg.normalGravity);
      // Maintain some horizontal momentum
      body.velocity.x *= cfg.glideDrag;
      this.trail.frequency = 40; // More particles when gliding
    } else {
      this.isGliding = false;
      body.setGravityY(0); // Use scene default gravity
      this.trail.frequency = 120;
    }
  }

  updateBoatMovement(cursors, windSystem, wetMult) {
    const body = this.sprite.body;
    const cfg = this.config;

    // Boat floats on water surface
    body.setGravityY(cfg.boatBuoyancy - cfg.normalGravity);

    if (cursors.left.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, -cfg.boatSpeed, 0.1);
      this.facing = -1;
    } else if (cursors.right.isDown) {
      body.velocity.x = Phaser.Math.Linear(body.velocity.x, cfg.boatSpeed, 0.1);
      this.facing = 1;
    } else {
      body.velocity.x *= 0.95;
    }

    // Slight bobbing
    body.velocity.y += Math.sin(Date.now() / 300) * 0.5;
  }

  // --- TRANSFORMATION ---

  transform(targetForm) {
    if (this.form === targetForm) return false;
    if (this.state === State.TRANSFORMING) return false;

    const costs = { [Form.BOAT]: 5 };
    const cost = costs[targetForm] || 5;

    if (this.fireflies < cost) return false;

    this.fireflies -= cost;

    // Duration scales with extra fireflies (base 8s + 1s per extra firefly up to 15s)
    this.transformDuration = 8000 + Math.min(this.fireflies, 7) * 1000;
    this.transformTimer = this.transformDuration;

    this.form = targetForm;
    this.sprite.setTexture(targetForm);

    // Brief invulnerability during transform
    this.invulnerable = true;
    this.invulnerableTimer = 500;

    // Flash effect
    this.scene.cameras.main.flash(200, 255, 220, 100);

    // Resize hitbox per form
    if (targetForm === Form.BOAT) {
      this.sprite.body.setSize(48, 20);
      this.sprite.body.setOffset(8, 6);
    }

    return true;
  }

  revertToPlane() {
    this.form = Form.PLANE;
    this.sprite.setTexture('plane');
    this.sprite.body.setSize(48, 24);
    this.sprite.body.setOffset(8, 12);
    this.transformTimer = 0;
    this.transformDuration = 0;

    // Brief invulnerability
    this.invulnerable = true;
    this.invulnerableTimer = 500;
  }

  // --- FIREFLY COLLECTION ---

  collectFirefly() {
    this.fireflies++;
    // Pulse glow
    this.scene.tweens.add({
      targets: this.glow,
      intensity: 0.6,
      radius: 50,
      duration: 200,
      yoyo: true,
    });
  }

  // --- DAMAGE & DEATH ---

  die(cause) {
    if (this.isDead || this.invulnerable) return;
    this.isDead = true;
    this.state = State.DEAD;

    this.sprite.body.setVelocity(0, 0);
    this.sprite.body.setAcceleration(0, 0);
    this.sprite.body.setGravityY(-600); // Float up briefly

    // Paper crumple effect
    this.scene.tweens.add({
      targets: this.sprite,
      scaleX: 0.3,
      scaleY: 0.3,
      angle: 720,
      alpha: 0,
      duration: 800,
      ease: 'Power2',
      onComplete: () => {
        this.scene.events.emit('player-died', cause);
      },
    });

    // Fade glow
    this.scene.tweens.add({
      targets: this.glow,
      intensity: 0,
      duration: 600,
    });

    this.trail.stop();
  }

  respawn(x, y) {
    this.isDead = false;
    this.state = State.AIRBORNE;
    this.form = Form.PLANE;
    this.sprite.setTexture('plane');
    this.sprite.setPosition(x, y);
    this.sprite.setScale(1);
    this.sprite.setAlpha(1);
    this.sprite.setAngle(0);
    this.sprite.body.setVelocity(0, 0);
    this.sprite.body.setGravityY(0);
    this.sprite.body.setSize(48, 24);
    this.sprite.body.setOffset(8, 12);
    this.glow.intensity = 0.3;
    this.trail.start();
    this.invulnerable = true;
    this.invulnerableTimer = 1500;
  }

  // --- WEATHER ---

  applyRain(dt) {
    this.wetness = Math.min(1, this.wetness + dt * 0.15);
  }

  applySun(dt) {
    this.wetness = Math.max(0, this.wetness - dt * 0.3);
  }

  // --- GETTERS ---

  get x() { return this.sprite.x; }
  get y() { return this.sprite.y; }
  get body() { return this.sprite.body; }
}
