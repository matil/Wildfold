/**
 * Level data for Wildfold
 * All positions in pixels. World coordinates.
 * Ground segments: [x, y, width, height]
 * Platforms: [x, y, width]
 * Water: [x, y, width, height]
 * Fireflies: [x, y]
 * Hazards: { type, x, y, ... }
 */

export const LEVELS = {
  'garden-1': {
    name: 'First Steps',
    width: 6400,
    height: 1080,
    spawnX: 200,
    spawnY: 700,
    checkpoints: [
      { x: 2000, y: 700 },
      { x: 4200, y: 600 },
    ],
    // Ground segments
    ground: [
      // Starting flat ground
      { x: 0, y: 880, w: 1200, h: 200 },
      // Small gap
      { x: 1280, y: 880, w: 800, h: 200 },
      // Step up
      { x: 2200, y: 816, w: 600, h: 264 },
      // Flat run
      { x: 2800, y: 880, w: 1400, h: 200 },
      // Final platform area
      { x: 4400, y: 816, w: 400, h: 264 },
      { x: 4900, y: 752, w: 300, h: 328 },
      // End ground
      { x: 5400, y: 880, w: 1000, h: 200 },
    ],
    // Floating platforms
    platforms: [
      { x: 1100, y: 720, w: 128 },
      { x: 1350, y: 660, w: 128 },
      { x: 1600, y: 600, w: 128 },
      { x: 3200, y: 720, w: 128 },
      { x: 3500, y: 640, w: 128 },
      { x: 4700, y: 650, w: 128 },
    ],
    // Fireflies
    fireflies: [
      { x: 400, y: 820 },
      { x: 600, y: 780 },
      { x: 900, y: 820 },
      { x: 1150, y: 680 },
      { x: 1400, y: 620 },
      { x: 1650, y: 560 },
      { x: 1500, y: 840 },
      { x: 2400, y: 760 },
      { x: 2800, y: 820 },
      { x: 3100, y: 840 },
      { x: 3250, y: 680 },
      { x: 3550, y: 600 },
      { x: 3800, y: 820 },
      { x: 4000, y: 780 },
      { x: 4500, y: 760 },
      { x: 4750, y: 600 },
      { x: 5000, y: 700 },
      { x: 5600, y: 820 },
      { x: 5900, y: 800 },
    ],
    // Water hazards (death pits)
    water: [
      { x: 1200, y: 920, w: 80, h: 160 },
    ],
    // Fire hazards
    fires: [],
    // Sprinklers
    sprinklers: [],
    // Wind zones
    windZones: [
      // Gentle tailwind to help player learn gliding
      { x: 800, y: 0, w: 600, h: 1080, dirX: 0.5, dirY: 0, intensity: 0.15 },
      // Updraft to help reach high platforms
      { x: 3100, y: 400, w: 200, h: 680, dirX: 0, dirY: -1, intensity: 0.25 },
    ],
    // Weather zones
    weatherZones: [],
    // Level end trigger
    exit: { x: 6100, y: 750, w: 100, h: 200 },
  },

  'garden-2': {
    name: 'Wind Whispers',
    width: 8000,
    height: 1080,
    spawnX: 200,
    spawnY: 700,
    checkpoints: [
      { x: 2400, y: 700 },
      { x: 4800, y: 600 },
      { x: 6500, y: 700 },
    ],
    ground: [
      { x: 0, y: 880, w: 1000, h: 200 },
      { x: 1200, y: 880, w: 600, h: 200 },
      { x: 2000, y: 880, w: 1200, h: 200 },
      // Gap with water
      { x: 3500, y: 880, w: 800, h: 200 },
      // Elevated section
      { x: 4500, y: 752, w: 600, h: 328 },
      { x: 5200, y: 816, w: 400, h: 264 },
      { x: 5800, y: 880, w: 1200, h: 200 },
      { x: 7200, y: 880, w: 800, h: 200 },
    ],
    platforms: [
      { x: 1000, y: 740, w: 128 },
      { x: 1250, y: 680, w: 128 },
      { x: 3200, y: 700, w: 128 },
      { x: 3900, y: 720, w: 128 },
      { x: 4200, y: 640, w: 128 },
      { x: 5500, y: 680, w: 128 },
      { x: 6800, y: 720, w: 128 },
      { x: 7000, y: 660, w: 128 },
    ],
    fireflies: [
      { x: 300, y: 820 }, { x: 600, y: 800 }, { x: 850, y: 830 },
      { x: 1050, y: 700 }, { x: 1300, y: 640 },
      { x: 1500, y: 840 }, { x: 1800, y: 820 },
      { x: 2200, y: 830 }, { x: 2600, y: 810 },
      { x: 3000, y: 840 }, { x: 3250, y: 660 },
      { x: 3600, y: 830 }, { x: 3950, y: 680 },
      { x: 4250, y: 600 }, { x: 4600, y: 700 },
      { x: 5000, y: 780 }, { x: 5300, y: 760 },
      { x: 5550, y: 640 }, { x: 5900, y: 830 },
      { x: 6200, y: 810 }, { x: 6500, y: 830 },
      { x: 6850, y: 680 }, { x: 7050, y: 620 },
      { x: 7400, y: 830 },
    ],
    water: [
      { x: 3200, y: 920, w: 300, h: 160 },
    ],
    fires: [],
    sprinklers: [
      { x: 2500, y: 848, active: true, interval: 3000 },
      { x: 6000, y: 848, active: true, interval: 2500 },
    ],
    windZones: [
      // Headwind challenge
      { x: 1800, y: 0, w: 800, h: 1080, dirX: -0.8, dirY: 0, intensity: 0.35 },
      // Strong tailwind
      { x: 3400, y: 0, w: 500, h: 1080, dirX: 1, dirY: 0, intensity: 0.4 },
      // Updraft
      { x: 4100, y: 300, w: 300, h: 780, dirX: 0, dirY: -1, intensity: 0.3 },
      // Gusty section
      { x: 6600, y: 0, w: 600, h: 1080, dirX: -0.5, dirY: -0.3, intensity: 0.25 },
    ],
    weatherZones: [
      { x: 4800, y: 0, w: 1200, h: 1080, state: 'rain' },
      { x: 6200, y: 0, w: 800, h: 1080, state: 'sun' },
    ],
    exit: { x: 7700, y: 750, w: 100, h: 200 },
  },

  'garden-3': {
    name: 'Paper Boat',
    width: 9600,
    height: 1080,
    spawnX: 200,
    spawnY: 700,
    checkpoints: [
      { x: 2000, y: 700 },
      { x: 4000, y: 500 },
      { x: 6400, y: 700 },
      { x: 8200, y: 700 },
    ],
    ground: [
      { x: 0, y: 880, w: 1600, h: 200 },
      { x: 1800, y: 880, w: 800, h: 200 },
      // Water section (need boat)
      { x: 3200, y: 880, w: 400, h: 200 },
      // Boat tutorial area
      { x: 4400, y: 880, w: 600, h: 200 },
      // More water
      { x: 5800, y: 880, w: 400, h: 200 },
      // Rain + wind challenge
      { x: 6800, y: 880, w: 1200, h: 200 },
      // Sun recovery zone
      { x: 8200, y: 880, w: 1400, h: 200 },
    ],
    platforms: [
      { x: 1400, y: 720, w: 128 },
      { x: 1700, y: 650, w: 128 },
      { x: 3000, y: 700, w: 128 },
      { x: 3600, y: 700, w: 128 },
      { x: 4000, y: 620, w: 128 },
      { x: 5200, y: 680, w: 128 },
      { x: 5500, y: 600, w: 128 },
      { x: 6400, y: 720, w: 128 },
      { x: 7800, y: 700, w: 128 },
      { x: 8000, y: 640, w: 128 },
    ],
    fireflies: [
      { x: 300, y: 820 }, { x: 600, y: 800 }, { x: 900, y: 830 },
      { x: 1200, y: 810 }, { x: 1450, y: 680 },
      { x: 1750, y: 610 }, { x: 2000, y: 830 },
      { x: 2300, y: 810 }, { x: 2600, y: 830 },
      // Extra fireflies before first water crossing (need 5 for boat)
      { x: 2800, y: 800 }, { x: 2900, y: 780 },
      { x: 3050, y: 660 }, { x: 3100, y: 830 },
      { x: 3400, y: 830 }, { x: 3650, y: 660 },
      { x: 4050, y: 580 }, { x: 4500, y: 830 },
      { x: 4700, y: 810 }, { x: 4900, y: 830 },
      // More fireflies for second crossing
      { x: 5100, y: 780 }, { x: 5250, y: 640 },
      { x: 5550, y: 560 }, { x: 5700, y: 830 },
      { x: 6000, y: 830 }, { x: 6200, y: 800 },
      { x: 6450, y: 680 }, { x: 6900, y: 830 },
      { x: 7200, y: 810 }, { x: 7500, y: 830 },
      { x: 7850, y: 660 }, { x: 8050, y: 600 },
      { x: 8400, y: 830 }, { x: 8700, y: 810 },
      { x: 9000, y: 830 },
    ],
    water: [
      // First water crossing (boat tutorial)
      { x: 2600, y: 900, w: 600, h: 180 },
      // Longer water crossing
      { x: 5000, y: 900, w: 800, h: 180 },
    ],
    fires: [
      { x: 7400, y: 848 },
    ],
    sprinklers: [
      { x: 4100, y: 848, active: true, interval: 4000 },
    ],
    windZones: [
      { x: 1600, y: 0, w: 400, h: 1080, dirX: 0.6, dirY: 0, intensity: 0.2 },
      { x: 3800, y: 200, w: 400, h: 880, dirX: 0, dirY: -0.8, intensity: 0.25 },
      // Headwind + rain combo
      { x: 7000, y: 0, w: 800, h: 1080, dirX: -0.7, dirY: 0, intensity: 0.4 },
      // Tailwind + sun recovery
      { x: 8400, y: 0, w: 600, h: 1080, dirX: 0.8, dirY: 0, intensity: 0.3 },
    ],
    weatherZones: [
      { x: 7000, y: 0, w: 1200, h: 1080, state: 'rain' },
      { x: 8400, y: 0, w: 1200, h: 1080, state: 'sun' },
    ],
    exit: { x: 9300, y: 750, w: 100, h: 200 },
  },
};
