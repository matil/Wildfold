#!/usr/bin/env python3
"""
WILDFOLD - Overnight Art Asset Generator
=========================================
Generates ALL game art assets via ComfyUI API.

SETUP:
  1. Start ComfyUI normally (python main.py --listen 0.0.0.0)
  2. Make sure you have an SDXL model loaded (Juggernaut XL, RealVisXL, or SDXL base)
  3. Run: python generate_all_art.py
  4. Go to sleep. Everything will be in ./output/ when you wake up.

REQUIREMENTS:
  pip install requests websocket-client Pillow

ESTIMATED TIME: 3-6 hours on RTX 3080 Ti (depending on model and settings)
ESTIMATED IMAGES: ~350-400 total generations
"""

import json
import os
import sys
import time
import uuid
import struct
import urllib.request
import urllib.parse
from pathlib import Path
from io import BytesIO

try:
    import websocket
except ImportError:
    print("Installing websocket-client...")
    os.system(f"{sys.executable} -m pip install websocket-client")
    import websocket

try:
    from PIL import Image
except ImportError:
    print("Installing Pillow...")
    os.system(f"{sys.executable} -m pip install Pillow")
    from PIL import Image

# ============================================================================
# CONFIGURATION - EDIT THESE TO MATCH YOUR SETUP
# ============================================================================

COMFYUI_URL = "127.0.0.1:8188"  # Default ComfyUI address
CLIENT_ID = str(uuid.uuid4())

# Your SDXL checkpoint filename (as it appears in ComfyUI)
# Change this to match your installed model
CHECKPOINT = "juggernautXL_v9Rundiffusionphoto2.safetensors"
# Alternatives:
# CHECKPOINT = "realvisxlV40_v40Bakedvae.safetensors"
# CHECKPOINT = "sd_xl_base_1.0.safetensors"

# Generation settings optimized for 3080 Ti 12GB
DEFAULT_WIDTH = 1344
DEFAULT_HEIGHT = 768
SPRITE_SIZE = 1024
DEFAULT_STEPS = 30
DEFAULT_CFG = 7.5
SAMPLER = "dpmpp_2m"
SCHEDULER = "karras"
BATCH_SIZE = 1  # Keep at 1 for reliability, increase to 2 if VRAM allows

# Number of variations per prompt
VARIATIONS_PER_BG = 3      # Background variations
VARIATIONS_PER_SPRITE = 4  # Character sprite variations (pick best)
VARIATIONS_PER_ENEMY = 3   # Enemy variations
VARIATIONS_PER_OBJECT = 2  # Object variations

# Output base directory
OUTPUT_DIR = Path("./output")

# Global negative prompt
GLOBAL_NEGATIVE = (
    "text, watermark, signature, logo, username, blurry, out of focus, "
    "low quality, low resolution, jpeg artifacts, deformed, disfigured, "
    "mutated, ugly, duplicate, error, cropped, worst quality, "
    "nsfw, nudity, person, human"
)

# ============================================================================
# COMFYUI API FUNCTIONS
# ============================================================================

def queue_prompt(prompt_workflow):
    """Send a workflow to ComfyUI and return the prompt_id."""
    p = {"prompt": prompt_workflow, "client_id": CLIENT_ID}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(
        f"http://{COMFYUI_URL}/prompt",
        data=data,
        headers={'Content-Type': 'application/json'}
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp['prompt_id']


def get_images(prompt_id):
    """Wait for generation to complete and return image data."""
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_URL}/ws?clientId={CLIENT_ID}")

    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break  # Generation complete
        else:
            continue  # Binary data (previews), skip

    ws.close()

    # Fetch the output images
    resp = urllib.request.urlopen(f"http://{COMFYUI_URL}/history/{prompt_id}")
    history = json.loads(resp.read())[prompt_id]

    images = []
    for node_id, node_output in history['outputs'].items():
        if 'images' in node_output:
            for img_data in node_output['images']:
                url = f"http://{COMFYUI_URL}/view?filename={urllib.parse.quote(img_data['filename'])}&subfolder={urllib.parse.quote(img_data.get('subfolder', ''))}&type={img_data['type']}"
                img_bytes = urllib.request.urlopen(url).read()
                images.append(img_bytes)

    return images


def build_workflow(positive, negative, width, height, seed=-1, steps=None, cfg=None, batch=None):
    """Build a standard txt2img ComfyUI workflow."""
    if seed == -1:
        seed = int.from_bytes(os.urandom(4), 'big')
    if steps is None:
        steps = DEFAULT_STEPS
    if cfg is None:
        cfg = DEFAULT_CFG
    if batch is None:
        batch = BATCH_SIZE

    workflow = {
        "3": {  # KSampler
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": SAMPLER,
                "scheduler": SCHEDULER,
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {  # Load Checkpoint
            "inputs": {
                "ckpt_name": CHECKPOINT
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {  # Empty Latent Image
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": batch
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {  # CLIP Text Encode (Positive)
            "inputs": {
                "text": positive,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {  # CLIP Text Encode (Negative)
            "inputs": {
                "text": negative,
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {  # VAE Decode
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {  # Save Image
            "inputs": {
                "filename_prefix": "wildfold",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }
    return workflow


def generate_and_save(positive, negative, width, height, save_dir, filename_base,
                       num_variations=1, seed_start=-1, steps=None, cfg=None):
    """Generate images and save them to disk."""
    save_dir = OUTPUT_DIR / save_dir
    save_dir.mkdir(parents=True, exist_ok=True)

    full_negative = f"{negative}, {GLOBAL_NEGATIVE}" if negative else GLOBAL_NEGATIVE

    for i in range(num_variations):
        seed = seed_start + i if seed_start > 0 else -1
        workflow = build_workflow(positive, full_negative, width, height, seed=seed, steps=steps, cfg=cfg)

        try:
            prompt_id = queue_prompt(workflow)
            images = get_images(prompt_id)

            for j, img_bytes in enumerate(images):
                img = Image.open(BytesIO(img_bytes))
                suffix = f"_v{i+1}" if num_variations > 1 else ""
                batch_suffix = f"_b{j}" if len(images) > 1 else ""
                filename = f"{filename_base}{suffix}{batch_suffix}.png"
                filepath = save_dir / filename
                img.save(filepath, "PNG")
                print(f"  ✓ Saved: {filepath}")

        except Exception as e:
            print(f"  ✗ FAILED: {filename_base}_v{i+1} - {e}")
            continue

        # Small delay between generations to prevent VRAM issues
        time.sleep(1)


# ============================================================================
# ASSET DEFINITIONS - ALL PROMPTS
# ============================================================================

def generate_backgrounds():
    """Generate all background layers for all worlds."""

    print("\n" + "="*60)
    print("GENERATING BACKGROUNDS")
    print("="*60)

    backgrounds = {
        # ---- WORLD 1: GARDEN ----
        "garden": {
            "far": [
                {
                    "name": "garden-night-sky",
                    "prompt": "photorealistic night sky over suburban backyard, stars visible, crescent moon, deep blue to dark purple gradient, wispy clouds, warm ambient glow from house windows in distance, no people, no text, cinematic photography, 8k",
                    "negative": "daytime, sun, bright, cartoon, illustration, anime",
                },
            ],
            "mid": [
                {
                    "name": "garden-main",
                    "prompt": "photorealistic backyard garden at night, side view, lush green bushes and flowers, large oak tree with thick branches, garden path with stepping stones, wooden fence, flower beds with roses and daisies, soft warm light from fireflies, dew on leaves, no people, no animals, game background, cinematic, 8k",
                    "negative": "daytime, cartoon, people, characters, front view, top view",
                },
                {
                    "name": "garden-shed",
                    "prompt": "photorealistic old wooden garden shed at night, side view, terracotta pots, watering can, cobwebs, ivy climbing walls, warm light from inside shed window, garden tools leaning on wall, no people, game background, 8k",
                    "negative": "daytime, cartoon, people, modern",
                },
                {
                    "name": "garden-pond",
                    "prompt": "photorealistic small garden pond at night, side view, lily pads floating, reflective water surface, mossy rocks around edges, reeds and cattails, moonlight reflecting off water, fireflies near surface, no people, game background, 8k",
                    "negative": "daytime, cartoon, people, ocean, river",
                },
                {
                    "name": "garden-tree-base",
                    "prompt": "photorealistic base of large oak tree at night, side view, exposed gnarled roots, mushrooms growing on bark, fallen autumn leaves, knot hole in trunk, moss and lichen, soft moonlight filtering through canopy, no people, game background, 8k",
                    "negative": "daytime, cartoon, people, full tree",
                },
                {
                    "name": "garden-flower-tunnel",
                    "prompt": "photorealistic garden archway covered in climbing roses at night, side view, stone path underneath, hanging lantern with warm glow, wisteria draping down, enchanting atmosphere, fireflies, no people, game background, 8k",
                    "negative": "daytime, cartoon, people, indoor",
                },
            ],
            "near": [
                {
                    "name": "garden-foreground",
                    "prompt": "close-up tall grass blades and wildflowers at night, shallow depth of field, bokeh firefly lights in background, dew drops on grass, dandelion, clover, side view ground level perspective, photorealistic macro photography, dark background, 8k",
                    "negative": "daytime, sharp background, cartoon, people",
                },
            ],
        },

        # ---- WORLD 2: NEIGHBORHOOD ----
        "neighborhood": {
            "far": [
                {
                    "name": "neighborhood-skyline",
                    "prompt": "photorealistic suburban neighborhood skyline at dusk, row of houses with lit windows, power lines silhouette, orange and purple sunset sky, tree silhouettes, no people, cinematic wide shot, 8k",
                    "negative": "cartoon, daytime noon, people, cars",
                },
            ],
            "mid": [
                {
                    "name": "neighborhood-street",
                    "prompt": "photorealistic suburban street side view, sidewalk with cracks, white picket fence, mailbox, parked cars, streetlamp with warm glow, fallen leaves on ground, autumn evening, no people, game background, 8k",
                    "negative": "cartoon, people, crowds, summer, snow",
                },
                {
                    "name": "neighborhood-gutter",
                    "prompt": "photorealistic storm drain and gutter on suburban street, side view, water flowing through grate, leaves caught in drain, wet asphalt curb, puddle reflections, evening light, no people, game background, 8k",
                    "negative": "cartoon, people, daytime bright",
                },
                {
                    "name": "neighborhood-alley",
                    "prompt": "photorealistic narrow alley between suburban houses, side view, garbage bins, bicycle leaning on brick wall, clothesline above, dim light, autumn leaves scattered, no people, game background, 8k",
                    "negative": "cartoon, people, modern city, skyscrapers",
                },
            ],
            "near": [
                {
                    "name": "neighborhood-foreground",
                    "prompt": "close-up chain link fence and overgrown weeds at dusk, shallow depth of field, scattered autumn leaves, cracked concrete sidewalk, ground level side view, photorealistic, 8k",
                    "negative": "cartoon, people, daytime bright",
                },
            ],
        },

        # ---- WORLD 3: PARK ----
        "park": {
            "far": [
                {
                    "name": "park-sky",
                    "prompt": "photorealistic overcast sky over public park, grey clouds with hints of light breaking through, distant tree line, birds flying, moody atmospheric, no people, cinematic, 8k",
                    "negative": "cartoon, clear sky, night, people",
                },
            ],
            "mid": [
                {
                    "name": "park-main",
                    "prompt": "photorealistic public park daytime, side view, large open grass field, park bench, walking path, scattered trees with full canopy, pond in background, playground visible in distance, overcast sky, no people, game background, cinematic, 8k",
                    "negative": "cartoon, people, night, snow",
                },
                {
                    "name": "park-playground",
                    "prompt": "photorealistic colorful playground equipment in park, side view, metal slide, swings, rubber mulch ground, sand pit, overcast daylight, no people, no children, game background, 8k",
                    "negative": "cartoon, people, children, night",
                },
                {
                    "name": "park-pond",
                    "prompt": "photorealistic park pond with wooden dock, side view, ducks on water, cattails, weeping willow tree hanging over water, reflections, overcast light, no people, game background, 8k",
                    "negative": "cartoon, people, ocean, river rapids",
                },
                {
                    "name": "park-hill",
                    "prompt": "photorealistic grassy hill in park, side view, kite stuck in tree at top, wildflowers, wind-blown grass bending, overcast sky, panoramic feel, no people, game background, 8k",
                    "negative": "cartoon, people, night, mountain",
                },
            ],
            "near": [
                {
                    "name": "park-foreground",
                    "prompt": "close-up park ground level, fallen leaves on grass, dandelions, small puddle, park bench leg visible, shallow depth of field, overcast daylight, photorealistic, 8k",
                    "negative": "cartoon, people, night",
                },
            ],
        },

        # ---- WORLD 4: STREAM ----
        "stream": {
            "far": [
                {
                    "name": "stream-sky",
                    "prompt": "photorealistic forest canopy from below with sky visible through gaps, dappled sunlight rays, green leaves, blue sky patches, atmospheric, no people, 8k",
                    "negative": "cartoon, night, people, open sky",
                },
            ],
            "mid": [
                {
                    "name": "stream-main",
                    "prompt": "photorealistic forest stream side view, rushing clear water over rocks, mossy boulders, ferns on riverbank, dappled sunlight through trees, small waterfall in background, no people, game background, nature photography, 8k",
                    "negative": "cartoon, people, ocean, city",
                },
                {
                    "name": "stream-rapids",
                    "prompt": "photorealistic white water rapids between large rocks, side view, spray mist, fast current, narrow rocky channel, overhanging branches, dramatic lighting, no people, game background, 8k",
                    "negative": "cartoon, people, calm water, ocean",
                },
                {
                    "name": "stream-waterfall",
                    "prompt": "photorealistic tall waterfall cascading into pool below, side view, cliff face with vines and moss, rainbow in mist, lush vegetation, dramatic, no people, game background, 8k",
                    "negative": "cartoon, people, dry, desert",
                },
                {
                    "name": "stream-calm",
                    "prompt": "photorealistic wide slow river section, side view, sandy bank, dragonflies, lily pads, fallen log bridge crossing, peaceful sunlight, no people, game background, 8k",
                    "negative": "cartoon, people, rapids, ocean",
                },
            ],
            "near": [
                {
                    "name": "stream-foreground",
                    "prompt": "close-up riverbank ground level, wet pebbles, fern fronds, water droplets on leaves, shallow depth of field, mossy rocks, photorealistic macro, 8k",
                    "negative": "cartoon, people, dry",
                },
            ],
        },

        # ---- WORLD 5: FOREST ----
        "forest": {
            "far": [
                {
                    "name": "forest-sky",
                    "prompt": "photorealistic dark forest canopy from below, dense tree coverage, very little sky visible, fog between distant trees, moody atmospheric, rays of light barely breaking through, no people, 8k",
                    "negative": "cartoon, bright, open sky, people",
                },
            ],
            "mid": [
                {
                    "name": "forest-main",
                    "prompt": "photorealistic dense forest interior, side view, towering ancient trees with thick trunks, heavy canopy blocking most light, shafts of light breaking through, thick undergrowth, ferns and moss everywhere, fog between trees, no people, atmospheric, game background, 8k",
                    "negative": "cartoon, bright, people, sparse trees",
                },
                {
                    "name": "forest-vertical",
                    "prompt": "photorealistic massive tree trunk with shelf mushrooms growing from bark, side view, thick vines hanging, hollow interior visible, vertical composition emphasizing height, moss and lichen, atmospheric fog, no people, game background, 8k",
                    "negative": "cartoon, people, small tree, bright",
                },
                {
                    "name": "forest-campfire",
                    "prompt": "photorealistic abandoned campfire in forest clearing, side view, glowing embers still hot, smoke rising, scorched ground ring, surrounding dark forest, wood logs partially burned, dangerous atmosphere, no people, game background, 8k",
                    "negative": "cartoon, people, bright daylight, cooking",
                },
                {
                    "name": "forest-night",
                    "prompt": "photorealistic dark forest at night, side view, owl eyes glowing in tree hollow, moonlight through canopy gaps, sparse fireflies, eerie shadows, roots and undergrowth, no people, game background, 8k",
                    "negative": "cartoon, people, bright, daytime",
                },
            ],
            "near": [
                {
                    "name": "forest-foreground",
                    "prompt": "close-up forest floor ground level, large mushrooms, decaying leaves, spider web with dew drops, moss-covered rock, shallow depth of field, dark moody atmosphere, photorealistic macro, 8k",
                    "negative": "cartoon, people, bright",
                },
            ],
        },

        # ---- WORLD 6: MOUNTAIN ----
        "mountain": {
            "far": [
                {
                    "name": "mountain-sky",
                    "prompt": "photorealistic dramatic mountain sky, towering cumulus clouds, dramatic lighting, sun behind clouds creating god rays, vast open sky, snow-capped peaks in far distance, epic atmosphere, no people, 8k",
                    "negative": "cartoon, flat, people, night",
                },
            ],
            "mid": [
                {
                    "name": "mountain-main",
                    "prompt": "photorealistic mountain rocky terrain side view, jagged cliff face, narrow ledge path, sparse alpine vegetation, snow patches, dramatic clouds below and above, strong wind visible in bent scrub trees, no people, game background, epic landscape photography, 8k",
                    "negative": "cartoon, people, forest, flat",
                },
                {
                    "name": "mountain-cliff",
                    "prompt": "photorealistic vertical rock wall with narrow cracks and ledges, side view, lichen growing on stone, small alpine flowers in crevices, rope bridge visible in distance, dramatic height, no people, game background, 8k",
                    "negative": "cartoon, people, flat, forest",
                },
                {
                    "name": "mountain-summit",
                    "prompt": "photorealistic above the treeline mountain, side view, rocky scree slope, thin air atmosphere, panoramic vista of clouds below, snow and ice patches, windswept barren rock, no people, game background, 8k",
                    "negative": "cartoon, people, trees, forest, flat",
                },
                {
                    "name": "mountain-storm",
                    "prompt": "photorealistic mountain storm, dark ominous clouds, lightning striking nearby peak, heavy rain, dangerous exposed rocky ridge, dramatic atmosphere, no people, game background, 8k",
                    "negative": "cartoon, people, sunny, calm",
                },
            ],
            "near": [
                {
                    "name": "mountain-foreground",
                    "prompt": "close-up rocky mountain ground level, loose gravel and scree, alpine flower growing from crack, lichen on stone, snow patches, shallow depth of field, harsh lighting, photorealistic, 8k",
                    "negative": "cartoon, people, lush vegetation",
                },
            ],
        },

        # ---- WORLD 7: SKY ----
        "sky": {
            "far": [
                {
                    "name": "sky-space",
                    "prompt": "photorealistic view of thin atmosphere transitioning to space, dark blue to black gradient, bright stars and milky way galaxy visible, thin blue atmospheric line on horizon, earth curvature barely visible far below, serene and vast, no people, no aircraft, 8k",
                    "negative": "cartoon, ground, trees, buildings, people, airplane",
                },
            ],
            "mid": [
                {
                    "name": "sky-clouds",
                    "prompt": "photorealistic view above clouds, side perspective, towering cumulus cloud formations as pillars, golden sunset light from below illuminating cloud edges, deep blue sky above transitioning to darker blue, stars becoming visible, no people, no aircraft, ethereal atmosphere, game background, 8k",
                    "negative": "cartoon, ground, people, airplane, buildings",
                },
                {
                    "name": "sky-storm-layer",
                    "prompt": "photorealistic inside thunderstorm cloud, side view, dark turbulent swirling interior, lightning bolts arcing within illuminating cloud walls, purple and dark blue tones, rain curtain visible below, dramatic dangerous atmosphere, no people, game background, 8k",
                    "negative": "cartoon, people, sunny, calm, ground",
                },
                {
                    "name": "sky-above-storm",
                    "prompt": "photorealistic calm above thunderstorm layer, side view, flat cloud top stretching like snowy field, stars above in dark sky, lightning flashing below through clouds, serene contrast with violence below, no people, game background, 8k",
                    "negative": "cartoon, people, ground, buildings",
                },
                {
                    "name": "sky-stratosphere",
                    "prompt": "photorealistic thin upper atmosphere, near-black sky, dense stars visible, wispy ice crystal clouds, deep blue horizon line with earth curvature, feeling of immense height and solitude, edge of space, no people, no aircraft, game background, 8k",
                    "negative": "cartoon, people, ground, clouds below, airplane",
                },
            ],
            "near": [
                {
                    "name": "sky-foreground",
                    "prompt": "close-up wispy cloud tendrils and ice crystals, shallow depth of field, light refracting through ice particles creating rainbow sparkles, thin atmosphere, dark sky behind, ethereal macro photography, 8k",
                    "negative": "cartoon, ground, people, solid clouds",
                },
            ],
        },
    }

    total = 0
    for world_name, layers in backgrounds.items():
        for layer_name, prompts in layers.items():
            for prompt_data in prompts:
                total += VARIATIONS_PER_BG

    print(f"Total background images to generate: {total}")
    count = 0

    for world_name, layers in backgrounds.items():
        for layer_name, prompts in layers.items():
            for prompt_data in prompts:
                count += VARIATIONS_PER_BG
                pct = int(count / total * 100)
                print(f"\n[{pct}%] {world_name}/{layer_name}/{prompt_data['name']}")

                generate_and_save(
                    positive=prompt_data["prompt"],
                    negative=prompt_data.get("negative", ""),
                    width=DEFAULT_WIDTH,
                    height=DEFAULT_HEIGHT,
                    save_dir=f"backgrounds/{world_name}/{layer_name}",
                    filename_base=prompt_data["name"],
                    num_variations=VARIATIONS_PER_BG,
                )


def generate_characters():
    """Generate all character sprites."""

    print("\n" + "="*60)
    print("GENERATING CHARACTER SPRITES")
    print("="*60)

    characters = {
        "plane": [
            {"name": "plane-idle", "prompt": "white paper airplane, origami style, visible fold creases, slightly worn paper texture, soft warm glow from within, resting on flat surface slight nose-up angle, side profile view, clean white paper with subtle shadows, isolated on solid dark navy blue background, product photography style, 8k", "negative": "realistic airplane, metal, plastic, toy, colored paper"},
            {"name": "plane-glide", "prompt": "white paper airplane in flight, origami style, visible fold creases, wings spread, slight upward angle, motion blur on wing tips, soft warm inner glow, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "realistic airplane, metal, grounded, colored paper"},
            {"name": "plane-dive", "prompt": "white paper airplane diving downward, origami style, visible fold creases, nose pointing down steep angle, speed feeling, side profile view, soft warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "realistic airplane, metal, upward, colored paper"},
            {"name": "plane-ground-slide", "prompt": "white paper airplane sliding flat on surface, origami style, visible fold creases, slight forward tilt, ground contact, momentum feeling, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "realistic airplane, metal, flying, colored paper"},
            {"name": "plane-jump", "prompt": "white paper airplane angled upward 45 degrees launching off surface, origami style, visible fold creases, dynamic lifting pose, soft warm glow, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "realistic airplane, metal, colored paper"},
            {"name": "plane-wet", "prompt": "white paper airplane slightly crumpled and drooping, damp paper texture, darker spots where wet, water stains visible, drooping wings, sad posture, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "dry, crisp, metal, colored paper"},
            {"name": "plane-dry-buff", "prompt": "white paper airplane crisp and bright, perfectly sharp fold lines, slight golden warm glow, pristine paper texture, confident pose slight upward angle, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "wet, crumpled, dark, metal, colored paper"},
            {"name": "plane-damage", "prompt": "white paper airplane slightly crumpled with small tear on wing edge, bent nose, damaged but still flying, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "pristine, perfect, metal, colored paper"},
        ],
        "boat": [
            {"name": "boat-idle", "prompt": "white paper origami boat, classic paper boat shape, visible fold creases, resting on calm water surface with gentle reflection, side profile view, clean white paper, soft warm inner glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real boat, wood, metal, toy boat, colored paper"},
            {"name": "boat-moving", "prompt": "white paper origami boat moving forward on water, slight forward tilt, small wake behind, water ripples around hull, side profile view, soft warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real boat, wood, metal, stationary, colored paper"},
            {"name": "boat-rocking", "prompt": "white paper origami boat tilted to one side on rough water, splash on hull, rocking motion, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "real boat, calm water, metal, colored paper"},
            {"name": "boat-transform-mid", "prompt": "white paper airplane mid-fold transitioning into paper boat shape, half plane half boat, visible folding in progress, magical transformation, side profile view, warm glow at fold points, isolated on solid dark navy blue background, 8k", "negative": "complete shape, metal, colored paper"},
        ],
        "frog": [
            {"name": "frog-crouch", "prompt": "white paper origami frog, classic origami frog shape, crouching pose ready to jump, visible fold creases and paper texture, side profile view, soft warm inner glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real frog, green, slimy, cartoon frog, colored paper"},
            {"name": "frog-jump", "prompt": "white paper origami frog mid-jump, legs extended launching upward, dynamic pose, visible fold creases, side profile view, warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real frog, green, grounded, colored paper"},
            {"name": "frog-peak", "prompt": "white paper origami frog at top of jump arc, legs tucked, airborne, weightless feeling, side profile view, warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real frog, green, grounded, colored paper"},
            {"name": "frog-land", "prompt": "white paper origami frog landing, legs compressed absorbing impact, slight paper crumple, side profile view, isolated on solid dark navy blue background, product photography, 8k", "negative": "real frog, green, jumping, colored paper"},
        ],
        "crane": [
            {"name": "crane-glide", "prompt": "white paper origami crane, traditional Japanese origami crane, wings fully extended spread wide, graceful gliding descent, visible fold creases, elegant pose, side profile view, soft warm inner glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real bird, feathers, cartoon, colored paper"},
            {"name": "crane-flap-down", "prompt": "white paper origami crane, wings angled downward mid-flap stroke, gaining height, dynamic pose, visible fold creases, side profile view, warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real bird, feathers, colored paper"},
            {"name": "crane-flap-up", "prompt": "white paper origami crane, wings angled upward recovery stroke, visible fold creases, side profile view, warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real bird, feathers, colored paper"},
            {"name": "crane-perched", "prompt": "white paper origami crane standing on surface, wings folded neatly at sides, elegant resting pose, visible fold creases, side profile view, warm glow, isolated on solid dark navy blue background, product photography, 8k", "negative": "real bird, feathers, flying, colored paper"},
        ],
    }

    total = sum(len(poses) * VARIATIONS_PER_SPRITE for poses in characters.values())
    print(f"Total character images to generate: {total}")
    count = 0

    for form_name, poses in characters.items():
        for pose in poses:
            count += VARIATIONS_PER_SPRITE
            pct = int(count / total * 100)
            print(f"\n[{pct}%] {form_name}/{pose['name']}")

            generate_and_save(
                positive=pose["prompt"],
                negative=pose.get("negative", ""),
                width=SPRITE_SIZE,
                height=SPRITE_SIZE,
                save_dir=f"sprites/characters/{form_name}",
                filename_base=pose["name"],
                num_variations=VARIATIONS_PER_SPRITE,
                cfg=6.0,  # Slightly lower CFG for characters
            )


def generate_enemies():
    """Generate all enemy sprites."""

    print("\n" + "="*60)
    print("GENERATING ENEMY SPRITES")
    print("="*60)

    enemies = [
        # Cat (Garden)
        {"name": "cat-idle", "dir": "cat", "prompt": "photorealistic domestic tabby cat sitting alert, side profile view, ears perked forward, tail wrapped around feet, watchful eyes, garden night setting, isolated subject, wildlife photography, 8k", "negative": "cartoon, cute, sleeping, people"},
        {"name": "cat-crouch", "dir": "cat", "prompt": "photorealistic domestic tabby cat crouching low hunting pose, side profile view, eyes focused forward, tail low, muscles tensed ready to pounce, night lighting, isolated subject, wildlife photography, 8k", "negative": "cartoon, cute, friendly, standing, people"},
        {"name": "cat-pounce", "dir": "cat", "prompt": "photorealistic domestic tabby cat mid-pounce leaping through air, side profile view, front paws extended, back legs pushing off, dynamic action, night lighting, isolated subject, wildlife photography, 8k", "negative": "cartoon, sitting, sleeping, people"},
        {"name": "cat-walk", "dir": "cat", "prompt": "photorealistic domestic tabby cat walking stalking prey, side profile view, low deliberate steps, focused expression, night garden, isolated subject, wildlife photography, 8k", "negative": "cartoon, running, sitting, people"},

        # Crow (Neighborhood)
        {"name": "crow-fly", "dir": "crow", "prompt": "photorealistic black crow in flight, side profile view, wings spread mid-flap, glossy black feathers, sharp beak, dusk sky background, isolated subject, wildlife photography, 8k", "negative": "cartoon, perched, colorful, people"},
        {"name": "crow-dive", "dir": "crow", "prompt": "photorealistic black crow swooping downward in attack dive, side profile view, wings tucked back, talons forward, aggressive posture, dramatic lighting, isolated subject, wildlife photography, 8k", "negative": "cartoon, perched, friendly, people"},
        {"name": "crow-perch", "dir": "crow", "prompt": "photorealistic black crow perched on fence post, side profile view, alert watchful pose, glossy feathers, sharp eye, dusk lighting, isolated subject, wildlife photography, 8k", "negative": "cartoon, flying, colorful, people"},

        # Wasp (Park)
        {"name": "wasp-fly", "dir": "wasp", "prompt": "photorealistic wasp in flight, side profile view, wings blurred with motion, stinger visible, yellow and black stripes, aggressive posture, macro photography, isolated subject, 8k", "negative": "cartoon, cute bee, friendly, people"},
        {"name": "wasp-attack", "dir": "wasp", "prompt": "photorealistic wasp diving with stinger extended, aggressive attack pose, side profile view, wings spread, macro photography, isolated subject, 8k", "negative": "cartoon, cute, friendly, people"},

        # Fish (Stream)
        {"name": "fish-jump", "dir": "fish", "prompt": "photorealistic large trout jumping out of river water, side profile view, mouth open, water splashing around, scales glistening, dynamic action pose, nature photography, isolated subject, 8k", "negative": "cartoon, goldfish, aquarium, small, people"},
        {"name": "fish-swim", "dir": "fish", "prompt": "photorealistic large trout swimming underwater, side profile view, fins extended, clear river water, determined expression, nature photography, 8k", "negative": "cartoon, goldfish, aquarium, people"},

        # Owl (Forest)
        {"name": "owl-fly", "dir": "owl", "prompt": "photorealistic great horned owl flying through dark forest, side profile view, massive wingspan, talons extended, piercing yellow eyes, silent flight, moonlight illumination, wildlife photography, 8k", "negative": "cartoon, cute, baby owl, daytime, people"},
        {"name": "owl-swoop", "dir": "owl", "prompt": "photorealistic great horned owl swooping down in attack, side profile view, talons reaching forward, wings back, intense yellow eyes, dark forest background, dramatic, wildlife photography, 8k", "negative": "cartoon, cute, perched, daytime, people"},
        {"name": "owl-perch", "dir": "owl", "prompt": "photorealistic great horned owl perched on thick branch in dark forest, side profile view, alert watching pose, ear tufts visible, yellow eyes glowing, moonlight, wildlife photography, 8k", "negative": "cartoon, cute, flying, daytime, people"},

        # Eagle (Mountain)
        {"name": "eagle-fly", "dir": "eagle", "prompt": "photorealistic golden eagle soaring with massive wingspan, side profile view, feathers ruffled by wind, fierce expression, mountain sky background, majestic, wildlife photography, 8k", "negative": "cartoon, bald eagle, small bird, perched, people"},
        {"name": "eagle-dive", "dir": "eagle", "prompt": "photorealistic golden eagle diving in steep attack stoop, side profile view, wings folded back, talons ready, incredible speed feeling, mountain backdrop, dramatic, wildlife photography, 8k", "negative": "cartoon, gentle, perched, people"},

        # Storm Cloud (Final Boss)
        {"name": "stormcloud-main", "dir": "stormcloud", "prompt": "massive cumulonimbus thundercloud, side view, dark ominous swirling interior, lightning bolts arcing within, vortex center suggesting angry face formation, purple and dark blue tones, rain curtain below, apocalyptic atmosphere, nature photography, 8k", "negative": "cartoon, friendly cloud, white fluffy, clear sky, people"},
        {"name": "stormcloud-lightning", "dir": "stormcloud", "prompt": "massive thunderstorm cloud with multiple lightning bolts striking downward, side view, electric blue and purple illumination, swirling dark clouds, terrifying power, dramatic atmosphere, 8k", "negative": "cartoon, calm, sunny, people"},
        {"name": "stormcloud-rage", "dir": "stormcloud", "prompt": "extreme close-up of thunderstorm cloud face formation in swirling vortex, angry expression in cloud formations, lightning for eyes, dark and terrifying, apocalyptic boss feeling, 8k", "negative": "cartoon, friendly, cute, people"},
    ]

    total = len(enemies) * VARIATIONS_PER_ENEMY
    print(f"Total enemy images to generate: {total}")
    count = 0

    for enemy in enemies:
        count += VARIATIONS_PER_ENEMY
        pct = int(count / total * 100)
        print(f"\n[{pct}%] {enemy['dir']}/{enemy['name']}")

        generate_and_save(
            positive=enemy["prompt"],
            negative=enemy.get("negative", ""),
            width=SPRITE_SIZE,
            height=SPRITE_SIZE,
            save_dir=f"sprites/enemies/{enemy['dir']}",
            filename_base=enemy["name"],
            num_variations=VARIATIONS_PER_ENEMY,
        )


def generate_objects():
    """Generate environment objects and hazards."""

    print("\n" + "="*60)
    print("GENERATING ENVIRONMENT OBJECTS")
    print("="*60)

    objects = [
        # Water
        {"name": "puddle-small", "dir": "hazards", "prompt": "photorealistic small puddle of water on garden path, top-down angled view, reflective surface, single leaf floating, wet ground around edges, isolated on dark background, product photography, 8k", "negative": "cartoon, ocean, river, people"},
        {"name": "puddle-medium", "dir": "hazards", "prompt": "photorealistic medium puddle of water on stone path, top-down angled view, reflective surface, leaves and twigs floating, mud edges, isolated on dark background, product photography, 8k", "negative": "cartoon, ocean, people"},
        {"name": "puddle-large", "dir": "hazards", "prompt": "photorealistic large garden puddle after rain, top-down angled view, reflective surface, multiple leaves floating, grass edges, isolated on dark background, product photography, 8k", "negative": "cartoon, ocean, people"},

        # Fire
        {"name": "fire-campfire", "dir": "hazards", "prompt": "photorealistic small campfire, side view, orange flames dancing, glowing red embers, smoke wisps rising, wood logs burning, isolated on dark background, 8k", "negative": "cartoon, large fire, explosion, people"},
        {"name": "fire-candle", "dir": "hazards", "prompt": "photorealistic lit candle with warm flame, side view, melting wax, flickering fire, isolated on dark background, product photography, 8k", "negative": "cartoon, large fire, people"},
        {"name": "fire-match", "dir": "hazards", "prompt": "photorealistic lit match with small bright flame, side view, wooden match stick, isolated on dark background, macro photography, 8k", "negative": "cartoon, large fire, people"},

        # Sprinkler
        {"name": "sprinkler", "dir": "objects", "prompt": "photorealistic garden sprinkler, side view, metal and plastic construction, water spray arc visible, droplets in air, green grass around base, isolated subject, product photography, 8k", "negative": "cartoon, industrial, people"},

        # Fan/Vent
        {"name": "fan-industrial", "dir": "objects", "prompt": "photorealistic industrial floor fan, side view, metal blades with motion blur, protective grill, strong airflow visible with dust particles, isolated on dark background, product photography, 8k", "negative": "cartoon, ceiling fan, people"},

        # Fence sections
        {"name": "fence-picket", "dir": "objects", "prompt": "photorealistic white picket fence section, side view, weathered wood paint peeling slightly, garden visible behind, isolated subject, 8k", "negative": "cartoon, metal fence, people"},
        {"name": "fence-wood", "dir": "objects", "prompt": "photorealistic wooden garden fence panel, side view, natural brown wood, horizontal slats, slightly weathered, moss on base, isolated subject, 8k", "negative": "cartoon, metal, chain link, people"},
        {"name": "fence-wire", "dir": "objects", "prompt": "photorealistic chain link fence section, side view, metal wire diamond pattern, slightly rusty, weeds growing through base, isolated subject, 8k", "negative": "cartoon, wooden fence, people"},

        # Vegetation
        {"name": "bush-round", "dir": "objects", "prompt": "photorealistic round garden bush, side view, dense green leaves, trimmed spherical shape, garden setting, isolated subject, 8k", "negative": "cartoon, dead, brown, people"},
        {"name": "bush-wild", "dir": "objects", "prompt": "photorealistic wild untrimmed garden bush, side view, uneven natural shape, mixed green leaves, small flowers, isolated subject, 8k", "negative": "cartoon, trimmed, topiary, people"},
        {"name": "flowers-cluster", "dir": "objects", "prompt": "photorealistic cluster of garden flowers, side view, mixed daisies and wildflowers, green stems and leaves, colorful petals, isolated subject on dark background, 8k", "negative": "cartoon, single flower, bouquet, people"},
        {"name": "mushrooms", "dir": "objects", "prompt": "photorealistic cluster of small mushrooms growing from ground, side view, brown caps, white stems, forest floor setting, moss around base, macro photography, 8k", "negative": "cartoon, giant, psychedelic, people"},

        # Firefly
        {"name": "firefly", "dir": "collectibles", "prompt": "single firefly glowing brightly, extreme close-up macro photography, soft warm yellow-green bioluminescent glow, translucent delicate wings, small dark body, bokeh dark background, magical atmosphere, nature macro, 8k", "negative": "cartoon, multiple insects, butterfly, moth, people"},

        # Stepping stones
        {"name": "stone-round", "dir": "objects", "prompt": "photorealistic round garden stepping stone, top-down view, grey natural stone, moss on edges, embedded in grass, isolated, 8k", "negative": "cartoon, brick, people"},
        {"name": "stone-flat", "dir": "objects", "prompt": "photorealistic flat slate stepping stone, top-down view, dark grey natural stone, irregular shape, grass around edges, isolated, 8k", "negative": "cartoon, round, people"},
    ]

    total = len(objects) * VARIATIONS_PER_OBJECT
    print(f"Total object images to generate: {total}")
    count = 0

    for obj in objects:
        count += VARIATIONS_PER_OBJECT
        pct = int(count / total * 100)
        print(f"\n[{pct}%] {obj['dir']}/{obj['name']}")

        generate_and_save(
            positive=obj["prompt"],
            negative=obj.get("negative", ""),
            width=SPRITE_SIZE,
            height=SPRITE_SIZE,
            save_dir=f"sprites/{obj['dir']}",
            filename_base=obj["name"],
            num_variations=VARIATIONS_PER_OBJECT,
        )


def generate_ui():
    """Generate UI elements."""

    print("\n" + "="*60)
    print("GENERATING UI ELEMENTS")
    print("="*60)

    ui_elements = [
        {"name": "menu-bg", "prompt": "photorealistic child's wooden desk from above, scattered white paper sheets, colored pencils, origami paper planes and boats, warm desk lamp light, cozy bedroom atmosphere, top-down view, nostalgic warm feeling, 8k", "negative": "cartoon, messy, dark, people, hands", "w": DEFAULT_WIDTH, "h": DEFAULT_HEIGHT},
        {"name": "world-map", "prompt": "hand-drawn treasure map style illustration on aged yellowed parchment paper, dotted trail path from bottom-left garden to top-right stars, garden house at bottom, hills and trees in middle, mountains above, clouds and moon at top, watercolor art style on old paper, vintage illustration, side view journey map, 8k", "negative": "photograph, modern, digital, people", "w": DEFAULT_WIDTH, "h": DEFAULT_HEIGHT},
    ]

    for ui in ui_elements:
        print(f"\n  UI: {ui['name']}")
        generate_and_save(
            positive=ui["prompt"],
            negative=ui.get("negative", ""),
            width=ui.get("w", SPRITE_SIZE),
            height=ui.get("h", SPRITE_SIZE),
            save_dir="ui",
            filename_base=ui["name"],
            num_variations=3,
        )


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def test_connection():
    """Test ComfyUI is running and accessible."""
    try:
        resp = urllib.request.urlopen(f"http://{COMFYUI_URL}/system_stats")
        data = json.loads(resp.read())
        vram = data.get('devices', [{}])[0].get('vram_total', 0) / (1024**3)
        print(f"✓ Connected to ComfyUI at {COMFYUI_URL}")
        print(f"  VRAM: {vram:.1f} GB")
        return True
    except Exception as e:
        print(f"✗ Cannot connect to ComfyUI at {COMFYUI_URL}")
        print(f"  Error: {e}")
        print(f"\n  Make sure ComfyUI is running:")
        print(f"    cd /path/to/ComfyUI")
        print(f"    python main.py --listen 0.0.0.0")
        return False


def main():
    print("="*60)
    print("  WILDFOLD - Art Asset Generator")
    print("  Generates ALL game art via ComfyUI")
    print("="*60)
    print(f"\nCheckpoint: {CHECKPOINT}")
    print(f"Output: {OUTPUT_DIR.absolute()}")

    if not test_connection():
        sys.exit(1)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    # Count total
    print("\nEstimated generations:")
    print(f"  Backgrounds: ~{7 * 6 * VARIATIONS_PER_BG} images")
    print(f"  Characters:  ~{20 * VARIATIONS_PER_SPRITE} images")
    print(f"  Enemies:     ~{20 * VARIATIONS_PER_ENEMY} images")
    print(f"  Objects:     ~{20 * VARIATIONS_PER_OBJECT} images")
    print(f"  UI:          ~6 images")
    total_est = (7*6*VARIATIONS_PER_BG + 20*VARIATIONS_PER_SPRITE + 20*VARIATIONS_PER_ENEMY + 20*VARIATIONS_PER_OBJECT + 6)
    time_est = total_est * 25 / 60  # ~25s per SDXL image on 3080 Ti
    print(f"\n  Total: ~{total_est} images")
    print(f"  Estimated time: ~{time_est:.0f} minutes ({time_est/60:.1f} hours)")

    input("\nPress ENTER to start generating (or Ctrl+C to cancel)...")

    try:
        generate_backgrounds()
        generate_characters()
        generate_enemies()
        generate_objects()
        generate_ui()
    except KeyboardInterrupt:
        print("\n\n⚠ Generation interrupted by user. Partial results saved.")
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        print("  Partial results saved. Re-run to continue.")

    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)
    print(f"\n{'='*60}")
    print(f"  COMPLETE! Time: {hours}h {mins}m")
    print(f"  Output: {OUTPUT_DIR.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
