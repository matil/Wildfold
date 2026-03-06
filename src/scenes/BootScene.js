import Phaser from 'phaser';

export class BootScene extends Phaser.Scene {
  constructor() {
    super('Boot');
  }

  preload() {
    // Show loading progress
    const w = this.cameras.main.width;
    const h = this.cameras.main.height;
    const bar = this.add.rectangle(w / 2, h / 2, 400, 30, 0x2e5a88);
    const fill = this.add.rectangle(w / 2 - 198, h / 2, 0, 26, 0x6eb5ff);
    fill.setOrigin(0, 0.5);

    this.load.on('progress', (val) => {
      fill.width = 396 * val;
    });

    // Try loading real assets (will gracefully fail to placeholders)
    // this.load.image('bg-far', 'assets/backgrounds/garden-far.png');
  }

  create() {
    this.generatePlaceholders();
    this.scene.start('Menu');
  }

  generatePlaceholders() {
    // --- PAPER PLANE ---
    const planeGfx = this.make.graphics({ x: 0, y: 0, add: false });
    planeGfx.fillStyle(0xf5f5f0, 1); // Off-white paper
    planeGfx.lineStyle(2, 0xccccbb, 1);
    // Paper plane shape (side view)
    planeGfx.beginPath();
    planeGfx.moveTo(0, 24);    // nose
    planeGfx.lineTo(56, 12);   // top wing tip
    planeGfx.lineTo(48, 24);   // wing fold
    planeGfx.lineTo(56, 32);   // bottom wing
    planeGfx.lineTo(0, 24);    // back to nose
    planeGfx.closePath();
    planeGfx.fillPath();
    planeGfx.strokePath();
    // Fold crease line
    planeGfx.lineStyle(1, 0xddddcc, 0.8);
    planeGfx.lineBetween(0, 24, 48, 24);
    planeGfx.generateTexture('plane', 64, 48);
    planeGfx.destroy();

    // --- BOAT ---
    const boatGfx = this.make.graphics({ x: 0, y: 0, add: false });
    boatGfx.fillStyle(0xf5f5f0, 1);
    boatGfx.lineStyle(2, 0xccccbb, 1);
    boatGfx.beginPath();
    boatGfx.moveTo(8, 0);     // left top
    boatGfx.lineTo(56, 0);    // right top
    boatGfx.lineTo(48, 28);   // right bottom
    boatGfx.lineTo(16, 28);   // left bottom
    boatGfx.closePath();
    boatGfx.fillPath();
    boatGfx.strokePath();
    // Fold lines
    boatGfx.lineStyle(1, 0xddddcc, 0.8);
    boatGfx.lineBetween(32, 0, 32, 28);
    boatGfx.generateTexture('boat', 64, 32);
    boatGfx.destroy();

    // --- FIREFLY ---
    const flyGfx = this.make.graphics({ x: 0, y: 0, add: false });
    flyGfx.fillStyle(0xffdd44, 1);
    flyGfx.fillCircle(8, 8, 4);
    flyGfx.fillStyle(0xffff88, 0.5);
    flyGfx.fillCircle(8, 8, 8);
    flyGfx.generateTexture('firefly', 16, 16);
    flyGfx.destroy();

    // --- GLOW PARTICLE ---
    const glowGfx = this.make.graphics({ x: 0, y: 0, add: false });
    glowGfx.fillStyle(0xffeeaa, 0.6);
    glowGfx.fillCircle(4, 4, 4);
    glowGfx.generateTexture('glow-particle', 8, 8);
    glowGfx.destroy();

    // --- GROUND TILE ---
    const groundGfx = this.make.graphics({ x: 0, y: 0, add: false });
    groundGfx.fillStyle(0x3d2b1f, 1); // Dark earth
    groundGfx.fillRect(0, 0, 64, 64);
    groundGfx.fillStyle(0x4a7c3f, 1); // Grass top
    groundGfx.fillRect(0, 0, 64, 16);
    groundGfx.lineStyle(1, 0x5a9c4f, 0.6);
    // Grass blades
    for (let i = 4; i < 64; i += 8) {
      groundGfx.lineBetween(i, 16, i - 2, 4);
      groundGfx.lineBetween(i, 16, i + 3, 6);
    }
    groundGfx.generateTexture('ground', 64, 64);
    groundGfx.destroy();

    // --- PLATFORM (floating) ---
    const platGfx = this.make.graphics({ x: 0, y: 0, add: false });
    platGfx.fillStyle(0x6b4226, 1);
    platGfx.fillRoundedRect(0, 4, 128, 20, 4);
    platGfx.fillStyle(0x4a7c3f, 1);
    platGfx.fillRoundedRect(0, 0, 128, 12, 4);
    platGfx.generateTexture('platform', 128, 24);
    platGfx.destroy();

    // --- WATER ---
    const waterGfx = this.make.graphics({ x: 0, y: 0, add: false });
    waterGfx.fillStyle(0x1a6baa, 0.8);
    waterGfx.fillRect(0, 0, 64, 64);
    waterGfx.fillStyle(0x2a8bca, 0.4);
    waterGfx.fillRect(0, 0, 64, 8);
    waterGfx.generateTexture('water', 64, 64);
    waterGfx.destroy();

    // --- FIRE HAZARD ---
    const fireGfx = this.make.graphics({ x: 0, y: 0, add: false });
    fireGfx.fillStyle(0xff4400, 1);
    fireGfx.fillTriangle(16, 0, 0, 32, 32, 32);
    fireGfx.fillStyle(0xffaa00, 1);
    fireGfx.fillTriangle(16, 8, 6, 32, 26, 32);
    fireGfx.generateTexture('fire', 32, 32);
    fireGfx.destroy();

    // --- BACKGROUND LAYERS (placeholder gradients) ---
    // Far: night sky
    const skyGfx = this.make.graphics({ x: 0, y: 0, add: false });
    skyGfx.fillGradientStyle(0x0a0a2e, 0x0a0a2e, 0x1a1a4e, 0x1a1a4e);
    skyGfx.fillRect(0, 0, 1920, 1080);
    // Stars
    for (let i = 0; i < 80; i++) {
      const sx = Math.random() * 1920;
      const sy = Math.random() * 600;
      const size = Math.random() * 2 + 1;
      skyGfx.fillStyle(0xffffff, Math.random() * 0.5 + 0.3);
      skyGfx.fillCircle(sx, sy, size);
    }
    skyGfx.generateTexture('bg-far', 1920, 1080);
    skyGfx.destroy();

    // Mid: garden silhouette
    const midGfx = this.make.graphics({ x: 0, y: 0, add: false });
    midGfx.fillStyle(0x1a3a1a, 0.8);
    // Bush silhouettes
    for (let x = 0; x < 3840; x += 200) {
      const h = 80 + Math.random() * 120;
      midGfx.fillEllipse(x + 100, 1080 - h / 2, 180 + Math.random() * 60, h);
    }
    // Tree silhouettes
    midGfx.fillStyle(0x0d2a0d, 0.9);
    midGfx.fillRect(400, 700, 30, 200);
    midGfx.fillEllipse(415, 680, 160, 180);
    midGfx.fillRect(1600, 650, 40, 250);
    midGfx.fillEllipse(1620, 620, 200, 200);
    midGfx.fillRect(2800, 720, 25, 180);
    midGfx.fillEllipse(2812, 700, 140, 160);
    midGfx.generateTexture('bg-mid', 3840, 1080);
    midGfx.destroy();

    // Near: foreground grass
    const nearGfx = this.make.graphics({ x: 0, y: 0, add: false });
    nearGfx.fillStyle(0x2d5a1e, 0.6);
    for (let x = 0; x < 3840; x += 40) {
      const h = 30 + Math.random() * 50;
      nearGfx.fillTriangle(x, 1080, x + 20, 1080 - h, x + 40, 1080);
    }
    nearGfx.generateTexture('bg-near', 3840, 1080);
    nearGfx.destroy();

    // --- WIND ARROW (HUD) ---
    const arrowGfx = this.make.graphics({ x: 0, y: 0, add: false });
    arrowGfx.fillStyle(0xffffff, 0.7);
    arrowGfx.fillTriangle(32, 8, 0, 16, 0, 0);
    arrowGfx.fillRect(0, 6, 20, 4);
    arrowGfx.generateTexture('wind-arrow', 32, 16);
    arrowGfx.destroy();

    // --- RAINDROP ---
    const rainGfx = this.make.graphics({ x: 0, y: 0, add: false });
    rainGfx.fillStyle(0x6699cc, 0.6);
    rainGfx.fillEllipse(2, 4, 3, 6);
    rainGfx.generateTexture('raindrop', 4, 8);
    rainGfx.destroy();

    // --- CAT ENEMY ---
    const catGfx = this.make.graphics({ x: 0, y: 0, add: false });
    catGfx.fillStyle(0x8B6914, 1);
    // Body
    catGfx.fillEllipse(48, 52, 64, 40);
    // Head
    catGfx.fillCircle(16, 36, 20);
    // Ears
    catGfx.fillTriangle(4, 20, 12, 4, 20, 20);
    catGfx.fillTriangle(16, 20, 24, 4, 32, 20);
    // Tail
    catGfx.lineStyle(4, 0x8B6914, 1);
    catGfx.beginPath();
    catGfx.moveTo(80, 44);
    catGfx.lineTo(92, 30);
    catGfx.lineTo(96, 38);
    catGfx.strokePath();
    // Eyes
    catGfx.fillStyle(0x44ff44, 1);
    catGfx.fillCircle(10, 34, 3);
    catGfx.fillCircle(22, 34, 3);
    catGfx.fillStyle(0x000000, 1);
    catGfx.fillCircle(10, 34, 1.5);
    catGfx.fillCircle(22, 34, 1.5);
    catGfx.generateTexture('cat', 100, 72);
    catGfx.destroy();

    // --- SPRINKLER ---
    const sprinkGfx = this.make.graphics({ x: 0, y: 0, add: false });
    sprinkGfx.fillStyle(0x888888, 1);
    sprinkGfx.fillRect(12, 16, 8, 24);
    sprinkGfx.fillStyle(0xaaaaaa, 1);
    sprinkGfx.fillEllipse(16, 12, 24, 8);
    sprinkGfx.generateTexture('sprinkler', 32, 40);
    sprinkGfx.destroy();

    // --- CHECKPOINT ---
    const cpGfx = this.make.graphics({ x: 0, y: 0, add: false });
    cpGfx.fillStyle(0xffdd44, 0.3);
    cpGfx.fillCircle(16, 16, 16);
    cpGfx.fillStyle(0xffdd44, 0.6);
    cpGfx.fillCircle(16, 16, 8);
    cpGfx.generateTexture('checkpoint', 32, 32);
    cpGfx.destroy();
  }
}
