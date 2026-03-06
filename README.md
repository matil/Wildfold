# Wildfold

**A paper plane's journey to the edge of space.**

2D side-scrolling platformer where a paper plane comes to life and travels through seven worlds — from a backyard garden to the edge of space.

## Tech Stack

- **Engine:** Phaser 3
- **Bundler:** Vite
- **Language:** JavaScript
- **Target:** Steam (via Electron) + Web

## Setup

```bash
npm install
npm run dev
```

Open `http://localhost:8080` to play.

## Controls

| Action | Keyboard |
|--------|----------|
| Move | WASD / Arrow Keys |
| Jump / Glide | Space (hold in air to glide) |
| Transform | E |
| Revert to Plane | Q |

## Core Mechanics

- **Hybrid movement** — glide through air, slide on ground
- **Firefly currency** — collect fireflies to power transformations
- **Dynamic wind** — shifts during gameplay, affects each form differently
- **Weather** — rain makes paper heavy (debuff), sun dries it out (buff)
- **Transformations** — plane (default), boat (crosses water), frog (high jumps), crane (reach heights)

## Project Structure

```
src/
  main.js              # Game config & entry point
  scenes/
    BootScene.js       # Asset loading & placeholder generation
    MenuScene.js       # Main menu
    GameScene.js       # Core gameplay
    HUDScene.js        # UI overlay
  entities/
    Player.js          # Paper plane controller
  systems/
    WindSystem.js      # Dynamic wind
    WeatherSystem.js   # Rain/sun mechanics
  levels/
    LevelData.js       # Level definitions
assets/
  sprites/             # Character & object sprites
  backgrounds/         # Parallax background layers
  audio/               # Music & SFX
  ui/                  # UI elements
```

## V1 Scope (Garden World)

- 3 levels (First Steps, Wind Whispers, Paper Boat)
- Paper Plane + Boat transformation
- Wind system, weather system
- Firefly collection
- Placeholder art (replace with Stable Diffusion assets)

## License

All rights reserved.
