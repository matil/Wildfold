#!/usr/bin/env python3
"""
WILDFOLD - Premium Art Pipeline v2 (Parallax-Correct)
======================================================
Properly generates parallax-compatible game art:
- FAR layers: side-view horizon sky, tileable, fully opaque
- MID layers: side-view main scene, the hero background, fully opaque
- FOREGROUND: individual transparent objects placed in-engine (NOT full scenes)
- SPRITES: characters, enemies, objects with auto bg-removal

SETUP:
  1. Start ComfyUI: cd ComfyUI && python main.py
  2. python generate_all_art.py
  3. Sleep. ~3-4 hours on RTX 3080 Ti.
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
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
from scipy import ndimage

# ============================================================================
# CONFIG
# ============================================================================

COMFYUI_URL = "127.0.0.1:8188"
CLIENT_ID = str(uuid.uuid4())
CHECKPOINT = None
COMFYUI_MODELS_PATH = r"C:\Users\Mati\Downloads\AI\ComfyUI\models\checkpoints"
ASSETS_DIR = Path("./assets")

BG_WIDTH = 1344
BG_HEIGHT = 768
BG_FINAL_W = 1920
BG_FINAL_H = 1080
SPRITE_GEN = 1024
SPRITE_FINAL = 512
ENEMY_FINAL = 512
OBJ_FINAL = 384

STEPS = 35
CFG = 7.5
SPRITE_CFG = 6.0
SAMPLER = "dpmpp_2m"
SCHEDULER = "karras"
CANDIDATES = 4

BG_NAVY = (10, 10, 40)
BG_BLACK = (0, 0, 0)
BG_TOL = 45

GNEG = (
    "text, watermark, signature, logo, username, blurry, out of focus, "
    "low quality, low resolution, jpeg artifacts, deformed, disfigured, "
    "mutated, ugly, duplicate, error, cropped, worst quality, "
    "nsfw, nudity, person, human, hands, fingers"
)

# ============================================================================
# PER-WORLD COLOR GRADING
# ============================================================================

GRADE = {
    "garden":       {"brightness": 0.95, "contrast": 1.1,  "saturation": 1.05, "temp": (-5,-3,10),  "tint": (20,25,50),  "tint_a": 0.08},
    "neighborhood": {"brightness": 1.0,  "contrast": 1.05, "saturation": 0.95, "temp": (10,5,-5),   "tint": (50,35,20),  "tint_a": 0.06},
    "park":         {"brightness": 0.98, "contrast": 1.0,  "saturation": 0.9,  "temp": (-3,-2,-2),  "tint": (40,42,45),  "tint_a": 0.05},
    "stream":       {"brightness": 1.05, "contrast": 1.1,  "saturation": 1.15, "temp": (-5,8,-3),   "tint": (15,35,20),  "tint_a": 0.05},
    "forest":       {"brightness": 0.85, "contrast": 1.15, "saturation": 0.9,  "temp": (-8,-2,5),   "tint": (10,18,15),  "tint_a": 0.1},
    "mountain":     {"brightness": 1.1,  "contrast": 1.2,  "saturation": 0.95, "temp": (-3,-3,5),   "tint": (35,38,50),  "tint_a": 0.04},
    "sky":          {"brightness": 1.0,  "contrast": 1.15, "saturation": 1.1,  "temp": (-5,-5,15),  "tint": (5,8,30),    "tint_a": 0.08},
}

STYLE = {
    "garden":       "masterpiece, award-winning photography, magical atmosphere, cinematic lighting, volumetric firefly light, dark moody night, ",
    "neighborhood": "masterpiece, cinematic photography, golden hour dusk, warm streetlamp glow, nostalgic autumn, ",
    "park":         "masterpiece, cinematic photography, overcast diffused light, moody grey sky, lush green, ",
    "stream":       "masterpiece, nature photography, dappled sunlight, crystal water, lush green forest, vibrant, ",
    "forest":       "masterpiece, dark atmospheric photography, deep shadows, volumetric fog, mysterious ancient woodland, ",
    "mountain":     "masterpiece, epic landscape photography, dramatic clouds, vast scale, harsh alpine light, ",
    "sky":          "masterpiece, aerospace photography, ethereal, cosmic lighting, vast infinite space, transcendent, ",
    "sprite":       "masterpiece, product photography, studio lighting, crisp sharp focus, clean edges, professional, ",
}

# ============================================================================
# COMFYUI API
# ============================================================================

def queue_prompt(wf):
    data = json.dumps({"prompt": wf, "client_id": CLIENT_ID}).encode()
    req = urllib.request.Request(f"http://{COMFYUI_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["prompt_id"]

def wait_images(pid):
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_URL}/ws?clientId={CLIENT_ID}")
    while True:
        out = ws.recv()
        if isinstance(out, str):
            msg = json.loads(out)
            if msg["type"] == "executing" and msg["data"]["node"] is None and msg["data"]["prompt_id"] == pid:
                break
    ws.close()
    resp = urllib.request.urlopen(f"http://{COMFYUI_URL}/history/{pid}")
    hist = json.loads(resp.read())[pid]
    imgs = []
    for no in hist["outputs"].values():
        if "images" in no:
            for im in no["images"]:
                url = f"http://{COMFYUI_URL}/view?filename={urllib.parse.quote(im['filename'])}&subfolder={urllib.parse.quote(im.get('subfolder',''))}&type={im['type']}"
                imgs.append(urllib.request.urlopen(url).read())
    return imgs

def build_wf(pos, neg, w, h, seed=-1, steps=STEPS, cfg=CFG):
    if seed == -1: seed = int.from_bytes(os.urandom(4), "big")
    return {
        "3": {"inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": SAMPLER,
              "scheduler": SCHEDULER, "denoise": 1.0, "model": ["4",0], "positive": ["6",0],
              "negative": ["7",0], "latent_image": ["5",0]}, "class_type": "KSampler"},
        "4": {"inputs": {"ckpt_name": CHECKPOINT}, "class_type": "CheckpointLoaderSimple"},
        "5": {"inputs": {"width": w, "height": h, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "6": {"inputs": {"text": pos, "clip": ["4",1]}, "class_type": "CLIPTextEncode"},
        "7": {"inputs": {"text": neg, "clip": ["4",1]}, "class_type": "CLIPTextEncode"},
        "8": {"inputs": {"samples": ["3",0], "vae": ["4",2]}, "class_type": "VAEDecode"},
        "9": {"inputs": {"filename_prefix": "wf", "images": ["8",0]}, "class_type": "SaveImage"},
    }

# ============================================================================
# IMAGE PROCESSING
# ============================================================================

def quality_score(img):
    g = np.array(img.convert("L"), dtype=np.float64)
    lap = float(np.var(ndimage.laplace(g)))
    sx = ndimage.sobel(g, axis=0); sy = ndimage.sobel(g, axis=1)
    edge = float(np.mean(np.hypot(sx, sy)))
    return lap * 0.5 + edge * 0.3 + float(np.std(g)) * 0.2

def pick_best(imgs):
    if len(imgs) <= 1: return imgs[0] if imgs else None
    return max(imgs, key=quality_score)

def remove_bg(img, bg_col=BG_NAVY, tol=BG_TOL):
    img = img.convert("RGBA")
    d = np.array(img, dtype=np.float64)
    dist = np.sqrt((d[:,:,0]-bg_col[0])**2 + (d[:,:,1]-bg_col[1])**2 + (d[:,:,2]-bg_col[2])**2)
    soft = tol * 0.6
    alpha = np.clip((dist - (tol - soft)) / soft, 0, 1) * 255
    # Edge preservation
    grey = np.array(img.convert("L"), dtype=np.float64)
    edges = ndimage.sobel(grey)
    edge_mask = edges > np.percentile(edges, 85)
    hard = dist > tol
    alpha[edge_mask & hard] = 255
    result = np.array(img)
    result[:,:,3] = alpha.astype(np.uint8)
    # Fill holes
    subject = alpha > 128
    from scipy.ndimage import binary_fill_holes
    filled = binary_fill_holes(subject)
    result[filled & ~subject, 3] = 255
    return Image.fromarray(result)

def trim(img, pad=4):
    if img.mode != "RGBA": return img
    bb = img.getbbox()
    if not bb: return img
    return img.crop((max(0,bb[0]-pad), max(0,bb[1]-pad), min(img.width,bb[2]+pad), min(img.height,bb[3]+pad)))

def color_grade(img, world):
    if world not in GRADE: return img
    g = GRADE[world]
    img = ImageEnhance.Brightness(img).enhance(g["brightness"])
    img = ImageEnhance.Contrast(img).enhance(g["contrast"])
    img = ImageEnhance.Color(img).enhance(g["saturation"])
    d = np.array(img).astype(np.float64)
    ch = min(3, d.shape[2]) if len(d.shape) == 3 else 0
    if ch:
        for c in range(ch): d[:,:,c] = np.clip(d[:,:,c] + g["temp"][c], 0, 255)
        if g["tint_a"] > 0:
            t = np.array(g["tint"], dtype=np.float64)
            o = g["tint_a"]
            for c in range(ch): d[:,:,c] = d[:,:,c] * (1-o) + t[c] * o * 255 / max(max(t), 1)
    return Image.fromarray(np.clip(d, 0, 255).astype(np.uint8))

def sharpen(img, amt=1.3):
    return ImageEnhance.Sharpness(img).enhance(amt)

# ============================================================================
# GENERATION FUNCTIONS
# ============================================================================

LOG = None
STATS = {"ok": 0, "fail": 0, "gens": 0}

def log(m):
    print(m)
    if LOG:
        with open(LOG, "a") as f: f.write(f"{time.strftime('%H:%M:%S')} {m}\n")

def gen_candidates(pos, neg, w, h, n=CANDIDATES, cfg=CFG):
    neg_full = f"{neg}, {GNEG}" if neg else GNEG
    cands = []
    for i in range(n):
        try:
            pid = queue_prompt(build_wf(pos, neg_full, w, h, cfg=cfg))
            imgs = wait_images(pid)
            if imgs: cands.append(Image.open(BytesIO(imgs[0])))
            STATS["gens"] += 1
            time.sleep(0.3)
        except Exception as e:
            log(f"    cand {i+1} err: {e}")
    return cands

def gen_bg(path, prompt, neg, world):
    p = ASSETS_DIR / path; p.parent.mkdir(parents=True, exist_ok=True)
    full = STYLE.get(world, "") + prompt
    log(f"    {CANDIDATES} candidates...")
    cands = gen_candidates(full, neg, BG_WIDTH, BG_HEIGHT)
    if not cands: log(f"  x FAIL {p.name}"); STATS["fail"] += 1; return
    best = pick_best(cands)
    best = best.resize((BG_FINAL_W, BG_FINAL_H), Image.LANCZOS)
    best = color_grade(best, world)
    best = sharpen(best, 1.2)
    best.save(p, "PNG"); log(f"  OK {p}"); STATS["ok"] += 1

def gen_sprite(path, prompt, neg, size=SPRITE_FINAL, bg=BG_NAVY):
    p = ASSETS_DIR / path; p.parent.mkdir(parents=True, exist_ok=True)
    full = STYLE.get("sprite", "") + prompt
    log(f"    {CANDIDATES} candidates...")
    cands = gen_candidates(full, neg, SPRITE_GEN, SPRITE_GEN, cfg=SPRITE_CFG)
    if not cands: log(f"  x FAIL {p.name}"); STATS["fail"] += 1; return
    best = pick_best(cands)
    best = remove_bg(best, bg)
    best = trim(best)
    best.thumbnail((size, size), Image.LANCZOS)
    if best.mode == "RGBA":
        rgb = sharpen(best.convert("RGB"), 1.4)
        r,g,b = rgb.split(); a = best.split()[3]
        best = Image.merge("RGBA", (r,g,b,a))
    best.save(p, "PNG"); log(f"  OK {p} ({best.size[0]}x{best.size[1]})"); STATS["ok"] += 1

def gen_ui(path, prompt, neg):
    p = ASSETS_DIR / path; p.parent.mkdir(parents=True, exist_ok=True)
    log(f"    {CANDIDATES} candidates...")
    cands = gen_candidates(prompt, neg, BG_WIDTH, BG_HEIGHT)
    if not cands: log(f"  x FAIL {p.name}"); STATS["fail"] += 1; return
    best = pick_best(cands)
    best = best.resize((BG_FINAL_W, BG_FINAL_H), Image.LANCZOS)
    best = sharpen(best, 1.2)
    best.save(p, "PNG"); log(f"  OK {p}"); STATS["ok"] += 1

# ============================================================================
# ASSET DEFINITIONS - PARALLAX-CORRECT
# ============================================================================

# CRITICAL PARALLAX RULES:
# - FAR (sky): horizontal panoramic, looking at horizon, SIDE VIEW, tileable
#   No ground. Just sky/clouds/distant mountains. Fully opaque.
# - MID (scene): side view main scene, the hero background. Ground + scenery.
#   Fully opaque. This is what the player sees most.
# - FOREGROUND: NOT a full scene. Individual objects as transparent sprites.
#   Placed in-engine. Ferns, grass, rocks, etc.
# ALL LAYERS SHARE THE SAME HORIZONTAL SIDE-VIEW PERSPECTIVE.

NN = "cartoon, anime, illustration, painting, sketch, drawing, 3d render, people, person, human, looking up, top down, bird eye, aerial, overhead, vertical"

BACKGROUNDS = [
    # ===== GARDEN =====
    # Far: night sky at horizon
    ("backgrounds/garden/garden-far.png",
     "panoramic night sky at horizon level, side view landscape format, stars scattered across deep blue-purple sky, thin crescent moon on upper right, wispy clouds near horizon, silhouette of distant houses and trees as a thin strip at very bottom, warm amber glow on horizon from distant city lights, horizontal composition, seamless tileable horizontally, 8k",
     f"looking up, overhead, ground, close-up, daytime, {NN}", "garden"),
    # Mid: main garden scene
    ("backgrounds/garden/garden-mid-1.png",
     "lush backyard garden at night, SIDE VIEW horizontal perspective like a 2D game background, left to right composition, dense flowering bushes roses hydrangeas, large oak tree with twisted branches, winding stone path with stepping stones, weathered wooden fence with climbing ivy, scattered glowing fireflies as warm orbs, dew on leaves, rich vegetation, ground visible at bottom, sky at top, 8k",
     f"looking up, top down, {NN}", "garden"),
    ("backgrounds/garden/garden-mid-2.png",
     "garden shed area at night, SIDE VIEW horizontal perspective like a 2D game level, charming wooden shed with warm window light, terracotta pots stacked outside, old watering can, ivy covered walls, brick path, garden tools leaning on wall, fireflies floating, ground at bottom sky at top, 8k",
     f"looking up, top down, {NN}", "garden"),
    ("backgrounds/garden/garden-mid-3.png",
     "garden pond area at night, SIDE VIEW horizontal perspective like a 2D platformer, small pond with lily pads and reflective surface, mossy rocks around edges, reeds and cattails, stepping stones crossing over water, ancient tree overhanging, fireflies reflecting in water, ground at bottom sky at top, 8k",
     f"looking up, top down, {NN}", "garden"),

    # ===== NEIGHBORHOOD =====
    ("backgrounds/neighborhood/neighborhood-far.png",
     "panoramic suburban sunset sky at horizon level, side view landscape, spectacular orange pink purple sunset gradient, silhouette of distant rooftops and church steeple at thin bottom strip, power line silhouettes crossing sky, first stars appearing in upper purple area, horizontal composition, seamless tileable, 8k",
     f"looking up, ground, close-up, noon, {NN}", "neighborhood"),
    ("backgrounds/neighborhood/neighborhood-mid-1.png",
     "quiet suburban street in autumn evening, SIDE VIEW horizontal perspective like a 2D game level, cracked sidewalk, charming houses in a row with lit windows, white picket fences, mailboxes, vintage parked car, warm streetlamp casting light pool, red gold autumn leaves on ground, wet pavement reflecting, ground at bottom sky at top, 8k",
     f"looking up, top down, aerial, {NN}", "neighborhood"),
    ("backgrounds/neighborhood/neighborhood-mid-2.png",
     "suburban alley between houses at dusk, SIDE VIEW horizontal perspective like 2D game, brick walls, garbage bins, bicycle leaning on wall, clothesline above, puddles on ground reflecting warm sky, autumn leaves, chain link fence section, ground at bottom sky at top, 8k",
     f"looking up, top down, {NN}", "neighborhood"),

    # ===== PARK =====
    ("backgrounds/park/park-far.png",
     "panoramic overcast sky at horizon level, side view landscape, layers of grey clouds with occasional warm light break, distant tree line silhouette at thin bottom strip, moody atmospheric, birds in distance, horizontal composition, seamless tileable, 8k",
     f"looking up, ground, close-up, clear blue, night, {NN}", "park"),
    ("backgrounds/park/park-mid-1.png",
     "beautiful public park on overcast day, SIDE VIEW horizontal perspective like 2D platformer, vast emerald grass field, wooden park bench, gravel path winding through, majestic scattered trees with full canopy, pond visible in distance, soft diffused overcast light, ground at bottom sky at top, 8k",
     f"looking up, top down, night, {NN}", "park"),
    ("backgrounds/park/park-mid-2.png",
     "park playground area overcast day, SIDE VIEW horizontal like 2D game, colorful slide and swing set, rubber mulch ground, sand pit, trees surrounding, bench nearby, overcast soft light, ground at bottom sky at top, 8k",
     f"looking up, top down, night, {NN}", "park"),
    ("backgrounds/park/park-mid-3.png",
     "park pond with dock overcast day, SIDE VIEW horizontal like 2D game, wooden dock extending into pond, ducks swimming, cattails and weeping willow, lily pads, gravel path along bank, ground at bottom sky at top, 8k",
     f"looking up, top down, night, {NN}", "park"),

    # ===== STREAM =====
    ("backgrounds/stream/stream-far.png",
     "panoramic forest canopy skyline at horizon, side view landscape, dense green treetops forming horizon line at bottom third, blue sky with scattered clouds above, golden sunbeams streaming through gaps between trees, atmospheric haze, horizontal composition, seamless tileable, 8k",
     f"looking up, ground level, close-up, night, {NN}", "stream"),
    ("backgrounds/stream/stream-mid-1.png",
     "crystal clear forest stream, SIDE VIEW horizontal like 2D platformer, rushing water over smooth rocks creating white ripples, large mossy boulders on banks, lush ferns cascading down, tall trees on both sides, dappled sunlight on water, small waterfall in background, ground and water at bottom sky through trees at top, 8k",
     f"looking up, top down, overhead, {NN}", "stream"),
    ("backgrounds/stream/stream-mid-2.png",
     "dramatic white water rapids section, SIDE VIEW horizontal like 2D game level, powerful current between large boulders, spray and mist, narrow rocky channel, overhanging mossy branches, dramatic light through mist, ground at bottom, 8k",
     f"looking up, top down, calm still, {NN}", "stream"),

    # ===== FOREST =====
    ("backgrounds/forest/forest-far.png",
     "panoramic dark forest skyline at horizon, side view landscape, dense dark treetop canopy forming thick horizon across bottom half, very dark moody sky above with thin light breaking through in one spot, mysterious fog layer between trees, horizontal composition, seamless tileable, 8k",
     f"bright, open sky, looking up, close-up, {NN}", "forest"),
    ("backgrounds/forest/forest-mid-1.png",
     "deep ancient forest interior, SIDE VIEW horizontal like 2D platformer, massive towering trees with trunks wider than houses, impenetrable canopy above creating deep shadow, single dramatic shaft of golden light, thick undergrowth ferns and moss, mysterious fog at ground level, ground at bottom dark canopy at top, 8k",
     f"looking up, top down, bright, meadow, {NN}", "forest"),
    ("backgrounds/forest/forest-mid-2.png",
     "dark forest at night, SIDE VIEW horizontal like 2D game, gnarled tree silhouettes, pair of glowing yellow owl eyes in tree hollow, thin moonbeams cutting through, few lonely fireflies, tangled roots, oppressive darkness, ground at bottom dark sky at top, 8k",
     f"looking up, top down, bright, daytime, {NN}", "forest"),

    # ===== MOUNTAIN =====
    ("backgrounds/mountain/mountain-far.png",
     "panoramic dramatic mountain sky at horizon, side view landscape, massive clouds lit from behind by sun creating god rays, distant snow-capped peaks as silhouettes at bottom strip, vast epic sky, horizontal composition, seamless tileable, 8k",
     f"looking up, ground, forest, flat, close-up, {NN}", "mountain"),
    ("backgrounds/mountain/mountain-mid-1.png",
     "dramatic mountain terrain, SIDE VIEW horizontal like 2D platformer, jagged granite cliff face with narrow ledge path, sparse alpine flowers in cracks, snow and ice patches, dramatic clouds at same level creating sense of extreme height, wind-bent dwarf trees, ground and rock at bottom sky at top, 8k",
     f"looking up, top down, forest, flat, {NN}", "mountain"),
    ("backgrounds/mountain/mountain-mid-2.png",
     "mountain in terrifying storm, SIDE VIEW horizontal like 2D game, dark apocalyptic clouds, lightning bolt striking nearby peak, horizontal rain, exposed rocky ridge, no shelter, raw power, ground at bottom dark sky at top, 8k",
     f"looking up, top down, sunny, calm, {NN}", "mountain"),

    # ===== SKY =====
    ("backgrounds/sky/sky-far.png",
     "edge of space panoramic at horizon level, side view landscape, thin glowing blue atmospheric line curving across bottom, transition from deep blue to pure black, thousands of crisp stars, visible milky way band, absolute vastness, horizontal composition, seamless tileable, 8k",
     f"ground, trees, buildings, airplane, clouds below, {NN}", "sky"),
    ("backgrounds/sky/sky-mid-1.png",
     "breathtaking view above cloud layer, SIDE VIEW horizontal like 2D platformer, towering cathedral cumulus cloud formations as platforms and pillars, golden pink sunset light illuminating cloud edges from below, deep cobalt sky above, stars becoming visible, cloud tops as terrain the player traverses, 8k",
     f"ground, buildings, airplane, looking up, {NN}", "sky"),
    ("backgrounds/sky/sky-mid-2.png",
     "inside massive thunderstorm cloud, SIDE VIEW horizontal like 2D game level, violent swirling dark interior lit by branching lightning, deep purple and electric blue, curtain of rain below, turbulent cloud walls as terrain, 8k",
     f"sunny, clear, ground, looking up, {NN}", "sky"),
]

# FOREGROUND OBJECTS - individual transparent sprites, placed in-engine
FOREGROUND = [
    # Garden foreground objects
    ("sprites/foreground/garden-grass-1.png", "single tuft of tall wild grass at night, side view, several blades with seed heads, dew drops catching moonlight, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    ("sprites/foreground/garden-grass-2.png", "single tall dandelion plant at night, side view, full seed puff ready to blow, long stem, leaves at base, isolated on solid #0A0A28 dark navy background, macro photography, 8k"),
    ("sprites/foreground/garden-fern.png", "single fern frond curling upward, side view, detailed green leaves with unfurling tip, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    ("sprites/foreground/garden-flower-1.png", "single wild rose bush branch, side view, pink flowers and buds, thorny stem, green leaves, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    ("sprites/foreground/garden-flower-2.png", "single cluster of white daisies, side view, 3 flowers on stems with leaves, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    # Stream foreground
    ("sprites/foreground/stream-fern.png", "single large lush fern plant, side view, multiple fronds cascading outward, rich green, water droplets on leaves, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    ("sprites/foreground/stream-rock.png", "single mossy river boulder, side view, smooth grey stone covered in bright green moss, wet glistening surface, isolated on solid #0A0A28 dark navy background, 8k"),
    ("sprites/foreground/stream-reeds.png", "cluster of tall river reeds, side view, thin green stems with brown seed heads at top, isolated on solid #0A0A28 dark navy background, botanical photography, 8k"),
    # Forest foreground
    ("sprites/foreground/forest-mushroom.png", "cluster of glowing bioluminescent mushrooms, side view, pale caps with blue-green glow, growing from dark mossy log, isolated on solid #0A0A28 dark navy background, 8k"),
    ("sprites/foreground/forest-root.png", "single thick gnarled tree root emerging from ground, side view, covered in moss, twisting shape, isolated on solid #0A0A28 dark navy background, 8k"),
    ("sprites/foreground/forest-branch.png", "single hanging tree branch with moss and lichen, side view, drooping with small ferns growing on it, isolated on solid #0A0A28 dark navy background, 8k"),
    # Mountain foreground
    ("sprites/foreground/mountain-rock.png", "single jagged alpine rock formation, side view, grey granite with lichen patches, small crack with alpine flower, isolated on solid #0A0A28 dark navy background, 8k"),
    ("sprites/foreground/mountain-snow.png", "single snow-covered rock ledge, side view, ice crystals on edge, small icicles hanging below, isolated on solid #0A0A28 dark navy background, 8k"),
    # Sky foreground
    ("sprites/foreground/sky-cloud-wisp.png", "single thin wispy cirrus cloud tendril, side view, delicate ice crystal structure, slight rainbow refraction, isolated on solid #000000 pure black background, 8k"),
]

SPRITE_NEG = f"realistic metal airplane, plastic toy, colored paper, real bird, real frog, feathers, green slimy, {NN}"

CHARACTERS = [
    ("sprites/plane/plane-idle.png", "single white paper airplane, hand-folded origami, visible sharp fold creases, slightly worn paper texture with fiber detail, soft warm amber glow from within through translucent paper, resting on surface nose raised, perfect side profile, isolated on solid #0A0A28 dark navy background, product photography, studio lighting, 8k"),
    ("sprites/plane/plane-glide.png", "single white paper airplane in graceful flight, origami, fold creases, wings spread slight upward angle, subtle motion blur on tips, warm inner glow through paper, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-dive.png", "single white paper airplane steep dive, origami, nose pointing sharply down, aerodynamic, fold creases, speed feeling, side profile, warm glow, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-slide.png", "single white paper airplane sliding along surface, origami, belly touching ground, forward lean momentum, fold creases, side profile, warm glow, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-jump.png", "single white paper airplane launching upward 45 degrees, origami, dynamic lifting full of energy, fold creases, warm glow intensifying, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-wet.png", "single white paper airplane drooping crumpled from moisture, darker wet spots, wings sagging, melancholy, fold lines softened by water, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-dry.png", "single white paper airplane pristine crisp, perfectly sharp folds, glowing bright warm gold within, confident upward angle, fresh strong paper, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/plane/plane-hit.png", "single white paper airplane with damage, small tear on wing, crumpled nose, one wing bent, battle-worn, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-idle.png", "single white paper origami boat, classic shape, fold creases, floating on calm water with reflection, warm amber glow within, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-moving.png", "single white paper origami boat moving forward through water, forward lean, V-shaped wake behind, ripples around hull, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-rocking.png", "single white paper origami boat tilted on choppy water, splash against hull, rocking motion, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/boat/boat-transform.png", "white paper mid-fold between airplane and boat shape, magical transformation, glowing warm light at every fold point, geometric transitional, side profile, isolated on solid #0A0A28 dark navy background, 8k"),
    ("sprites/frog/frog-crouch.png", "single white paper origami frog, crouching coiled to spring, geometric fold creases, warm amber glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/frog/frog-jump.png", "single white paper origami frog peak of jump, legs extended below, airborne dynamic, fold creases, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/frog/frog-land.png", "single white paper origami frog landing legs compressed, slight crumple on impact, fold creases, glow dimming, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/crane/crane-glide.png", "single white paper origami crane, traditional Japanese, wings fully spread soaring glide, geometric folds, elegant majestic, warm amber glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/crane/crane-flap.png", "single white paper origami crane wings downward mid-flap gaining altitude, dynamic, fold creases, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
    ("sprites/crane/crane-perch.png", "single white paper origami crane standing tall one leg, wings folded at sides, serene elegant, fold creases, warm glow, side profile, isolated on solid #0A0A28 dark navy background, studio photography, 8k"),
]

ENEMIES = [
    ("sprites/enemies/cat-idle.png", "photorealistic tabby cat sitting alert, side profile, ears forward, bright green eyes, detailed fur, tail curled, night lighting, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, kitten, sleeping, {NN}"),
    ("sprites/enemies/cat-crouch.png", "photorealistic tabby cat low hunting crouch, side profile, muscles tensed, dilated pupils, tail low, ready to pounce, night, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, relaxed, {NN}"),
    ("sprites/enemies/cat-pounce.png", "photorealistic tabby cat mid-pounce in air, side profile, paws extended claws out, body stretched, intense, dynamic action, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, sitting, {NN}"),
    ("sprites/enemies/cat-walk.png", "photorealistic tabby cat stalking walk, side profile, low body, careful steps, predatory gaze, dim light, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, running, {NN}"),
    ("sprites/enemies/crow-fly.png", "photorealistic black crow powerful flight, side profile, wings spread, glossy iridescent plumage, sharp beak, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, colorful, {NN}"),
    ("sprites/enemies/crow-dive.png", "photorealistic black crow aggressive dive attack, side profile, wings swept, talons forward, beak open, terrifying, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, gentle, {NN}"),
    ("sprites/enemies/wasp-fly.png", "photorealistic paper wasp aggressive flight, side profile, wings motion blur, stinger extended, yellow black bands, macro, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, cute bee, {NN}"),
    ("sprites/enemies/fish-jump.png", "photorealistic large trout leaping from water, side profile, mouth open, water spray arc, iridescent scales, powerful, frozen action, isolated on solid #0A0A28 dark navy background, nature photography, 8k", f"cartoon, goldfish, small, {NN}"),
    ("sprites/enemies/owl-fly.png", "photorealistic great horned owl silent flight, side profile, enormous wingspan, feathers detailed, massive talons, piercing yellow eyes, moonlight, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, baby, {NN}"),
    ("sprites/enemies/owl-swoop.png", "photorealistic great horned owl steep attack dive, side profile, wings pulled back, talons reaching, predatory yellow eyes, feathers windswept, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, cute, {NN}"),
    ("sprites/enemies/eagle-fly.png", "photorealistic golden eagle soaring, side profile, massive wingspan, golden-brown plumage in sunlight, fierce beak, powerful, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, small bird, {NN}"),
    ("sprites/enemies/eagle-dive.png", "photorealistic golden eagle hunting stoop, side profile, wings folded, talons extended like weapons, incredible speed, isolated on solid #0A0A28 dark navy background, wildlife photography, 8k", f"cartoon, gentle, {NN}"),
    ("sprites/enemies/storm-main.png", "massive cumulonimbus thundercloud, side view, dark purple interior with turbulence, lightning branching inside, angry face in vortex patterns, rain curtain below, electric purple blue, terrifying scale, isolated on solid #000000 black background, 8k", f"cartoon, white fluffy, friendly, {NN}"),
    ("sprites/enemies/storm-rage.png", "rage state thunderstorm cloud boss, violent vortex forming clear angry face, lightning bolt eyes crackling, wind-torn edges, debris swirling, multiple lightning strikes, apocalyptic, isolated on solid #000000 black background, 8k", f"cartoon, friendly, cute, {NN}"),
]

OBJECTS = [
    ("sprites/hazards/fire-campfire.png", "photorealistic small campfire, side view, dancing orange yellow flames with tips, red hot embers, smoke wisps, crossed wood logs with bark, warm light, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, explosion, {NN}"),
    ("sprites/hazards/fire-candle.png", "photorealistic lit beeswax candle dancing flame, side view, melting wax dripping, warm glow, isolated on solid #0A0A28 dark navy background, product photography, 8k", f"cartoon, {NN}"),
    ("sprites/objects/sprinkler.png", "photorealistic garden sprinkler, side view, metal green plastic, water spray arc with droplets catching light, isolated on solid #0A0A28 dark navy background, product photography, 8k", f"cartoon, {NN}"),
    ("sprites/objects/fence-picket.png", "photorealistic white picket fence section, side view, weathered paint, wood grain, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, metal, {NN}"),
    ("sprites/objects/fence-wood.png", "photorealistic rustic wooden fence panel, side view, aged brown wood, horizontal slats, moss at base, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, metal, {NN}"),
    ("sprites/objects/bush-round.png", "photorealistic round topiary bush, side view, dense vivid green, freshly trimmed spherical, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, dead, {NN}"),
    ("sprites/objects/bush-wild.png", "photorealistic wild bush with small white flowers, side view, organic shape, rich green, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, {NN}"),
    ("sprites/objects/flowers.png", "photorealistic cluster wildflowers, side view, colorful daisies cosmos, green stems, vibrant petals, isolated on solid #0A0A28 dark navy background, botanical photography, 8k", f"cartoon, single, {NN}"),
    ("sprites/objects/mushrooms.png", "photorealistic cluster small forest mushrooms, side view, brown caps white spots, delicate stems, dewdrops, mossy base, macro, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, giant, {NN}"),
    ("sprites/objects/stone.png", "photorealistic natural stepping stone, three quarter view, smooth grey river stone, moss patches, organic shape, isolated on solid #0A0A28 dark navy background, 8k", f"cartoon, {NN}"),
    ("sprites/collectibles/firefly.png", "single firefly insect bright warm yellow-green bioluminescent glow, extreme macro, translucent veined wings, glowing abdomen, magical halo, isolated on solid #000000 pure black background, enchanting, 8k", f"cartoon, butterfly, moth, multiple, {NN}"),
]

UI_ASSETS = [
    ("ui/menu-bg.png", "masterpiece, photorealistic childs wooden desk from above, scattered white paper with folds, colorful pencils crayons, hand-folded origami airplanes and boats, warm brass desk lamp golden light, cozy bedroom, nostalgic, top-down flat lay, 8k", f"cartoon, dark, {NN}, hands, fingers"),
    ("ui/world-map.png", "masterpiece, hand-illustrated treasure map on aged parchment, dotted trail from garden bottom-left through hills trees mountains to stars top-right, small watercolor illustrations, compass rose, torn edges, vintage cartography, warm sepia, 8k", f"photograph, digital, modern, {NN}"),
]

# ============================================================================
# MAIN
# ============================================================================

def detect_ckpt():
    global CHECKPOINT
    if CHECKPOINT: return True
    d = Path(COMFYUI_MODELS_PATH)
    if not d.exists():
        # Try alternate path
        alt = Path(r"C:\Users\Mati\Downloads\AI\ComfyUI\ComfyUI\models\checkpoints")
        if alt.exists(): d = alt
        else: log(f"x Models dir not found: {COMFYUI_MODELS_PATH}"); return False
    cks = [f for f in d.glob("*.safetensors") if f.stat().st_size > 2_000_000_000]
    if not cks:
        log("x No SDXL checkpoint (>2GB)")
        log("  https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors")
        return False
    for p in ["realvis","juggernaut","dreamshar","sdxl"]:
        for c in cks:
            if p in c.name.lower(): CHECKPOINT = c.name; log(f"  Model: {CHECKPOINT} ({c.stat().st_size/1024**3:.1f}GB)"); return True
    CHECKPOINT = cks[0].name; log(f"  Model: {CHECKPOINT}"); return True

def test_conn():
    try:
        r = urllib.request.urlopen(f"http://{COMFYUI_URL}/system_stats")
        d = json.loads(r.read()); v = d.get("devices",[{}])[0].get("vram_total",0)/1024**3
        log(f"  ComfyUI connected | VRAM: {v:.1f} GB"); return True
    except: log(f"x ComfyUI not running at {COMFYUI_URL}"); return False

def main():
    global LOG
    print("\n" + "="*60)
    print("  W I L D F O L D")
    print("  Premium Art Pipeline v2 (Parallax-Correct)")
    print("  Best-of-4 | Upscale | Color Grade | Smart BG Remove")
    print("="*60)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LOG = ASSETS_DIR / "generation_log.txt"
    with open(LOG, "w") as f: f.write(f"Wildfold Art Gen v2 - {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

    if not test_conn(): sys.exit(1)
    if not detect_ckpt(): sys.exit(1)

    all_assets = len(BACKGROUNDS) + len(FOREGROUND) + len(CHARACTERS) + len(ENEMIES) + len(OBJECTS) + len(UI_ASSETS)
    total_gens = all_assets * CANDIDATES
    est = total_gens * 22 / 3600

    log(f"\n  Quality: Best of {CANDIDATES} per asset")
    log(f"  Total assets: {all_assets}")
    log(f"    BG far+mid:  {len(BACKGROUNDS)} (upscale {BG_FINAL_W}x{BG_FINAL_H} + color grade)")
    log(f"    FG objects:  {len(FOREGROUND)} (transparent sprites for in-engine placement)")
    log(f"    Characters:  {len(CHARACTERS)} (bg-remove + trim + {SPRITE_FINAL}px)")
    log(f"    Enemies:     {len(ENEMIES)} (bg-remove + trim + {ENEMY_FINAL}px)")
    log(f"    Objects:     {len(OBJECTS)} (bg-remove + trim)")
    log(f"    UI:          {len(UI_ASSETS)}")
    log(f"  Total gens: {total_gens}")
    log(f"  Est. time: ~{est:.1f} hours")

    input(f"\n  Press ENTER to start...")

    start = time.time()
    done = 0

    try:
        log(f"\n{'='*60}\n  PHASE 1: BACKGROUNDS ({len(BACKGROUNDS)})\n{'='*60}")
        for path, prompt, neg, world in BACKGROUNDS:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            gen_bg(path, prompt, neg, world)

        log(f"\n{'='*60}\n  PHASE 2: FOREGROUND OBJECTS ({len(FOREGROUND)})\n{'='*60}")
        fg_neg = f"realistic, {NN}"
        for path, prompt in FOREGROUND:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            gen_sprite(path, prompt, fg_neg, 384)

        log(f"\n{'='*60}\n  PHASE 3: CHARACTERS ({len(CHARACTERS)})\n{'='*60}")
        for path, prompt in CHARACTERS:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            gen_sprite(path, prompt, SPRITE_NEG, SPRITE_FINAL)

        log(f"\n{'='*60}\n  PHASE 4: ENEMIES ({len(ENEMIES)})\n{'='*60}")
        for path, prompt, neg in ENEMIES:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            bg = BG_BLACK if "storm" in path else BG_NAVY
            gen_sprite(path, prompt, neg, ENEMY_FINAL, bg)

        log(f"\n{'='*60}\n  PHASE 5: OBJECTS ({len(OBJECTS)})\n{'='*60}")
        for path, prompt, neg in OBJECTS:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            bg = BG_BLACK if "firefly" in path else BG_NAVY
            gen_sprite(path, prompt, neg, OBJ_FINAL, bg)

        log(f"\n{'='*60}\n  PHASE 6: UI ({len(UI_ASSETS)})\n{'='*60}")
        for path, prompt, neg in UI_ASSETS:
            done += 1; log(f"\n[{done}/{all_assets}] {path}")
            gen_ui(path, prompt, neg)

    except KeyboardInterrupt:
        log("\n  Interrupted. Partial results saved.")
    except Exception as e:
        log(f"\n  Error: {e}")
        import traceback; traceback.print_exc()

    el = time.time() - start
    nf = sum(1 for _ in ASSETS_DIR.rglob("*.png"))
    log(f"\n{'='*60}")
    log(f"  DONE: {nf} images | {STATS['ok']} ok, {STATS['fail']} fail | {STATS['gens']} total gens")
    log(f"  Time: {int(el//3600)}h {int((el%3600)//60)}m {int(el%60)}s")
    log(f"  Output: {ASSETS_DIR.absolute()}")
    log(f"\n  Next: git add assets/ && git commit -m 'Add art' && git push")
    log(f"{'='*60}")

if __name__ == "__main__":
    main()
