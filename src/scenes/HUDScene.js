import Phaser from 'phaser';

export class HUDScene extends Phaser.Scene {
  constructor() {
    super('HUD');
  }

  init(data) {
    this.gameScene = data.gameScene;
  }

  create() {
    // --- Firefly counter (top-left) ---
    this.fireflyIcon = this.add.image(40, 40, 'firefly').setScale(2);
    this.fireflyText = this.add.text(65, 30, '0', {
      fontSize: '24px',
      fontFamily: 'Arial',
      color: '#ffdd44',
      stroke: '#000000',
      strokeThickness: 3,
    });

    // --- Transform timer (below firefly) ---
    this.transformBg = this.add.circle(40, 100, 22, 0x000000, 0.4);
    this.transformArc = this.add.graphics();
    this.transformText = this.add.text(40, 100, '', {
      fontSize: '14px',
      fontFamily: 'Arial',
      color: '#ffffff',
    }).setOrigin(0.5);
    this.transformBg.setVisible(false);
    this.transformText.setVisible(false);

    // --- Wind indicator (top-right) ---
    this.windArrow = this.add.image(1860, 40, 'wind-arrow').setScale(1.5);
    this.windArrow.setAlpha(0);
    this.windText = this.add.text(1860, 60, '', {
      fontSize: '12px',
      fontFamily: 'Arial',
      color: '#aabbcc',
    }).setOrigin(0.5);

    // --- Weather indicator (top-center) ---
    this.weatherText = this.add.text(960, 20, '', {
      fontSize: '16px',
      fontFamily: 'Arial',
      color: '#ffffff',
      stroke: '#000000',
      strokeThickness: 2,
    }).setOrigin(0.5).setAlpha(0.6);

    // --- Wetness bar (below firefly counter) ---
    this.wetBg = this.add.rectangle(40, 150, 60, 8, 0x333333, 0.5);
    this.wetFill = this.add.rectangle(11, 150, 0, 6, 0x4488cc);
    this.wetFill.setOrigin(0, 0.5);
    this.wetLabel = this.add.text(75, 145, '', {
      fontSize: '10px',
      fontFamily: 'Arial',
      color: '#6699bb',
    });

    // --- Form indicator ---
    this.formText = this.add.text(40, 170, 'PLANE', {
      fontSize: '12px',
      fontFamily: 'Arial',
      color: '#cccccc',
      stroke: '#000000',
      strokeThickness: 2,
    }).setOrigin(0.5, 0);

    // Listen for events
    if (this.gameScene) {
      this.gameScene.events.on('firefly-collected', (count) => {
        this.fireflyText.setText(count.toString());
        // Pulse animation
        this.tweens.add({
          targets: [this.fireflyIcon, this.fireflyText],
          scaleX: 1.3,
          scaleY: 1.3,
          duration: 150,
          yoyo: true,
        });
      });
    }
  }

  update() {
    if (!this.gameScene || !this.gameScene.player) return;

    const player = this.gameScene.player;
    const wind = this.gameScene.windSystem;
    const weather = this.gameScene.weatherSystem;

    // Firefly count
    this.fireflyText.setText(player.fireflies.toString());

    // Transform timer
    if (player.form !== 'plane' && player.transformDuration > 0) {
      this.transformBg.setVisible(true);
      this.transformText.setVisible(true);

      const pct = player.transformTimer / player.transformDuration;
      const secs = Math.ceil(player.transformTimer / 1000);
      this.transformText.setText(secs.toString());

      // Draw arc
      this.transformArc.clear();
      const color = pct > 0.3 ? 0x44dd44 : (pct > 0.15 ? 0xdddd44 : 0xdd4444);
      this.transformArc.lineStyle(4, color, 0.8);
      this.transformArc.beginPath();
      this.transformArc.arc(40, 100, 20, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * pct, false);
      this.transformArc.strokePath();

      // Flash warning
      if (secs <= 3) {
        this.transformText.setColor(secs % 2 === 0 ? '#ff4444' : '#ffffff');
      }
    } else {
      this.transformBg.setVisible(false);
      this.transformText.setVisible(false);
      this.transformArc.clear();
    }

    // Wind indicator
    if (wind) {
      const info = wind.getInfo();
      if (info.intensity > 0.05) {
        this.windArrow.setAlpha(Math.min(1, info.intensity * 2));
        this.windArrow.setAngle(info.angle);
        this.windArrow.setScale(1 + info.intensity);

        const strengthLabel = info.intensity < 0.2 ? 'Light' : info.intensity < 0.4 ? 'Moderate' : 'Strong';
        this.windText.setText(strengthLabel);
        this.windText.setAlpha(0.6);
      } else {
        this.windArrow.setAlpha(0);
        this.windText.setText('Calm');
        this.windText.setAlpha(0.3);
      }
    }

    // Weather
    if (weather) {
      const state = weather.getState();
      const labels = { clear: '', overcast: 'Overcast', rain: 'Rain', sun: 'Sunny' };
      this.weatherText.setText(labels[state] || '');
    }

    // Wetness
    if (player.wetness > 0.01) {
      const w = player.wetness * 58;
      this.wetFill.setSize(w, 6);
      this.wetLabel.setText('Wet');
      this.wetBg.setAlpha(0.5);
      this.wetFill.setAlpha(0.8);
      this.wetLabel.setAlpha(0.6);
    } else {
      this.wetBg.setAlpha(0);
      this.wetFill.setAlpha(0);
      this.wetLabel.setAlpha(0);
    }

    // Form
    this.formText.setText(player.form.toUpperCase());
  }
}
