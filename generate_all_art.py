#!/usr/bin/env python3
"""
WILDFOLD - Premium Art Pipeline
=================================
Generates production-quality game art via ComfyUI.
- Best-of-4 selection (sharpness scoring)
- 2-pass hi-res generation for backgrounds
- Per-world color grading for visual consistency
- Smart edge-aware background removal for sprites
- Auto upscale for crisp detail

SETUP:
  1. Start ComfyUI: cd ComfyUI && python main.py
  2. Download SDXL model into ComfyUI/models/checkpoints/
  3. python generate_all_art.py
  4. Sleep. ~3-4 hours on RTX 3080 Ti.

REQUIREMENTS (auto-installed):
  pip install websocket-client Pillow numpy scipy
"""

import json, os, sys, time, uuid, urllib.request, urllib.parse
from pathlib import Path
from io import BytesIO

for pkg in ["websocket-client", "Pillow", "numpy", "scipy"]:
    try:
        __import__(pkg.replace("-", "_").split("-")[0])
    except ImportError:
        os.system(f"{sys.executable} -m pip install {pkg}")

import websocket
from PIL import Image, ImageFilter, ImageEnhance, ImageStat
import numpy as np
from scipy import ndimage

# ============================================================================
# CONFIG
# ============================================================================

COMFYUI_URL = "127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())

CHECKPOINT = None  # Auto-detect
COMFYUI_MODELS_PATH = r"C:\Users\Mati\Downloads\AI\ComfyUI\ComfyUI\models\checkpoints"

ASSETS_DIR = Path("./assets")

# Generation settings for 3080 Ti 12GB
BG_WIDTH = 1344
BG_HEIGHT = 768
BG_UPSCALE_WIDTH = 1920   # Final bg resolution
BG_UPSCALE_HEIGHT = 1080
SPRITE_GEN_SIZE = 1024
SPRITE_FINAL_SIZE = 512    # Characters
ENEMY_FINAL_SIZE = 512     # Enemies
OBJECT_FINAL_SIZE = 384    # Objects

STEPS = 35           # More steps = more detail
CFG = 7.5
SPRITE_CFG = 6.0
SAMPLER = "dpmpp_2m"
SCHEDULER = "karras"

CANDIDATES = 4  # Generate N, keep best

# Background removal
BG_COLOR_NAVY = (10, 10, 40)
BG_COLOR_BLACK = (0, 0, 0)
BG_TOLERANCE = 45

GLOBAL_NEGATIVE = (
    "text, watermark, signature, logo, username, blurry, out of focus, "
    "low quality, low resolution, jpeg artifacts, deformed, disfigured, "
    "mutated, ugly, duplicate, error, cropped, worst quality, "
    "nsfw, nudity, person, human, hands, fingers"
)

# ============================================================================
# PER-WORLD COLOR GRADING
# Ensures visual consistency within each world
# ============================================================================

WORLD_GRADING = {
    "garden": {
        "brightness": 0.95,     # Slightly dark (night)
        "contrast": 1.1,
        "saturation": 1.05,
        "color_temp": (-5, -3, 10),  # Cool blue night shift
        "tint": (20, 25, 50),         # Night blue tint overlay at 8% opacity
        "tint_opacity": 0.08,
    },
    "neighborhood": {
        "brightness": 1.0,
        "contrast": 1.05,
        "saturation": 0.95,      # Slightly muted
        "color_temp": (10, 5, -5),  # Warm dusk
        "tint": (50, 35, 20),
        "tint_opacity": 0.06,
    },
    "park": {
        "brightness": 0.98,
        "contrast": 1.0,
        "saturation": 0.9,       # Overcast = desaturated
        "color_temp": (-3, -2, -2),
        "tint": (40, 42, 45),    # Grey overcast
        "tint_opacity": 0.05,
    },
    "stream": {
        "brightness": 1.05,
        "contrast": 1.1,
        "saturation": 1.15,      # Rich greens
        "color_temp": (-5, 8, -3),  # Green shift
        "tint": (15, 35, 20),
        "tint_opacity": 0.05,
    },
    "forest": {
        "brightness": 0.85,      # Dark
        "contrast": 1.15,
        "saturation": 0.9,
        "color_temp": (-8, -2, 5),  # Dark cool
        "tint": (10, 18, 15),
        "tint_opacity": 0.1,
    },
    "mountain": {
        "brightness": 1.1,
        "contrast": 1.2,         # Harsh dramatic
        "saturation": 0.95,
        "color_temp": (-3, -3, 5),  # Cool altitude
        "tint": (35, 38, 50),
        "tint_opacity": 0.04,
    },
    "sky": {
        "brightness": 1.0,
        "contrast": 1.15,
        "saturation": 1.1,
        "color_temp": (-5, -5, 15),  # Deep blue space
        "tint": (5, 8, 30),
        "tint_opacity": 0.08,
    },
}

# ============================================================================
# ART DIRECTION PREFIXES (prepended to all prompts per world)
# ============================================================================

WORLD_STYLE = {
    "garden":       "masterpiece, award-winning photography, magical atmosphere, cinematic lighting, volumetric firefly light, dark moody night scene with warm pockets of light, ",
    "neighborhood": "masterpiece, cinematic photography, golden hour dusk lighting, warm streetlamp glow, nostalgic suburban autumn atmosphere, ",
    "park":         "masterpiece, cinematic photography, overcast diffused natural light, moody grey sky, lush green nature, peaceful yet melancholic, ",
    "stream":       "masterpiece, nature photography, dappled sunlight through canopy, crystal clear water, lush green forest, vibrant natural colors, ",
    "forest":       "masterpiece, dark atmospheric photography, deep shadows, volumetric fog, mysterious ancient woodland, sparse dramatic light shafts, ",
    "mountain":     "masterpiece, epic landscape photography, dramatic clouds, vast scale, harsh alpine light, wind-swept desolation, ",
    "sky":          "masterpiece, aerospace photography, ethereal atmosphere, cosmic lighting, vast infinite space, transcendent beauty, ",
    "sprite":       "masterpiece, product photography, studio lighting, crisp sharp focus, clean edges, professional, ",
}

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
# IMAGE QUALITY SCORING
# ============================================================================

def sharpness_score(img):
    """Score image sharpness using Laplacian variance. Higher = sharper."""
    grey = np.array(img.convert("L"), dtype=np.float64)
    laplacian = ndimage.laplace(grey)
    return float(np.var(laplacian))

def detail_score(img):
    """Combined quality score: sharpness + edge density + contrast."""
    grey = np.array(img.convert("L"), dtype=np.float64)
    # Sharpness
    lap_var = float(np.var(ndimage.laplace(grey)))
    # Edge density (Sobel)
    sx = ndimage.sobel(grey, axis=0)
    sy = ndimage.sobel(grey, axis=1)
    edge_density = float(np.mean(np.hypot(sx, sy)))
    # Local contrast
    local_std = float(np.std(grey))
    # Weighted combination
    return lap_var * 0.5 + edge_density * 0.3 + local_std * 0.2

def pick_best(images):
    """From a list of PIL Images, return the one with highest quality score."""
    if len(images) == 1:
        return images[0]
    scored = [(detail_score(img), img) for img in images]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]

# ============================================================================
# IMAGE POST-PROCESSING
# ============================================================================

def remove_background_smart(img, bg_color=BG_COLOR_NAVY, tolerance=BG_TOLERANCE):
    """Edge-aware background removal with alpha matting."""
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.float64)
    r, g, b = data[:,:,0], data[:,:,1], data[:,:,2]

    # Color distance
    dist = np.sqrt((r - bg_color[0])**2 + (g - bg_color[1])**2 + (b - bg_color[2])**2)

    # Hard mask
    hard_mask = dist > tolerance

    # Soft edge mask (gradient at edges for anti-aliasing)
    soft_zone = tolerance * 0.6
    alpha = np.clip((dist - (tolerance - soft_zone)) / soft_zone, 0, 1)
    alpha = (alpha * 255).astype(np.uint8)

    # Edge detection to preserve sharp edges of the subject
    grey = np.array(img.convert("L"), dtype=np.float64)
    edges = ndimage.sobel(grey)
    edge_mask = edges > np.percentile(edges, 85)

    # Where there are strong edges, use hard alpha
    alpha[edge_mask & hard_mask] = 255

    # Apply
    result = np.array(img)
    result[:,:,3] = alpha

    # Clean up: remove isolated transparent pixels inside the subject
    from scipy.ndimage import binary_fill_holes, binary_dilation
    subject_mask = alpha > 128
    filled = binary_fill_holes(subject_mask)
    # Restore alpha for filled holes
    result[filled & ~subject_mask, 3] = 255

    return Image.fromarray(result)

def trim_transparent(img):
    """Crop transparent borders with small padding."""
    if img.mode != "RGBA":
        return img
    bbox = img.getbbox()
    if bbox:
        # Add 4px padding
        x1 = max(0, bbox[0] - 4)
        y1 = max(0, bbox[1] - 4)
        x2 = min(img.width, bbox[2] + 4)
        y2 = min(img.height, bbox[3] + 4)
        return img.crop((x1, y1, x2, y2))
    return img

def upscale_lanczos(img, target_w, target_h):
    """High-quality upscale using Lanczos resampling."""
    return img.resize((target_w, target_h), Image.LANCZOS)

def sharpen_pass(img, amount=1.3):
    """Subtle sharpening for crisp detail."""
    enhancer = ImageEnhance.Sharpness(img)
    return enhancer.enhance(amount)

def color_grade(img, world):
    """Apply per-world color grading for visual consistency."""
    if world not in WORLD_GRADING:
        return img

    g = WORLD_GRADING[world]

    # Brightness
    img = ImageEnhance.Brightness(img).enhance(g["brightness"])
    # Contrast
    img = ImageEnhance.Contrast(img).enhance(g["contrast"])
    # Saturation
    img = ImageEnhance.Color(img).enhance(g["saturation"])

    # Color temperature shift
    data = np.array(img).astype(np.float64)
    ct = g["color_temp"]
    if len(data.shape) == 3:
        channels = min(3, data.shape[2])
        for c in range(channels):
            data[:,:,c] = np.clip(data[:,:,c] + ct[c], 0, 255)

    # Tint overlay
    if g["tint_opacity"] > 0:
        tint = np.array(g["tint"], dtype=np.float64)
        opacity = g["tint_opacity"]
        for c in range(channels):
            data[:,:,c] = data[:,:,c] * (1 - opacity) + tint[c] * opacity * 255 / max(tint)

    data = np.clip(data, 0, 255).astype(np.uint8)
    return Image.fromarray(data)

# ============================================================================
# LOGGING
# ============================================================================

LOG_FILE = None
STATS = {"ok": 0, "fail": 0, "total_candidates": 0}

def log(msg):
    print(msg)
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

# ============================================================================
# CORE GENERATION
# ============================================================================

def generate_candidates(positive, negative, width, height, n=CANDIDATES, cfg_val=CFG):
    """Generate N candidate images, return as list of PIL Images."""
    neg = f"{negative}, {GLOBAL_NEGATIVE}" if negative else GLOBAL_NEGATIVE
    candidates = []
    for i in range(n):
        try:
            wf = build_workflow(positive, neg, width, height, cfg=cfg_val, steps=STEPS)
            pid = queue_prompt(wf)
            imgs = wait_and_get_images(pid)
            if imgs:
                candidates.append(Image.open(BytesIO(imgs[0])))
            time.sleep(0.3)
        except Exception as e:
            log(f"    candidate {i+1} failed: {e}")
    STATS["total_candidates"] += len(candidates)
    return candidates

def gen_background(save_path, prompt, negative, world):
    """Generate background: best-of-N, upscale, color grade, sharpen."""
    path = ASSETS_DIR / save_path
    path.parent.mkdir(parents=True, exist_ok=True)

    style = WORLD_STYLE.get(world, "")
    full_prompt = style + prompt

    log(f"    Generating {CANDIDATES} candidates...")
    candidates = generate_candidates(full_prompt, negative, BG_WIDTH, BG_HEIGHT)

    if not candidates:
        log(f"  x FAIL {path.name}: no candidates")
        STATS["fail"] += 1
        return False

    # Pick best
    best = pick_best(candidates)
    log(f"    Picked best of {len(candidates)} (score: {detail_score(best):.1f})")

    # Upscale to game resolution
    best = upscale_lanczos(best, BG_UPSCALE_WIDTH, BG_UPSCALE_HEIGHT)

    # Color grade for world consistency
    best = color_grade(best, world)

    # Sharpen
    best = sharpen_pass(best, 1.2)

    best.save(path, "PNG", optimize=True)
    log(f"  OK {path} ({best.size[0]}x{best.size[1]})")
    STATS["ok"] += 1
    return True

def gen_sprite(save_path, prompt, negative, final_size=SPRITE_FINAL_SIZE, bg_color=BG_COLOR_NAVY):
    """Generate sprite: best-of-N, bg remove, trim, resize, sharpen."""
    path = ASSETS_DIR / save_path
    path.parent.mkdir(parents=True, exist_ok=True)

    style = WORLD_STYLE.get("sprite", "")
    full_prompt = style + prompt

    log(f"    Generating {CANDIDATES} candidates...")
    candidates = generate_candidates(full_prompt, negative, SPRITE_GEN_SIZE, SPRITE_GEN_SIZE, cfg_val=SPRITE_CFG)

    if not candidates:
        log(f"  x FAIL {path.name}: no candidates")
        STATS["fail"] += 1
        return False

    # Pick best
    best = pick_best(candidates)
    log(f"    Picked best of {len(candidates)}")

    # Remove background
    best = remove_background_smart(best, bg_color)

    # Trim transparent borders
    best = trim_transparent(best)

    # Resize to final size (maintain aspect ratio)
    best.thumbnail((final_size, final_size), Image.LANCZOS)

    # Sharpen
    # Convert to RGB for sharpening, then restore alpha
    if best.mode == "RGBA":
        rgb = best.convert("RGB")
        rgb = sharpen_pass(rgb, 1.4)
        r, g, b = rgb.split()
        a = best.split()[3]
        best = Image.merge("RGBA", (r, g, b, a))

    best.save(path, "PNG", optimize=True)
    log(f"  OK {path} ({best.size[0]}x{best.size[1]})")
    STATS["ok"] += 1
    return True

def gen_ui_image(save_path, prompt, negative):
    """Generate UI image: best-of-N, upscale, sharpen."""
    path = ASSETS_DIR / save_path
    path.parent.mkdir(parents=True, exist_ok=True)

    log(f"    Generating {CANDIDATES} candidates...")
    candidates = generate_candidates(prompt, negative, BG_WIDTH, BG_HEIGHT)

    if not candidates:
        log(f"  x FAIL {path.name}")
        STATS["fail"] += 1
        return False

    best = pick_best(candidates)
    best = upscale_lanczos(best, BG_UPSCALE_WIDTH, BG_UPSCALE_HEIGHT)
    best = sharpen_pass(best, 1.2)
    best.save(path, "PNG", optimize=True)
    log(f"  OK {path}")
    STATS["ok"] += 1
    return True

# ============================================================================
# ASSET DEFINITIONS - PREMIUM PROMPTS
# ============================================================================

N = "cartoon, anime, illustration, painting, sketch, drawing, 3d render, people, person, human"

# BACKGROUNDS: (path, prompt, negative, world)
BACKGROUNDS = [
    # ===== GARDEN (magical night) =====
    ("backgrounds/garden/garden-sky.png",
     "night sky over suburban backyard, thousands of stars visible, thin crescent moon, deep blue to dark purple gradient sky, wispy thin clouds, warm amber glow from distant house windows reflecting on atmosphere, long exposure photography, seamless tileable, 8k ultra detailed",
     f"daytime, sun, bright sky, {N}", "garden"),
    ("backgrounds/garden/garden-main.png",
     "lush backyard garden at night, perfect side view for 2D game, dense flowering bushes with roses and hydrangeas, large ancient oak tree with thick twisted branches, winding stone path with moss between stepping stones, weathered wooden fence with climbing ivy, scattered fireflies creating warm bokeh orbs of light, dew glistening on every leaf, rich detailed vegetation, depth layers, 8k ultra detailed",
     f"daytime, bare, winter, snow, {N}", "garden"),
    ("backgrounds/garden/garden-shed.png",
     "charming old wooden garden shed at night, side view, terracotta pots stacked outside, vintage watering can, cobwebs in corners, ivy and wisteria climbing walls, single warm lantern light from dusty window, garden tools leaning against wall, brick path leading to door, 8k ultra detailed",
     f"daytime, modern, clean, {N}", "garden"),
    ("backgrounds/garden/garden-pond.png",
     "small magical garden pond at night, side view, lily pads with tiny white flowers floating, perfectly reflective dark water surface mirroring moon, mossy ancient rocks around edges, tall reeds and cattails, single firefly reflected in water, peaceful serene atmosphere, 8k ultra detailed",
     f"daytime, ocean, river, large water, {N}", "garden"),
    ("backgrounds/garden/garden-tree.png",
     "magnificent base of ancient oak tree at night, side view, massive exposed gnarled roots creating natural caves, bioluminescent mushrooms growing on bark, thick carpet of fallen autumn leaves, dense moss and lichen covering everything, knot hole glowing with firefly light inside, 8k ultra detailed",
     f"daytime, small tree, sapling, {N}", "garden"),
    ("backgrounds/garden/garden-fg.png",
     "extreme close-up tall wild grass blades and wildflowers at night, ground level macro perspective, shallow depth of field, beautiful bokeh of warm firefly orbs in background, crystal dew drops on grass catching moonlight, dandelion seeds floating, clover flowers, 8k ultra detailed macro photography",
     f"daytime, sharp background, aerial view, {N}", "garden"),

    # ===== NEIGHBORHOOD (autumn dusk) =====
    ("backgrounds/neighborhood/neighborhood-sky.png",
     "breathtaking suburban skyline at golden hour dusk, row of charming houses with warm lit windows, silhouette of power lines and utility poles, spectacular orange pink and purple sunset gradient, tree silhouettes against sky, first stars appearing, seamless tileable, 8k ultra detailed",
     f"noon, night, {N}", "neighborhood"),
    ("backgrounds/neighborhood/neighborhood-street.png",
     "quiet suburban street in autumn evening, perfect side view, cracked sidewalk with weeds growing through, charming white picket fence with peeling paint, classic mailbox, vintage parked cars, warm glowing streetlamp casting pool of light, scattered red and gold autumn leaves, wet pavement reflecting lights, 8k ultra detailed",
     f"summer, snow, busy, crowded, {N}", "neighborhood"),
    ("backgrounds/neighborhood/neighborhood-alley.png",
     "atmospheric narrow alley between old suburban houses at dusk, side view, metal garbage bins, rusty bicycle leaning on brick wall, clothesline with sheets above, dim light at end of alley, autumn leaves collected in corners, puddles reflecting sky, 8k ultra detailed",
     f"modern city, skyscrapers, clean, {N}", "neighborhood"),
    ("backgrounds/neighborhood/neighborhood-fg.png",
     "extreme close-up rusty chain link fence with overgrown weeds at dusk, ground level, shallow depth of field, scattered wet autumn leaves on cracked concrete, warm light filtering through fence, macro photography, seamless tileable, 8k ultra detailed",
     f"clean, new, {N}", "neighborhood"),

    # ===== PARK (overcast green) =====
    ("backgrounds/park/park-sky.png",
     "dramatic overcast sky over parkland, layers of grey clouds with occasional break of warm light, distant treeline silhouette, moody atmospheric volumetric light, birds silhouette, seamless tileable, 8k ultra detailed",
     f"clear blue sky, night, sunset, {N}", "park"),
    ("backgrounds/park/park-main.png",
     "beautiful public park on overcast day, side view, vast open emerald grass field, weathered wooden park bench, winding gravel path, majestic scattered trees with full canopy, serene pond visible in background, distant playground, soft diffused light, rich green tones, 8k ultra detailed",
     f"night, desert, {N}", "park"),
    ("backgrounds/park/park-playground.png",
     "charming playground equipment in park, side view, colorful painted metal slide with patina, wooden swing set, rubber mulch ground, sand pit with toys left behind, overcast soft light, nostalgic feeling, 8k ultra detailed",
     f"night, indoor, {N}, children", "park"),
    ("backgrounds/park/park-pond.png",
     "peaceful park pond with old wooden dock, side view, family of ducks swimming, tall cattails and bulrushes, graceful weeping willow tree branches touching water, perfect reflections, dragonflies, overcast soft light, 8k ultra detailed",
     f"ocean, rapids, night, {N}", "park"),
    ("backgrounds/park/park-fg.png",
     "close-up park ground level, scattered colorful fallen leaves on wet grass, dandelion puffs, tiny mushroom, small rain puddle, ground level macro, overcast diffused light, seamless tileable, 8k ultra detailed",
     f"night, bright sun, {N}", "park"),

    # ===== STREAM (lush water) =====
    ("backgrounds/stream/stream-sky.png",
     "looking up through dense forest canopy, dappled golden sunlight rays breaking through green leaves, scattered blue sky patches, light particles floating in beams, atmospheric depth, seamless tileable, 8k ultra detailed",
     f"night, overcast, {N}", "stream"),
    ("backgrounds/stream/stream-main.png",
     "crystal clear forest stream, side view, rushing water over smooth rocks creating white ripples, large mossy boulders, lush ferns cascading from banks, dappled sunlight creating light patterns on water, small waterfall cascading in background, incredibly detailed water, 8k ultra detailed",
     f"desert, ocean, city, {N}", "stream"),
    ("backgrounds/stream/stream-rapids.png",
     "dramatic white water rapids between large boulders, side view, powerful current spray and mist, narrow rocky channel, overhanging tree branches with hanging moss, dramatic lighting through mist, action and energy, 8k ultra detailed",
     f"calm, still, ocean, {N}", "stream"),
    ("backgrounds/stream/stream-fg.png",
     "extreme close-up riverbank, wet polished pebbles and stones, unfurling fern fronds, crystal water droplets on leaves, bright green moss on rocks, macro ground level, dappled light, seamless tileable, 8k ultra detailed",
     f"dry, desert, {N}", "stream"),

    # ===== FOREST (dark mysterious) =====
    ("backgrounds/forest/forest-sky.png",
     "looking up through ancient dark forest canopy, almost completely blocking sky, thick branches interweaving, occasional thin beam of light cutting through darkness, mysterious fog drifting between trees high above, 8k ultra detailed",
     f"bright, open, sunny, {N}", "forest"),
    ("backgrounds/forest/forest-main.png",
     "deep ancient forest interior, side view, massive towering trees with trunks wider than houses, impenetrable canopy creating deep shadow, single dramatic shaft of golden light cutting through darkness, thick undergrowth of ferns and moss, mysterious fog rolling between trees at ground level, 8k ultra detailed",
     f"bright, sparse, meadow, {N}", "forest"),
    ("backgrounds/forest/forest-night.png",
     "terrifying dark forest at night, side view, pair of glowing yellow owl eyes peering from black tree hollow, thin moonbeams cutting through canopy gaps, a few lonely fireflies, gnarled tree silhouettes, roots like fingers, oppressive darkness, 8k ultra detailed",
     f"bright, daytime, friendly, {N}", "forest"),
    ("backgrounds/forest/forest-fg.png",
     "extreme close-up ancient forest floor, cluster of glowing bioluminescent mushrooms, decomposing leaves, intricate spider web with morning dew drops catching light, thick emerald moss on fallen log, macro ground level, dark atmosphere, seamless tileable, 8k ultra detailed",
     f"bright, clean, {N}", "forest"),

    # ===== MOUNTAIN (epic harsh) =====
    ("backgrounds/mountain/mountain-sky.png",
     "epic mountain sky, massive towering cumulonimbus clouds lit by golden sun behind them, god rays streaming down, vast infinite sky feeling, snow-capped peaks in far distance below clouds, awe-inspiring scale, seamless tileable, 8k ultra detailed",
     f"flat, indoor, {N}", "mountain"),
    ("backgrounds/mountain/mountain-main.png",
     "dramatic mountain terrain side view, jagged granite cliff face with narrow dangerous ledge path, sparse hardy alpine flowers clinging to cracks, patches of snow and ice, dramatic clouds both below and above creating sense of extreme height, wind-bent dwarf trees, vertigo-inducing scale, 8k ultra detailed",
     f"flat, forest, city, {N}", "mountain"),
    ("backgrounds/mountain/mountain-storm.png",
     "terrifying mountain storm, dark apocalyptic clouds, multiple lightning bolts striking nearby peaks simultaneously, horizontal rain, exposed dangerous rocky ridge, no shelter, raw power of nature, dramatic atmosphere, 8k ultra detailed",
     f"sunny, calm, peaceful, {N}", "mountain"),
    ("backgrounds/mountain/mountain-fg.png",
     "extreme close-up mountain rock face, loose gravel and scree, tiny resilient alpine flower blooming from crack in rock, patches of colorful lichen, thin ice crystals, harsh directional light, macro ground level, seamless tileable, 8k ultra detailed",
     f"lush, tropical, {N}", "mountain"),

    # ===== SKY (cosmic transcendent) =====
    ("backgrounds/sky/sky-space.png",
     "edge of space, thin glowing blue atmospheric line on curved horizon far below, transition from deep blue to pure black, thousands of crisp stars and visible milky way galaxy band, absolute silence and vastness, ISS perspective, seamless tileable, 8k ultra detailed",
     f"ground, trees, buildings, airplane, clouds, {N}", "sky"),
    ("backgrounds/sky/sky-clouds.png",
     "breathtaking view above cloud layer, side perspective, towering cathedral-like cumulus cloud formations reaching upward like pillars, golden and pink sunset light illuminating cloud edges from below, deep cobalt blue sky above, first stars becoming visible, ethereal otherworldly beauty, 8k ultra detailed",
     f"ground, buildings, airplane, {N}", "sky"),
    ("backgrounds/sky/sky-storm.png",
     "inside massive thunderstorm cloud, side view, violent swirling dark interior lit by branching lightning arcs, deep purple and electric blue tones, curtain of rain visible below, turbulent and terrifying, raw atmospheric power, 8k ultra detailed",
     f"sunny, calm, clear, ground, {N}", "sky"),
    ("backgrounds/sky/sky-fg.png",
     "extreme close-up thin cirrus cloud wisps and ice crystals at high altitude, light refracting through crystals creating prismatic rainbow sparkles, near-black sky behind, otherworldly ethereal beauty, macro photography, seamless tileable, 8k ultra detailed",
     f"ground, thick clouds, {N}", "sky"),
]

SPRITE_NEG = f"realistic metal airplane, plastic toy, colored paper, real bird, real frog, feathers, green slimy, {N}"

CHARACTERS = [
    # PLANE (8 poses)
    ("sprites/plane/plane-idle.png", "single white paper airplane, hand-folded origami style, visible sharp fold creases, slightly worn authentic paper texture with subtle fiber detail, soft warm amber glow emanating from within through translucent paper, resting on flat surface with nose slightly raised, perfect side profile silhouette, isolated on solid #0A0A28 dark navy background, professional product photography, studio lighting, 8k"),
    ("sprites/plane/plane-glide.png", "single white paper airplane in graceful flight, origami style, fold creases visible, wings elegantly spread at slight upward angle, subtle motion blur on wing tips suggesting movement, warm inner glow visible through paper, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-dive.png", "single white paper airplane in steep dive, origami style, nose pointing sharply downward, aerodynamic pose, fold creases, sense of speed and gravity, side profile, warm glow, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-slide.png", "single white paper airplane sliding along flat surface, origami style, belly touching ground, slight forward lean suggesting momentum, fold creases, side profile, warm glow, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-jump.png", "single white paper airplane launching upward at 45 degree angle, origami style, dynamic lifting pose full of energy, fold creases, warm glow intensifying, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-wet.png", "single white paper airplane drooping and slightly crumpled from moisture, darker translucent wet spots on paper, wings sagging downward, melancholy posture, fold lines softened by water, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-dry.png", "single white paper airplane in pristine crisp condition, perfectly sharp fold lines, paper glowing bright warm gold from within, confident upward angle, paper looks fresh and strong, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-hit.png", "single white paper airplane with visible damage, small tear on wing edge, crumpled nose, one wing slightly bent, battle-worn but still airborne, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),

    # BOAT (4 poses)
    ("sprites/boat/boat-idle.png", "single white paper origami boat, classic traditional paper boat shape, clean fold creases visible, floating on small area of calm water with beautiful reflection, warm amber glow from within, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-moving.png", "single white paper origami boat moving forward through water, slight forward lean, small V-shaped wake trailing behind, water ripples around hull, dynamic pose, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-rocking.png", "single white paper origami boat tilted to one side on choppy water, small splash against hull, dynamic rocking motion captured, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-transform.png", "single piece of white paper caught mid-fold between airplane and boat shape, magical transformation in progress, glowing warm light at every fold point, geometric transitional form, side profile, isolated on solid #0A0A28 dark navy background, 8k"),

    # FROG (3 poses)
    ("sprites/frog/frog-crouch.png", "single white paper origami frog in classic folded shape, crouching pose coiled ready to spring, visible geometric fold creases, paper texture, warm amber inner glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/frog/frog-jump.png", "single white paper origami frog at peak of jump, legs fully extended below, airborne dynamic pose, fold creases visible on legs and body, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/frog/frog-land.png", "single white paper origami frog landing with legs compressed absorbing impact, slight paper crumple on contact, fold creases, warm glow dimming slightly, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),

    # CRANE (3 poses)
    ("sprites/crane/crane-glide.png", "single white paper origami crane in traditional Japanese thousand cranes style, wings fully spread in graceful soaring glide, beautiful geometric fold creases, elegant and majestic, warm amber glow from within, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/crane/crane-flap.png", "single white paper origami crane with wings angled downward in powerful flap stroke, gaining altitude, dynamic movement, fold creases, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/crane/crane-perch.png", "single white paper origami crane standing tall on one leg, wings folded neatly at sides, serene elegant resting pose, precise fold creases, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
]

ENEMIES = [
    # Cat (4 poses)
    ("sprites/enemies/cat-idle.png", "photorealistic domestic tabby cat sitting upright and alert, side profile, ears pointed forward, bright watchful green eyes, detailed fur texture, tail curled around feet, dramatic night lighting, isolated on solid #0A0A28 dark navy background, national geographic wildlife photography, 8k", f"cartoon, cute, kitten, sleeping, {N}"),
    ("sprites/enemies/cat-crouch.png", "photorealistic domestic tabby cat in low hunting crouch, side profile, every muscle tensed and visible under fur, eyes locked forward with dilated pupils, tail straight and low, ready to explode into pounce, night lighting, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, relaxed, {N}"),
    ("sprites/enemies/cat-pounce.png", "photorealistic domestic tabby cat mid-pounce frozen in air, side profile, front paws extended with claws out, back legs fully extended from push-off, body stretched long, intense focused expression, dynamic action shot, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, sitting, relaxed, {N}"),
    ("sprites/enemies/cat-walk.png", "photorealistic domestic tabby cat in slow deliberate stalking walk, side profile, low body position, placing paws carefully, predatory focused gaze, detailed fur in dim light, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, running, playing, {N}"),

    # Crow (2 poses)
    ("sprites/enemies/crow-fly.png", "photorealistic large black crow in powerful flight, side profile, wings fully spread showing feather detail, glossy iridescent black plumage, sharp dark beak, intelligent eye, dramatic lighting, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, colorful, parrot, {N}"),
    ("sprites/enemies/crow-dive.png", "photorealistic large black crow in aggressive diving attack, side profile, wings swept back, talons extended forward, beak open, terrifying angle of attack, dramatic lighting, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, perched, gentle, {N}"),

    # Wasp
    ("sprites/enemies/wasp-fly.png", "photorealistic paper wasp in aggressive flight, side profile, translucent wings with motion blur, prominent stinger extended, vivid yellow and black banding, compound eyes visible, extreme macro photography, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, cute, bee on flower, {N}"),

    # Fish
    ("sprites/enemies/fish-jump.png", "photorealistic large rainbow trout leaping dramatically from water, side profile, mouth wide open, water droplets spraying in arc around body, iridescent scales catching light, powerful muscular body, frozen action, isolated on solid #0A0A28 dark navy background, nature photography, 8k", f"cartoon, goldfish, small, aquarium, {N}"),

    # Owl (2 poses)
    ("sprites/enemies/owl-fly.png", "photorealistic great horned owl in silent flight, side profile, enormous wingspan fully extended, each feather individually detailed, massive talons hanging below, piercing bright yellow eyes staring directly, moonlight on feathers, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, baby owl, {N}"),
    ("sprites/enemies/owl-swoop.png", "photorealistic great horned owl in steep attack dive, side profile, wings pulled back, enormous talons reaching forward, intense predatory yellow eyes, feathers swept by wind, terrifying and beautiful, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, perched, {N}"),

    # Eagle (2 poses)
    ("sprites/enemies/eagle-fly.png", "photorealistic golden eagle soaring majestically, side profile, massive wingspan at least 2 meters, every feather detailed, golden-brown plumage catching sunlight, fierce curved beak, powerful build, king of the sky, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, bald eagle, small bird, {N}"),
    ("sprites/enemies/eagle-dive.png", "photorealistic golden eagle in terrifying hunting stoop, side profile, wings completely folded against body, talons extended forward like weapons, incredible speed captured, mountain context, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, gentle, slow, {N}"),

    # Storm Cloud Boss (2 states)
    ("sprites/enemies/storm-main.png", "massive towering cumulonimbus thundercloud formation, side view, dark grey-purple interior with visible internal turbulence, multiple lightning bolts branching inside illuminating cloud structure, suggestion of angry face formed by vortex patterns, heavy rain curtain falling below, electric purple and deep blue tones, terrifying scale, isolated on solid #000000 black background, 8k", f"cartoon, white fluffy, friendly, cute, {N}"),
    ("sprites/enemies/storm-rage.png", "extreme rage state thunderstorm cloud boss, violent swirling vortex forming clear angry face shape, lightning bolts for eyes crackling with energy, wind-torn edges, debris and ice swirling around, multiple lightning strikes below, maximum fury, apocalyptic, isolated on solid #000000 black background, 8k", f"cartoon, friendly, cute, calm, {N}"),
]

OBJECTS = [
    # Hazards
    ("sprites/hazards/fire-campfire.png", "photorealistic small campfire, side view, dancing orange and yellow flames with detailed tips, pile of red hot glowing embers, thin smoke wisps rising, crossed wood logs with bark detail, warm light radiating, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, large explosion, {N}"),
    ("sprites/hazards/fire-candle.png", "photorealistic lit beeswax candle with warm dancing flame, side view, melting wax dripping down sides, gentle warm glow, isolated on solid #0A0A28 dark navy background, product photography, 8k", f"cartoon, {N}"),

    # Garden objects
    ("sprites/objects/sprinkler.png", "photorealistic garden oscillating sprinkler, side view, metal and green plastic, beautiful arc of water spray with individual droplets catching light, wet grass around base, isolated on solid #0A0A28 dark navy background, product photography, 8k", f"cartoon, industrial, {N}"),
    ("sprites/objects/fence-picket.png", "photorealistic section of classic white picket fence, side view, charming weathered paint with character, detailed wood grain, slightly crooked post, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, metal, new, {N}"),
    ("sprites/objects/fence-wood.png", "photorealistic rustic wooden garden fence panel, side view, natural brown aged wood with beautiful grain pattern, horizontal slats with gaps, moss growing at base, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, metal, chain link, {N}"),
    ("sprites/objects/bush-round.png", "photorealistic perfectly round topiary garden bush, side view, dense vivid green leaves, freshly trimmed spherical shape, isolated on solid #0A0A28 dark navy background, garden photography, 8k", f"cartoon, dead, brown, {N}"),
    ("sprites/objects/bush-wild.png", "photorealistic wild natural garden bush with small white flowers, side view, organic uneven shape, rich green leaves, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, trimmed, {N}"),
    ("sprites/objects/flowers.png", "photorealistic beautiful cluster of garden wildflowers, side view, mixed colorful daisies cosmos and black-eyed susans, green stems and leaves, vibrant petals, isolated on solid #0A0A28 dark navy background, botanical photography, 8k", f"cartoon, single, bouquet, {N}"),
    ("sprites/objects/mushrooms.png", "photorealistic cluster of small forest mushrooms growing from mossy ground, side view, brown caps with white spots, delicate white stems, tiny dewdrops, macro photography, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, giant, psychedelic, {N}"),
    ("sprites/objects/stone.png", "photorealistic natural garden stepping stone, three quarter view, smooth grey river stone, patches of green moss on edges, organic rounded shape, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, brick, {N}"),

    # Collectible
    ("sprites/collectibles/firefly.png", "single firefly insect emitting beautiful bright warm yellow-green bioluminescent glow, extreme macro photography, translucent delicate veined wings, small dark body with glowing abdomen, magical halo of light around it, isolated on solid #000000 pure black background, enchanting, 8k", f"cartoon, butterfly, moth, multiple, swarm, {N}"),
]

UI_ASSETS = [
    ("ui/menu-bg.png",
     "masterpiece, photorealistic child's wooden study desk photographed from directly above, scattered sheets of white paper with fold marks, colorful pencils and crayons arranged messily, several hand-folded origami paper airplanes and boats in white paper, warm brass desk lamp casting golden pool of light, cozy bedroom atmosphere with wooden texture, nostalgic warm feeling, top-down flat lay photography, 8k ultra detailed",
     f"cartoon, messy room, dark, {N}, hands, fingers"),
    ("ui/world-map.png",
     "masterpiece, beautifully hand-illustrated treasure map on aged yellowed parchment paper, charming dotted trail path winding from garden with tiny house at bottom-left up through hills and trees in middle section to mountains then through clouds to stars at top-right, small watercolor illustrations along the path, compass rose, torn edges, coffee stain, vintage cartography style, warm sepia tones, 8k ultra detailed",
     f"photograph, digital, modern, clean, {N}"),
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
        log("x No SDXL checkpoint found (>2GB)")
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
        resp = urllib.request.urlopen(f"http://{COMFYUI_URL}/system_stats")
        data = json.loads(resp.read())
        vram = data.get("devices", [{}])[0].get("vram_total", 0) / 1024**3
        log(f"  ComfyUI connected | VRAM: {vram:.1f} GB")
        return True
    except:
        log(f"x ComfyUI not running at {COMFYUI_URL}")
        log("  Start it: cd ComfyUI && python main.py")
        return False

def main():
    global LOG_FILE
    print()
    print("=" * 60)
    print("  W I L D F O L D")
    print("  Premium Art Pipeline")
    print("  Best-of-4 | Upscale | Color Grade | Smart BG Remove")
    print("=" * 60)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = ASSETS_DIR / "generation_log.txt"
    with open(LOG_FILE, "w") as f:
        f.write(f"Wildfold Art Generation - {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    if not test_connection():
        sys.exit(1)
    if not detect_checkpoint():
        sys.exit(1)

    n_assets = len(BACKGROUNDS) + len(CHARACTERS) + len(ENEMIES) + len(OBJECTS) + len(UI_ASSETS)
    n_total_gens = n_assets * CANDIDATES
    est_sec = n_total_gens * 22  # ~22s per SDXL image on 3080 Ti
    est_hrs = est_sec / 3600

    log(f"\n  Quality mode: Best of {CANDIDATES} candidates per asset")
    log(f"  Total assets: {n_assets}")
    log(f"    Backgrounds: {len(BACKGROUNDS)} (upscale to {BG_UPSCALE_WIDTH}x{BG_UPSCALE_HEIGHT} + color grade)")
    log(f"    Characters:  {len(CHARACTERS)} (bg remove + trim + resize to {SPRITE_FINAL_SIZE}px)")
    log(f"    Enemies:     {len(ENEMIES)} (bg remove + trim + resize to {ENEMY_FINAL_SIZE}px)")
    log(f"    Objects:     {len(OBJECTS)} (bg remove + trim + resize)")
    log(f"    UI:          {len(UI_ASSETS)} (upscale)")
    log(f"  Total generations: {n_total_gens}")
    log(f"  Estimated time: ~{est_hrs:.1f} hours")
    log(f"  Output: {ASSETS_DIR.absolute()}")

    input(f"\n  Press ENTER to start ({n_total_gens} images to generate)...")

    start = time.time()
    done = 0

    try:
        # BACKGROUNDS
        log(f"\n{'='*60}")
        log(f"  PHASE 1/5: BACKGROUNDS ({len(BACKGROUNDS)} assets)")
        log(f"{'='*60}")
        for i, (path, prompt, neg, world) in enumerate(BACKGROUNDS):
            done += 1
            log(f"\n[{done}/{n_assets}] {path}")
            gen_background(path, prompt, neg, world)

        # CHARACTERS
        log(f"\n{'='*60}")
        log(f"  PHASE 2/5: CHARACTERS ({len(CHARACTERS)} assets)")
        log(f"{'='*60}")
        for i, (path, prompt) in enumerate(CHARACTERS):
            done += 1
            log(f"\n[{done}/{n_assets}] {path}")
            gen_sprite(path, prompt, SPRITE_NEG, SPRITE_FINAL_SIZE)

        # ENEMIES
        log(f"\n{'='*60}")
        log(f"  PHASE 3/5: ENEMIES ({len(ENEMIES)} assets)")
        log(f"{'='*60}")
        for i, (path, prompt, neg) in enumerate(ENEMIES):
            done += 1
            log(f"\n[{done}/{n_assets}] {path}")
            bg = BG_COLOR_BLACK if "storm" in path else BG_COLOR_NAVY
            gen_sprite(path, prompt, neg, ENEMY_FINAL_SIZE, bg)

        # OBJECTS
        log(f"\n{'='*60}")
        log(f"  PHASE 4/5: OBJECTS ({len(OBJECTS)} assets)")
        log(f"{'='*60}")
        for i, (path, prompt, neg) in enumerate(OBJECTS):
            done += 1
            log(f"\n[{done}/{n_assets}] {path}")
            bg = BG_COLOR_BLACK if "firefly" in path else BG_COLOR_NAVY
            gen_sprite(path, prompt, neg, OBJECT_FINAL_SIZE, bg)

        # UI
        log(f"\n{'='*60}")
        log(f"  PHASE 5/5: UI ({len(UI_ASSETS)} assets)")
        log(f"{'='*60}")
        for i, (path, prompt, neg) in enumerate(UI_ASSETS):
            done += 1
            log(f"\n[{done}/{n_assets}] {path}")
            gen_ui_image(path, prompt, neg)

    except KeyboardInterrupt:
        log("\n\n  Interrupted by user. Partial results saved.")
    except Exception as e:
        log(f"\n\n  Error: {e}")
        import traceback
        traceback.print_exc()

    elapsed = time.time() - start
    n_files = sum(1 for _ in ASSETS_DIR.rglob("*.png"))

    summary = f"""
{'='*60}
  GENERATION COMPLETE

  Images saved:    {n_files}
  Succeeded:       {STATS['ok']}
  Failed:          {STATS['fail']}
  Total candidates generated: {STATS['total_candidates']}
  Time:            {int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s
  Output:          {ASSETS_DIR.absolute()}
  Log:             {LOG_FILE}

  Next steps:
    git add assets/
    git commit -m "Add production art assets"
    git push
{'='*60}
"""
    log(summary)

if __name__ == "__main__":
    main()
