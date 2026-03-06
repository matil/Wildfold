import Phaser from 'phaser';

export class MenuScene extends Phaser.Scene {
  constructor() {
    super('Menu');
  }

  create() {
    const w = this.cameras.main.width;
    const h = this.cameras.main.height;

    // Background
    this.add.rectangle(w / 2, h / 2, w, h, 0x0a0a2e);

    // Stars
    for (let i = 0; i < 60; i++) {
      const star = this.add.circle(
        Math.random() * w,
        Math.random() * h * 0.6,
        Math.random() * 2 + 0.5,
        0xffffff,
        Math.random() * 0.5 + 0.2
      );
      this.tweens.add({
        targets: star,
        alpha: { from: star.alpha, to: star.alpha * 0.3 },
        duration: 1000 + Math.random() * 2000,
        yoyo: true,
        repeat: -1,
      });
    }

    // Ground silhouette
    const ground = this.add.graphics();
    ground.fillStyle(0x0d1a0d, 1);
    ground.fillRect(0, h - 120, w, 120);
    ground.fillStyle(0x1a2a1a, 1);
    // Hills
    for (let x = 0; x < w; x += 200) {
      const hh = 60 + Math.random() * 80;
      ground.fillEllipse(x + 100, h - 120, 250, hh * 2);
    }

    // Floating fireflies
    for (let i = 0; i < 15; i++) {
      const ff = this.add.circle(
        200 + Math.random() * (w - 400),
        h - 200 + Math.random() * 100,
        3,
        0xffdd44,
        0.6
      );
      this.tweens.add({
        targets: ff,
        x: ff.x + Phaser.Math.Between(-40, 40),
        y: ff.y + Phaser.Math.Between(-30, 30),
        alpha: { from: 0.3, to: 0.8 },
        duration: 2000 + Math.random() * 2000,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });
    }

    // Title
    const title = this.add.text(w / 2, 200, 'WILDFOLD', {
      fontSize: '72px',
      fontFamily: 'Arial',
      fontStyle: 'bold',
      color: '#f5f5f0',
      stroke: '#2e5a88',
      strokeThickness: 4,
    }).setOrigin(0.5);

    // Subtitle
    this.add.text(w / 2, 270, 'A paper plane\'s journey to the edge of space', {
      fontSize: '18px',
      fontFamily: 'Arial',
      color: '#8899aa',
    }).setOrigin(0.5);

    // Gentle float on title
    this.tweens.add({
      targets: title,
      y: { from: 200, to: 210 },
      duration: 3000,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });

    // --- Level select buttons ---
    const levels = [
      { id: 'garden-1', label: 'Level 1: First Steps' },
      { id: 'garden-2', label: 'Level 2: Wind Whispers' },
      { id: 'garden-3', label: 'Level 3: Paper Boat' },
    ];

    levels.forEach((lvl, i) => {
      const y = 420 + i * 70;
      const btn = this.add.rectangle(w / 2, y, 320, 50, 0x1a2a4a, 0.8)
        .setInteractive({ useHandCursor: true })
        .setStrokeStyle(2, 0x2e5a88);

      const label = this.add.text(w / 2, y, lvl.label, {
        fontSize: '20px',
        fontFamily: 'Arial',
        color: '#ccddee',
      }).setOrigin(0.5);

      btn.on('pointerover', () => {
        btn.setFillStyle(0x2e5a88, 0.9);
        label.setColor('#ffffff');
      });
      btn.on('pointerout', () => {
        btn.setFillStyle(0x1a2a4a, 0.8);
        label.setColor('#ccddee');
      });
      btn.on('pointerdown', () => {
        this.cameras.main.fadeOut(500, 0, 0, 0);
        this.time.delayedCall(500, () => {
          this.scene.start('Game', { level: lvl.id });
        });
      });
    });

    // Controls hint
    this.add.text(w / 2, h - 60, 'WASD / Arrows: Move   |   Space: Jump / Glide   |   E: Transform   |   Q: Revert', {
      fontSize: '14px',
      fontFamily: 'Arial',
      color: '#556677',
    }).setOrigin(0.5);

    // Version
    this.add.text(w - 20, h - 20, 'v0.1.0 - Prototype', {
      fontSize: '12px',
      fontFamily: 'Arial',
      color: '#334455',
    }).setOrigin(1, 1);

    // Fade in
    this.cameras.main.fadeIn(500);
  }
}
