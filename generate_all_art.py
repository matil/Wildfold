#!/usr/bin/env python3
"""
WILDFOLD - Fully Automated Art Pipeline
=========================================
Generates ALL game art, removes backgrounds, organizes into game folders.
Zero manual work. Run it, sleep, wake up to a ready game.

SETUP:
  1. Start ComfyUI: cd ComfyUI && python main.py
  2. Run: python generate_all_art.py
  3. Sleep.

REQUIREMENTS (auto-installed):
  pip install websocket-client Pillow numpy
"""

import json, os, sys, time, uuid, urllib.request, urllib.parse
from pathlib import Path
from io import BytesIO

try:
    import websocket
except ImportError:
    os.system(f"{sys.executable} -m pip install websocket-client")
    import websocket

try:
    from PIL import Image, ImageFilter
    import numpy as np
except ImportError:
    os.system(f"{sys.executable} -m pip install Pillow numpy")
    from PIL import Image, ImageFilter
    import numpy as np

# ============================================================================
# CONFIG - EDIT THESE IF NEEDED
# ============================================================================

COMFYUI_URL = "127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())

# Auto-detected. Set manually if auto-detect fails: "YourModel.safetensors"
CHECKPOINT = None
COMFYUI_MODELS_PATH = r"C:\Users\Mati\Downloads\AI\ComfyUI\ComfyUI\models\checkpoints"

# Output directly into game assets folder
ASSETS_DIR = Path("./assets")

# Generation settings for 3080 Ti 12GB
BG_WIDTH = 1344
BG_HEIGHT = 768
SPRITE_SIZE = 1024
STEPS = 30
CFG = 7.5
SPRITE_CFG = 6.0
SAMPLER = "dpmpp_2m"
SCHEDULER = "karras"

# Sprite bg removal settings
BG_COLOR = (10, 10, 40)
BG_TOLERANCE = 50

GLOBAL_NEGATIVE = (
    "text, watermark, signature, logo, username, blurry, out of focus, "
    "low quality, low resolution, jpeg artifacts, deformed, disfigured, "
    "mutated, ugly, duplicate, error, cropped, worst quality, "
    "nsfw, nudity, person, human"
)

# ============================================================================
# COMFYUI API
# ============================================================================

def queue_prompt(workflow):
    data = json.dumps({"prompt": workflow, "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(f"http://{COMFYUI_URL}/prompt", data=data,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["prompt_id"]

def wait_and_get_images(prompt_id):
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_URL}/ws?clientId={CLIENT_ID}")
    while True:
        out = ws.recv()
        if isinstance(out, str):
            msg = json.loads(out)
            if msg["type"] == "executing" and msg["data"]["node"] is None and msg["data"]["prompt_id"] == prompt_id:
                break
    ws.close()
    resp = urllib.request.urlopen(f"http://{COMFYUI_URL}/history/{prompt_id}")
    history = json.loads(resp.read())[prompt_id]
    images = []
    for node_output in history["outputs"].values():
        if "images" in node_output:
            for img in node_output["images"]:
                url = f"http://{COMFYUI_URL}/view?filename={urllib.parse.quote(img['filename'])}&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type={img['type']}"
                images.append(urllib.request.urlopen(url).read())
    return images

def build_workflow(positive, negative, width, height, seed=-1, steps=STEPS, cfg=CFG):
    if seed == -1:
        seed = int.from_bytes(os.urandom(4), "big")
    return {
        "3": {"inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": SAMPLER,
              "scheduler": SCHEDULER, "denoise": 1.0, "model": ["4", 0],
              "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}, "class_type": "KSampler"},
        "4": {"inputs": {"ckpt_name": CHECKPOINT}, "class_type": "CheckpointLoaderSimple"},
        "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"text": positive, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": negative, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
        "8": {"inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": "wildfold", "images": ["8", 0]}, "class_type": "SaveImage"},
    }

# ============================================================================
# IMAGE POST-PROCESSING
# ============================================================================

def remove_background(img):
    img = img.convert("RGBA")
    data = np.array(img)
    r, g, b = data[:,:,0].astype(float), data[:,:,1].astype(float), data[:,:,2].astype(float)
    dist = np.sqrt((r - BG_COLOR[0])**2 + (g - BG_COLOR[1])**2 + (b - BG_COLOR[2])**2)
    mask = dist < BG_TOLERANCE
    data[mask, 3] = 0
    result = Image.fromarray(data)
    alpha = result.split()[3].filter(ImageFilter.SMOOTH)
    result.putalpha(alpha)
    return result

def trim_and_resize(img, max_size=512):
    if img.mode == "RGBA":
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    return img

# ============================================================================
# LOGGING
# ============================================================================

LOG_FILE = None

def log(msg):
    print(msg)
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

# ============================================================================
# GENERATE SINGLE ASSET
# ============================================================================

def gen(positive, negative, width, height, save_path, is_sprite=False, sprite_size=256, cfg_override=None):
    path = ASSETS_DIR / save_path
    path.parent.mkdir(parents=True, exist_ok=True)
    neg = f"{negative}, {GLOBAL_NEGATIVE}" if negative else GLOBAL_NEGATIVE
    cfg_val = cfg_override or (SPRITE_CFG if is_sprite else CFG)
    try:
        wf = build_workflow(positive, neg, width, height, cfg=cfg_val)
        pid = queue_prompt(wf)
        imgs = wait_and_get_images(pid)
        if not imgs:
            log(f"  x No images: {path.name}")
            return False
        img = Image.open(BytesIO(imgs[0]))
        if is_sprite:
            img = remove_background(img)
            img = trim_and_resize(img, sprite_size)
        img.save(path, "PNG")
        log(f"  OK {path}")
        time.sleep(0.5)
        return True
    except Exception as e:
        log(f"  FAIL {path.name}: {e}")
        return False

# ============================================================================
# ALL ASSETS
# ============================================================================

N = "cartoon, people, person, human"

BACKGROUNDS = [
    # GARDEN
    ("backgrounds/garden/garden-sky.png", "photorealistic night sky over suburban backyard, stars visible, crescent moon, deep blue to dark purple gradient, wispy clouds, warm glow from house windows, seamless tileable, no people, cinematic, 8k", "daytime, sun, cartoon"),
    ("backgrounds/garden/garden-main.png", "photorealistic backyard garden at night, side view, lush bushes flowers, large oak tree, garden path stepping stones, wooden fence, flower beds, firefly light, dew, no people, seamless game background, 8k", f"daytime, {N}"),
    ("backgrounds/garden/garden-shed.png", "photorealistic old wooden garden shed at night, side view, terracotta pots, watering can, ivy, warm light from window, no people, seamless game background, 8k", f"daytime, {N}"),
    ("backgrounds/garden/garden-pond.png", "photorealistic small garden pond at night, side view, lily pads, reflective water, mossy rocks, reeds, moonlight, fireflies, no people, seamless game background, 8k", f"daytime, {N}"),
    ("backgrounds/garden/garden-tree.png", "photorealistic base of large oak tree at night, side view, exposed roots, mushrooms, fallen leaves, moss lichen, moonlight through canopy, no people, seamless game background, 8k", f"daytime, {N}"),
    ("backgrounds/garden/garden-fg.png", "close-up tall grass wildflowers at night, shallow depth of field, bokeh firefly lights, dew drops, ground level side view, photorealistic macro, dark bg, seamless tileable, 8k", f"daytime, {N}"),
    # NEIGHBORHOOD
    ("backgrounds/neighborhood/neighborhood-sky.png", "photorealistic suburban skyline at dusk, houses with lit windows, power lines, orange purple sunset, tree silhouettes, no people, seamless tileable, 8k", N),
    ("backgrounds/neighborhood/neighborhood-street.png", "photorealistic suburban street side view, sidewalk, white picket fence, mailbox, parked cars, streetlamp, autumn leaves, evening, no people, seamless game background, 8k", N),
    ("backgrounds/neighborhood/neighborhood-alley.png", "photorealistic narrow alley between houses side view, garbage bins, bicycle on wall, clothesline, dim light, autumn, no people, seamless game background, 8k", N),
    ("backgrounds/neighborhood/neighborhood-fg.png", "close-up chain link fence weeds at dusk, shallow depth of field, autumn leaves, cracked concrete, ground level, photorealistic, seamless tileable, 8k", N),
    # PARK
    ("backgrounds/park/park-sky.png", "photorealistic overcast sky over park, grey clouds light breaking through, distant tree line, moody, no people, seamless tileable, 8k", N),
    ("backgrounds/park/park-main.png", "photorealistic public park daytime side view, open grass, bench, path, scattered trees, pond background, overcast, no people, seamless game background, 8k", N),
    ("backgrounds/park/park-playground.png", "photorealistic playground equipment park side view, slide swings rubber mulch, overcast, no people no children, seamless game background, 8k", f"{N}, children"),
    ("backgrounds/park/park-pond.png", "photorealistic park pond wooden dock side view, ducks, cattails, weeping willow, reflections, overcast, no people, seamless game background, 8k", N),
    ("backgrounds/park/park-fg.png", "close-up park ground, fallen leaves grass, dandelions, puddle, ground level, overcast, photorealistic, seamless tileable, 8k", N),
    # STREAM
    ("backgrounds/stream/stream-sky.png", "photorealistic forest canopy from below, dappled sunlight, green leaves, blue sky patches, atmospheric, no people, seamless tileable, 8k", N),
    ("backgrounds/stream/stream-main.png", "photorealistic forest stream side view, rushing water over rocks, mossy boulders, ferns, dappled sunlight, waterfall bg, no people, seamless game background, 8k", N),
    ("backgrounds/stream/stream-rapids.png", "photorealistic white water rapids between rocks side view, spray mist, fast current, rocky channel, branches, no people, seamless game background, 8k", N),
    ("backgrounds/stream/stream-fg.png", "close-up riverbank ground level, wet pebbles, fern fronds, water droplets, mossy rocks, photorealistic macro, seamless tileable, 8k", N),
    # FOREST
    ("backgrounds/forest/forest-sky.png", "photorealistic dark forest canopy from below, dense, fog between trees, light barely breaking through, moody, no people, seamless tileable, 8k", f"bright, {N}"),
    ("backgrounds/forest/forest-main.png", "photorealistic dense forest interior side view, towering trees, heavy canopy, light shafts, undergrowth, ferns moss fog, no people, seamless game background, 8k", f"bright, {N}"),
    ("backgrounds/forest/forest-night.png", "photorealistic dark forest night side view, owl eyes in hollow, moonlight through gaps, sparse fireflies, eerie, no people, seamless game background, 8k", f"bright, daytime, {N}"),
    ("backgrounds/forest/forest-fg.png", "close-up forest floor, mushrooms, decaying leaves, spider web dew, moss rock, dark moody, photorealistic macro, seamless tileable, 8k", f"bright, {N}"),
    # MOUNTAIN
    ("backgrounds/mountain/mountain-sky.png", "photorealistic dramatic mountain sky, towering clouds, god rays, vast, snow peaks distance, epic, no people, seamless tileable, 8k", N),
    ("backgrounds/mountain/mountain-main.png", "photorealistic mountain rocky terrain side view, jagged cliff, narrow ledge, sparse alpine vegetation, snow patches, clouds, bent trees, no people, seamless game background, 8k", N),
    ("backgrounds/mountain/mountain-storm.png", "photorealistic mountain storm, dark clouds, lightning striking peak, heavy rain, exposed ridge, dramatic, no people, seamless game background, 8k", f"sunny, calm, {N}"),
    ("backgrounds/mountain/mountain-fg.png", "close-up rocky mountain ground, loose gravel, alpine flower in crack, lichen, snow, harsh light, photorealistic, seamless tileable, 8k", N),
    # SKY
    ("backgrounds/sky/sky-space.png", "photorealistic thin atmosphere to space, dark blue to black, stars milky way, thin blue line on horizon, serene vast, no people no aircraft, seamless tileable, 8k", f"ground, trees, airplane, {N}"),
    ("backgrounds/sky/sky-clouds.png", "photorealistic above clouds side view, towering cumulus, golden sunset from below, deep blue sky, stars visible, no people no aircraft, seamless game background, 8k", f"ground, airplane, {N}"),
    ("backgrounds/sky/sky-storm.png", "photorealistic inside thunderstorm cloud side view, dark turbulent, lightning arcing, purple blue, rain below, dramatic, no people, seamless game background, 8k", f"sunny, {N}"),
    ("backgrounds/sky/sky-fg.png", "close-up wispy cloud tendrils ice crystals, light refracting rainbow sparkles, thin atmosphere, dark sky, ethereal macro, seamless tileable, 8k", f"ground, {N}"),
]

SPRITE_NEG = "realistic airplane, metal, plastic, toy, colored paper, real bird, real frog, feathers, green slimy"

CHARACTERS = [
    ("sprites/plane/plane-idle.png", "white paper airplane origami, visible fold creases, worn paper texture, warm glow within, resting surface nose-up, side profile, isolated solid dark navy blue background, product photography, 8k"),
    ("sprites/plane/plane-glide.png", "white paper airplane in flight origami, fold creases, wings spread, upward angle, motion blur tips, warm glow, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-dive.png", "white paper airplane diving down origami, fold creases, nose down steep, speed, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-slide.png", "white paper airplane sliding flat surface origami, fold creases, forward tilt, ground contact, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-jump.png", "white paper airplane angled upward 45 degrees launching origami, fold creases, dynamic lift, warm glow, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-wet.png", "white paper airplane crumpled drooping damp, darker wet spots, drooping wings, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-dry.png", "white paper airplane crisp bright sharp folds, golden warm glow, pristine, upward angle, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/plane/plane-hit.png", "white paper airplane crumpled small tear on wing, bent nose, damaged, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/boat/boat-idle.png", "white paper origami boat classic shape, fold creases, calm water reflection, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/boat/boat-moving.png", "white paper origami boat moving forward, forward tilt, small wake, ripples, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/boat/boat-rocking.png", "white paper origami boat tilted side rough water, splash hull, rocking, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/boat/boat-transform.png", "white paper airplane mid-fold into boat shape, transitional, folding in progress, warm glow at folds, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/frog/frog-crouch.png", "white paper origami frog classic, crouching ready to jump, fold creases, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/frog/frog-jump.png", "white paper origami frog mid-jump legs extended upward, dynamic, fold creases, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/frog/frog-land.png", "white paper origami frog landing legs compressed, slight crumple, side profile, isolated solid dark navy blue background, 8k"),
    ("sprites/crane/crane-glide.png", "white paper origami crane traditional Japanese, wings spread graceful glide, fold creases, elegant, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/crane/crane-flap.png", "white paper origami crane wings downward mid-flap gaining height, dynamic, fold creases, side profile, warm glow, isolated solid dark navy blue background, 8k"),
    ("sprites/crane/crane-perch.png", "white paper origami crane standing wings folded sides, elegant resting, fold creases, side profile, warm glow, isolated solid dark navy blue background, 8k"),
]

ENEMIES = [
    ("sprites/enemies/cat-idle.png", "photorealistic tabby cat sitting alert, side profile, ears perked, watchful, night, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon, cute, sleeping"),
    ("sprites/enemies/cat-crouch.png", "photorealistic tabby cat crouching hunting, side profile, tensed to pounce, night, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon, cute"),
    ("sprites/enemies/cat-pounce.png", "photorealistic tabby cat mid-pounce leaping, side profile, paws extended, dynamic, night, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon"),
    ("sprites/enemies/cat-walk.png", "photorealistic tabby cat stalking, side profile, low deliberate steps, night, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon"),
    ("sprites/enemies/crow-fly.png", "photorealistic black crow flight, side profile, wings spread, glossy feathers, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon, colorful"),
    ("sprites/enemies/crow-dive.png", "photorealistic black crow swooping attack dive, side profile, talons forward, aggressive, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon"),
    ("sprites/enemies/wasp-fly.png", "photorealistic wasp flight, side profile, wings blurred, stinger visible, yellow black, aggressive, macro, isolated solid dark navy blue background, 8k", "cartoon, cute bee"),
    ("sprites/enemies/fish-jump.png", "photorealistic large trout jumping from water, side profile, mouth open, splash, scales, dynamic, isolated solid dark navy blue background, 8k", "cartoon, goldfish"),
    ("sprites/enemies/owl-fly.png", "photorealistic great horned owl flying, side profile, wingspan, talons, yellow eyes, moonlit, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon, cute"),
    ("sprites/enemies/owl-swoop.png", "photorealistic great horned owl swooping attack, side profile, talons reaching, intense eyes, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon"),
    ("sprites/enemies/eagle-fly.png", "photorealistic golden eagle soaring, side profile, massive wingspan, fierce, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon, small"),
    ("sprites/enemies/eagle-dive.png", "photorealistic golden eagle diving attack, side profile, wings folded, talons ready, speed, isolated solid dark navy blue background, wildlife photography, 8k", "cartoon"),
    ("sprites/enemies/storm-main.png", "massive cumulonimbus thundercloud, side view, dark swirling, lightning within, vortex center face, purple blue, rain below, isolated solid black background, 8k", "cartoon, fluffy, friendly"),
    ("sprites/enemies/storm-rage.png", "thunderstorm cloud face in vortex, angry expression, lightning eyes, terrifying, isolated solid black background, 8k", "cartoon, friendly, cute"),
]

OBJECTS = [
    ("sprites/hazards/fire-campfire.png", "photorealistic small campfire side view, orange flames, embers, smoke, wood logs, isolated solid dark navy blue background, 8k", "cartoon, explosion"),
    ("sprites/hazards/fire-candle.png", "photorealistic lit candle warm flame side view, melting wax, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/sprinkler.png", "photorealistic garden sprinkler side view, metal plastic, water spray arc, droplets, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/fence-picket.png", "photorealistic white picket fence section side view, weathered wood, isolated solid dark navy blue background, 8k", "cartoon, metal"),
    ("sprites/objects/fence-wood.png", "photorealistic wooden fence panel side view, brown slats, weathered, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/bush-round.png", "photorealistic round garden bush side view, dense green trimmed, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/bush-wild.png", "photorealistic wild untrimmed bush side view, natural shape, flowers, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/flowers.png", "photorealistic cluster garden flowers side view, daisies wildflowers, colorful, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/objects/mushrooms.png", "photorealistic cluster small mushrooms side view, brown caps, moss, macro, isolated solid dark navy blue background, 8k", "cartoon, giant"),
    ("sprites/objects/stone.png", "photorealistic round garden stepping stone, angled view, grey, moss edges, isolated solid dark navy blue background, 8k", "cartoon"),
    ("sprites/collectibles/firefly.png", "single firefly glowing brightly, macro, warm yellow-green bioluminescence, translucent wings, isolated solid black background, magical, 8k", "cartoon, butterfly, multiple"),
]

UI = [
    ("ui/menu-bg.png", "photorealistic childs wooden desk from above, scattered white paper, colored pencils, origami paper planes boats, warm desk lamp, cozy bedroom, top-down, nostalgic, 8k", "cartoon, messy, dark, people, hands"),
    ("ui/world-map.png", "hand-drawn treasure map aged parchment, dotted trail bottom-left garden to top-right stars, house bottom, hills trees middle, mountains, clouds moon top, watercolor vintage, 8k", "photograph, modern, digital, people"),
]

# ============================================================================
# MAIN
# ============================================================================

def detect_checkpoint():
    global CHECKPOINT
    if CHECKPOINT:
        return True
    models_dir = Path(COMFYUI_MODELS_PATH)
    if not models_dir.exists():
        log(f"x Models dir not found: {COMFYUI_MODELS_PATH}")
        return False
    checks = [f for f in models_dir.glob("*.safetensors") if f.stat().st_size > 2_000_000_000]
    if not checks:
        log("x No SDXL checkpoint (>2GB)")
        log(f"  Download: https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors")
        log(f"  Place in: {COMFYUI_MODELS_PATH}")
        return False
    for pref in ["realvis", "juggernaut", "dreamshar", "sdxl"]:
        for c in checks:
            if pref in c.name.lower():
                CHECKPOINT = c.name
                log(f"  Model: {CHECKPOINT} ({c.stat().st_size/1024**3:.1f}GB)")
                return True
    CHECKPOINT = checks[0].name
    log(f"  Model: {CHECKPOINT}")
    return True

def test_connection():
    try:
        urllib.request.urlopen(f"http://{COMFYUI_URL}/system_stats")
        log("  ComfyUI connected")
        return True
    except:
        log(f"x ComfyUI not running at {COMFYUI_URL}")
        log("  Start it first: cd ComfyUI && python main.py")
        return False

def main():
    global LOG_FILE
    print("="*60)
    print("  WILDFOLD - Automated Art Pipeline")
    print("  Run. Sleep. Done.")
    print("="*60)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = ASSETS_DIR / "generation_log.txt"
    if not test_connection():
        sys.exit(1)
    if not detect_checkpoint():
        sys.exit(1)

    total = len(BACKGROUNDS) + len(CHARACTERS) + len(ENEMIES) + len(OBJECTS) + len(UI)
    est = total * 25 / 60
    log(f"\n  Total assets: {total}")
    log(f"  Backgrounds: {len(BACKGROUNDS)}")
    log(f"  Characters: {len(CHARACTERS)} (auto: bg-remove + trim + resize)")
    log(f"  Enemies: {len(ENEMIES)} (auto: bg-remove + trim + resize)")
    log(f"  Objects: {len(OBJECTS)} (auto: bg-remove + trim + resize)")
    log(f"  UI: {len(UI)}")
    log(f"  Est. time: ~{est:.0f} min ({est/60:.1f} hrs)")

    input("\n  Press ENTER to start (Ctrl+C to cancel)...")

    start = time.time()
    done = 0

    try:
        log("\n--- BACKGROUNDS ---")
        for i, (p, pos, neg) in enumerate(BACKGROUNDS):
            log(f"[{done+1}/{total}] {p}")
            gen(pos, neg, BG_WIDTH, BG_HEIGHT, p)
            done += 1

        log("\n--- CHARACTERS ---")
        for i, (p, pos) in enumerate(CHARACTERS):
            log(f"[{done+1}/{total}] {p}")
            gen(pos, SPRITE_NEG, SPRITE_SIZE, SPRITE_SIZE, p, is_sprite=True, sprite_size=256)
            done += 1

        log("\n--- ENEMIES ---")
        for i, (p, pos, neg) in enumerate(ENEMIES):
            log(f"[{done+1}/{total}] {p}")
            gen(pos, neg, SPRITE_SIZE, SPRITE_SIZE, p, is_sprite=True, sprite_size=384)
            done += 1

        log("\n--- OBJECTS ---")
        for i, (p, pos, neg) in enumerate(OBJECTS):
            log(f"[{done+1}/{total}] {p}")
            gen(pos, neg, SPRITE_SIZE, SPRITE_SIZE, p, is_sprite=True, sprite_size=256)
            done += 1

        log("\n--- UI ---")
        for i, (p, pos, neg) in enumerate(UI):
            log(f"[{done+1}/{total}] {p}")
            gen(pos, neg, BG_WIDTH, BG_HEIGHT, p)
            done += 1

    except KeyboardInterrupt:
        log("\nInterrupted. Partial results saved.")
    except Exception as e:
        log(f"\nError: {e}")
        import traceback; traceback.print_exc()

    elapsed = time.time() - start
    n_files = sum(1 for _ in ASSETS_DIR.rglob("*.png"))
    log(f"\n{'='*60}")
    log(f"  DONE: {n_files} images in {int(elapsed//3600)}h {int((elapsed%3600)//60)}m")
    log(f"  Output: {ASSETS_DIR.absolute()}")
    log(f"{'='*60}")

if __name__ == "__main__":
    main()
