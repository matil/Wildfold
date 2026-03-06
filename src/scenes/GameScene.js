import Phaser from 'phaser';
import { Player } from '../entities/Player.js';
import { WindSystem } from '../systems/WindSystem.js';
import { WeatherSystem, WeatherState } from '../systems/WeatherSystem.js';
import { LEVELS } from '../levels/LevelData.js';

export class GameScene extends Phaser.Scene {
  constructor() {
    super('Game');
  }

  init(data) {
    this.levelId = data.level || 'garden-1';
  }

  create() {
    const level = LEVELS[this.levelId];
    if (!level) {
      console.error('Level not found:', this.levelId);
      return;
    }

    this.levelData = level;
    this.currentCheckpoint = { x: level.spawnX, y: level.spawnY };

    // --- World bounds ---
    this.physics.world.setBounds(0, 0, level.width, level.height);

    // --- Background parallax layers ---
    this.bgFar = this.add.tileSprite(0, 0, level.width, 1080, 'bg-far')
      .setOrigin(0, 0).setScrollFactor(0.1).setDepth(0);
    this.bgMid = this.add.tileSprite(0, 0, level.width, 1080, 'bg-mid')
      .setOrigin(0, 0).setScrollFactor(0.4).setDepth(1);
    this.bgNear = this.add.tileSprite(0, 0, level.width, 1080, 'bg-near')
      .setOrigin(0, 0).setScrollFactor(0.7).setDepth(2);

    // --- Systems ---
    this.windSystem = new WindSystem(this);
    this.weatherSystem = new WeatherSystem(this);

    // --- Ground & Platforms ---
    this.groundGroup = this.physics.add.staticGroup();
    this.platformGroup = this.physics.add.staticGroup();

    for (const g of level.ground) {
      const tile = this.groundGroup.create(g.x + g.w / 2, g.y + g.h / 2, 'ground');
      tile.setDisplaySize(g.w, g.h);
      tile.refreshBody();
      tile.setDepth(10);
    }

    for (const p of level.platforms) {
      const plat = this.platformGroup.create(p.x + p.w / 2, p.y + 12, 'platform');
      plat.setDisplaySize(p.w, 24);
      plat.refreshBody();
      plat.setDepth(10);
    }

    // --- Water (death zones) ---
    this.waterGroup = this.physics.add.staticGroup();
    this.waterVisuals = [];
    for (const w of level.water) {
      const water = this.waterGroup.create(w.x + w.w / 2, w.y + w.h / 2, 'water');
      water.setDisplaySize(w.w, w.h);
      water.refreshBody();
      water.setDepth(8);
      water.setAlpha(0.7);

      // Animated water surface
      this.tweens.add({
        targets: water,
        alpha: { from: 0.5, to: 0.8 },
        duration: 1500,
        yoyo: true,
        repeat: -1,
      });
    }

    // --- Fire hazards ---
    this.fireGroup = this.physics.add.staticGroup();
    for (const f of level.fires) {
      const fire = this.fireGroup.create(f.x, f.y, 'fire');
      fire.setDepth(12);
      // Flicker
      this.tweens.add({
        targets: fire,
        scaleX: { from: 0.9, to: 1.1 },
        scaleY: { from: 0.9, to: 1.15 },
        duration: 200 + Math.random() * 200,
        yoyo: true,
        repeat: -1,
      });
    }

    // --- Sprinklers ---
    this.sprinklers = [];
    for (const s of level.sprinklers) {
      const spr = this.add.sprite(s.x, s.y, 'sprinkler').setDepth(11);
      const sprayZone = this.add.zone(s.x, s.y - 60, 80, 120);
      this.physics.add.existing(sprayZone, true);

      const timer = this.time.addEvent({
        delay: s.interval,
        loop: true,
        callback: () => {
          // Create water spray particles
          const spray = this.add.particles(s.x, s.y - 20, 'raindrop', {
            speed: { min: 80, max: 150 },
            angle: { min: 230, max: 310 },
            scale: { start: 0.8, end: 0.2 },
            alpha: { start: 0.6, end: 0 },
            lifespan: 800,
            quantity: 15,
            maxParticles: 15,
          });
          spray.setDepth(12);
          // Apply rain effect if player is near
          if (Phaser.Math.Distance.Between(this.player.x, this.player.y, s.x, s.y) < 100) {
            this.player.applyRain(0.3);
          }
          this.time.delayedCall(1000, () => spray.destroy());
        },
      });
      this.sprinklers.push({ sprite: spr, zone: sprayZone, timer });
    }

    // --- Fireflies ---
    this.fireflyGroup = this.physics.add.group();
    for (const ff of level.fireflies) {
      const firefly = this.fireflyGroup.create(ff.x, ff.y, 'firefly');
      firefly.setDepth(15);
      firefly.body.setAllowGravity(false);
      firefly.body.setCircle(8);

      // Floating bob animation
      this.tweens.add({
        targets: firefly,
        y: ff.y + Phaser.Math.Between(-15, -5),
        duration: 1000 + Math.random() * 1000,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });

      // Glow pulse
      this.tweens.add({
        targets: firefly,
        alpha: { from: 0.6, to: 1 },
        duration: 500 + Math.random() * 500,
        yoyo: true,
        repeat: -1,
      });
    }

    // --- Checkpoints ---
    this.checkpointGroup = this.physics.add.staticGroup();
    for (const cp of level.checkpoints) {
      const cpSprite = this.checkpointGroup.create(cp.x, cp.y, 'checkpoint');
      cpSprite.setDepth(5);
      cpSprite.setData('activated', false);
      cpSprite.setAlpha(0.4);
    }

    // --- Exit zone ---
    this.exitZone = this.add.zone(level.exit.x, level.exit.y, level.exit.w, level.exit.h);
    this.physics.add.existing(this.exitZone, true);
    // Exit visual
    const exitGlow = this.add.pointlight(level.exit.x, level.exit.y, 0x44ddff, 60, 0.4, 0.05);
    exitGlow.setDepth(5);
    this.tweens.add({
      targets: exitGlow,
      intensity: { from: 0.3, to: 0.6 },
      radius: { from: 50, to: 80 },
      duration: 1500,
      yoyo: true,
      repeat: -1,
    });

    // --- Wind zones ---
    for (const wz of level.windZones) {
      this.windSystem.addZone(wz.x, wz.y, wz.w, wz.h, wz.dirX, wz.dirY, wz.intensity);
    }

    // --- Weather zones ---
    for (const wz of level.weatherZones) {
      this.weatherSystem.addZone(wz.x, wz.y, wz.w, wz.h, wz.state);
    }

    // --- Player ---
    this.player = new Player(this, level.spawnX, level.spawnY);

    // --- Collisions ---
    this.physics.add.collider(this.player.sprite, this.groundGroup);
    this.physics.add.collider(this.player.sprite, this.platformGroup);

    // Firefly collection
    this.physics.add.overlap(this.player.sprite, this.fireflyGroup, (playerSprite, firefly) => {
      this.collectFirefly(firefly);
    });

    // Water = death (unless boat)
    this.physics.add.overlap(this.player.sprite, this.waterGroup, () => {
      if (this.player.form === 'boat') {
        this.player.isOnWater = true;
      } else {
        this.player.die('water');
      }
    });

    // Fire = instant death
    this.physics.add.overlap(this.player.sprite, this.fireGroup, () => {
      this.player.die('fire');
    });

    // Checkpoints
    this.physics.add.overlap(this.player.sprite, this.checkpointGroup, (playerSprite, cp) => {
      if (!cp.getData('activated')) {
        cp.setData('activated', true);
        cp.setAlpha(1);
        this.currentCheckpoint = { x: cp.x, y: cp.y };
        // Activation effect
        this.tweens.add({
          targets: cp,
          scaleX: 1.5,
          scaleY: 1.5,
          duration: 300,
          yoyo: true,
        });
      }
    });

    // Exit
    this.physics.add.overlap(this.player.sprite, this.exitZone, () => {
      this.levelComplete();
    });

    // --- Camera ---
    this.cameras.main.startFollow(this.player.sprite, true, 0.08, 0.08);
    this.cameras.main.setBounds(0, 0, level.width, level.height);
    this.cameras.main.setDeadzone(100, 50);

    // --- Input ---
    this.cursors = this.input.keyboard.createCursorKeys();
    this.keys = {
      left: this.input.keyboard.addKey('A'),
      right: this.input.keyboard.addKey('D'),
      up: this.input.keyboard.addKey('W'),
      down: this.input.keyboard.addKey('S'),
      jump: this.input.keyboard.addKey('SPACE'),
      transform: this.input.keyboard.addKey('E'),
      revert: this.input.keyboard.addKey('Q'),
    };

    // Combined cursors (arrow keys + WASD)
    this.combinedCursors = {
      left: { get isDown() { return this.scene.cursors.left.isDown || this.scene.keys.left.isDown; }, scene: this },
      right: { get isDown() { return this.scene.cursors.right.isDown || this.scene.keys.right.isDown; }, scene: this },
      up: { get isDown() { return this.scene.cursors.up.isDown || this.scene.keys.up.isDown; }, scene: this },
      down: { get isDown() { return this.scene.cursors.down.isDown || this.scene.keys.down.isDown; }, scene: this },
      space: { get isDown() { return this.scene.cursors.space.isDown || this.scene.keys.jump.isDown; }, scene: this },
    };

    // Transform key
    this.keys.transform.on('down', () => {
      if (this.player.form === 'plane') {
        this.player.transform('boat');
      }
    });
    this.keys.revert.on('down', () => {
      if (this.player.form !== 'plane') {
        this.player.revertToPlane();
      }
    });

    // --- Death handler ---
    this.events.on('player-died', (cause) => {
      this.time.delayedCall(1000, () => {
        this.respawnPlayer();
      });
    });

    // --- Launch HUD ---
    this.scene.launch('HUD', { gameScene: this });

    // Level title display
    this.showLevelTitle(level.name);
  }

  update(time, delta) {
    // Reset boat water status each frame (re-checked by overlap)
    this.player.isOnWater = false;

    // Update systems
    this.windSystem.update(delta, this.player.x, this.player.y);
    this.weatherSystem.update(delta, this.player.x, this.player.y, this.player);

    // Update player
    this.player.update(delta, this.combinedCursors, this.windSystem);

    // Parallax scrolling
    const camX = this.cameras.main.scrollX;
    this.bgFar.tilePositionX = camX * 0.1;
    this.bgMid.tilePositionX = camX * 0.4;
    this.bgNear.tilePositionX = camX * 0.7;

    // Fall death
    if (this.player.y > this.levelData.height + 100) {
      this.player.die('fall');
    }
  }

  collectFirefly(firefly) {
    this.player.collectFirefly();
    firefly.destroy();

    // Collection particles
    const particles = this.add.particles(firefly.x, firefly.y, 'glow-particle', {
      speed: { min: 50, max: 120 },
      scale: { start: 1, end: 0 },
      alpha: { start: 0.8, end: 0 },
      tint: 0xffdd44,
      lifespan: 500,
      quantity: 8,
      maxParticles: 8,
      blendMode: 'ADD',
    });
    particles.setDepth(16);
    this.time.delayedCall(600, () => particles.destroy());

    // Update HUD
    this.events.emit('firefly-collected', this.player.fireflies);
  }

  respawnPlayer() {
    this.player.respawn(this.currentCheckpoint.x, this.currentCheckpoint.y);
    this.cameras.main.flash(300, 0, 0, 0);
  }

  levelComplete() {
    if (this._completing) return;
    this._completing = true;

    // Flash and fade
    this.cameras.main.flash(500, 255, 255, 255);
    this.player.sprite.body.setVelocity(0, 0);
    this.player.sprite.body.setAcceleration(0);

    // Show completion
    const text = this.add.text(this.cameras.main.midPoint.x, this.cameras.main.midPoint.y, 'Level Complete!', {
      fontSize: '48px',
      fontFamily: 'Arial',
      color: '#ffdd44',
      stroke: '#000000',
      strokeThickness: 4,
    }).setOrigin(0.5).setScrollFactor(0).setDepth(200);

    this.tweens.add({
      targets: text,
      scaleX: { from: 0, to: 1 },
      scaleY: { from: 0, to: 1 },
      duration: 500,
      ease: 'Back.easeOut',
    });

    // Return to menu after delay
    this.time.delayedCall(2500, () => {
      this.scene.stop('HUD');
      this.scene.start('Menu');
    });
  }

  showLevelTitle(name) {
    const title = this.add.text(960, 200, name, {
      fontSize: '36px',
      fontFamily: 'Arial',
      color: '#ffffff',
      stroke: '#000000',
      strokeThickness: 3,
    }).setOrigin(0.5).setScrollFactor(0).setDepth(200).setAlpha(0);

    this.tweens.add({
      targets: title,
      alpha: { from: 0, to: 1 },
      y: { from: 200, to: 180 },
      duration: 800,
      hold: 1500,
      yoyo: true,
      onComplete: () => title.destroy(),
    });
  }
}
