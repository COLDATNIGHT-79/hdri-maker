"""
Stamp Library for HDRI Maker.
Manages stamp assets (trees, mountains, buildings, etc.) for placing
silhouettes and objects onto the HDRI canvas.
Includes procedural stamp generation for built-in assets.
"""

import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image


# ============================================================
#  STAMP INSTANCE
# ============================================================

class StampInstance:
    """An instance of a stamp placed on the HDRI canvas."""

    _counter = 0

    def __init__(self):
        StampInstance._counter += 1
        self.id = StampInstance._counter
        self.stamp_id = ""
        self.category = ""
        self.x = 0.5  # Normalized position (0-1)
        self.y = 0.5
        self.scale = 1.0
        self.rotation = 0.0  # Degrees
        self.flip_h = False
        self.opacity = 1.0
        self.color = (0.0, 0.0, 0.0)  # Silhouette color
        self.silhouette_mode = True  # True = solid color, False = use stamp's own colors

    def copy(self) -> 'StampInstance':
        s = StampInstance()
        s.stamp_id = self.stamp_id
        s.category = self.category
        s.x = self.x
        s.y = self.y
        s.scale = self.scale
        s.rotation = self.rotation
        s.flip_h = self.flip_h
        s.opacity = self.opacity
        s.color = self.color
        s.silhouette_mode = self.silhouette_mode
        return s

    def to_dict(self) -> dict:
        return {
            'stamp_id': self.stamp_id,
            'category': self.category,
            'x': self.x, 'y': self.y,
            'scale': self.scale,
            'rotation': self.rotation,
            'flip_h': self.flip_h,
            'opacity': self.opacity,
            'color': self.color,
            'silhouette_mode': self.silhouette_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'StampInstance':
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


# ============================================================
#  STAMP ASSET
# ============================================================

class StampAsset:
    """A single stamp asset (image + metadata)."""

    def __init__(self, stamp_id: str, category: str, name: str,
                 image_data: np.ndarray, filepath: str = ""):
        self.stamp_id = stamp_id
        self.category = category
        self.name = name
        self.image_data = image_data  # RGBA float32, original size
        self.filepath = filepath
        self._thumbnail = None

    @property
    def width(self) -> int:
        return self.image_data.shape[1]

    @property
    def height(self) -> int:
        return self.image_data.shape[0]

    def get_thumbnail(self, size: int = 64) -> np.ndarray:
        """Get a small thumbnail for UI display."""
        if self._thumbnail is None or self._thumbnail.shape[0] != size:
            img = Image.fromarray(
                (np.clip(self.image_data, 0, 1) * 255).astype(np.uint8), 'RGBA'
            )
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            self._thumbnail = np.array(img)
        return self._thumbnail


# ============================================================
#  STAMP LIBRARY
# ============================================================

class StampLibrary:
    """Manages all available stamp assets, both built-in and user-imported."""

    # Built-in categories
    CATEGORIES = [
        "Trees", "Mountains", "Buildings", "Foliage",
        "Power Lines", "Birds", "Nature", "Custom"
    ]

    def __init__(self, assets_dir: str = None):
        self.stamps: Dict[str, StampAsset] = {}
        self._assets_dir = assets_dir or str(
            Path(__file__).parent.parent / "assets" / "stamps"
        )
        self._ensure_directories()
        self._generate_builtin_stamps()
        self._load_custom_stamps()

    def _ensure_directories(self):
        """Create stamp asset directories if they don't exist."""
        base = Path(self._assets_dir)
        base.mkdir(parents=True, exist_ok=True)
        for cat in self.CATEGORIES:
            (base / cat.lower().replace(" ", "_")).mkdir(exist_ok=True)

    def get_stamp(self, stamp_id: str) -> Optional[StampAsset]:
        return self.stamps.get(stamp_id)

    def get_by_category(self, category: str) -> List[StampAsset]:
        return [s for s in self.stamps.values() if s.category == category]

    def get_all_categories(self) -> List[str]:
        """Get categories that have at least one stamp."""
        cats = set()
        for s in self.stamps.values():
            cats.add(s.category)
        return sorted(cats)

    def import_stamp(self, filepath: str, category: str = "Custom",
                     name: str = None) -> Optional[StampAsset]:
        """Import a custom stamp from a PNG/JPG file."""
        try:
            img = Image.open(filepath).convert('RGBA')
            data = np.array(img).astype(np.float32) / 255.0
            stamp_id = f"custom_{Path(filepath).stem}"
            name = name or Path(filepath).stem.replace("_", " ").title()

            # Copy to stamps directory
            dest_dir = Path(self._assets_dir) / category.lower().replace(" ", "_")
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / Path(filepath).name
            img.save(str(dest))

            asset = StampAsset(stamp_id, category, name, data, str(dest))
            self.stamps[stamp_id] = asset
            return asset
        except Exception as e:
            print(f"[StampLibrary] Failed to import stamp: {e}")
            return None

    # ================================================================
    #  BUILT-IN STAMP GENERATION
    # ================================================================

    def _generate_builtin_stamps(self):
        """Generate procedural stamps for the built-in library."""
        self._gen_trees()
        self._gen_mountains()
        self._gen_buildings()
        self._gen_nature()

    def _add_stamp(self, stamp_id: str, category: str, name: str,
                   image_data: np.ndarray):
        """Register a generated stamp."""
        # Save to disk
        filepath = Path(self._assets_dir) / category.lower().replace(" ", "_") / f"{stamp_id}.png"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if not filepath.exists():
            img = Image.fromarray(
                (np.clip(image_data, 0, 1) * 255).astype(np.uint8), 'RGBA'
            )
            img.save(str(filepath))

        asset = StampAsset(stamp_id, category, name, image_data, str(filepath))
        self.stamps[stamp_id] = asset

    def _gen_trees(self):
        """Generate tree silhouette stamps."""
        size = 256

        # --- Oak Tree ---
        data = np.zeros((size, size, 4), dtype=np.float32)
        center_x = size // 2
        y_coords, x_coords = np.mgrid[:size, :size]

        # Trunk
        trunk_w = size // 16
        trunk_h = size // 3
        trunk_mask = (
            (x_coords >= center_x - trunk_w) &
            (x_coords <= center_x + trunk_w) &
            (y_coords >= size - trunk_h) &
            (y_coords < size)
        )
        data[trunk_mask] = [0, 0, 0, 1]

        # Canopy (circle)
        canopy_r = size // 3
        canopy_cy = size - trunk_h - canopy_r + size // 8
        dist_canopy = np.sqrt(
            (x_coords - center_x) ** 2 + (y_coords - canopy_cy) ** 2
        ).astype(np.float32)

        # Add noise to canopy edge
        rng = np.random.RandomState(1)
        noise = np.zeros((size, size), dtype=np.float32)
        for freq in [4, 8, 16]:
            n = np.repeat(np.repeat(
                rng.random((size // freq, size // freq)).astype(np.float32),
                freq, axis=0), freq, axis=1)[:size, :size]
            noise += n * (1.0 / freq * 4)
        noise = noise * canopy_r * 0.2

        canopy_mask = dist_canopy < (canopy_r + noise)
        data[canopy_mask] = [0, 0, 0, 1]
        self._add_stamp("tree_oak", "Trees", "Oak Tree", data)

        # --- Pine Tree ---
        data = np.zeros((size, size, 4), dtype=np.float32)
        trunk_w = size // 20
        trunk_h = size // 4
        trunk_mask = (
            (x_coords >= center_x - trunk_w) &
            (x_coords <= center_x + trunk_w) &
            (y_coords >= size - trunk_h) &
            (y_coords < size)
        )
        data[trunk_mask] = [0, 0, 0, 1]

        # Triangular canopy with tiers
        for tier in range(4):
            tier_top = int(size * 0.1 + tier * size * 0.15)
            tier_bot = int(size * 0.3 + tier * size * 0.15)
            tier_width = int(size * 0.08 + tier * size * 0.08)

            for y in range(tier_top, min(tier_bot, size)):
                t = (y - tier_top) / max(tier_bot - tier_top, 1)
                w = int(tier_width * t)
                x_start = max(0, center_x - w)
                x_end = min(size, center_x + w)
                data[y, x_start:x_end] = [0, 0, 0, 1]

        self._add_stamp("tree_pine", "Trees", "Pine Tree", data)

        # --- Palm Tree ---
        data = np.zeros((size, size, 4), dtype=np.float32)
        # Curved trunk
        for y in range(size // 3, size):
            t = (y - size // 3) / (size * 2 / 3)
            curve = int(np.sin(t * 1.2) * size * 0.1)
            cx = center_x + curve
            w = max(1, int(3 + t * 4))
            x_start = max(0, cx - w)
            x_end = min(size, cx + w)
            data[y, x_start:x_end] = [0, 0, 0, 1]

        # Palm fronds
        frond_cy = size // 3
        frond_cx = center_x + int(np.sin(1.2) * size * 0.1)
        num_fronds = 7
        for i in range(num_fronds):
            angle = -np.pi * 0.3 + i * np.pi * 0.6 / (num_fronds - 1)
            angle += (np.random.RandomState(i + 10).random() - 0.5) * 0.2
            for t in np.linspace(0, 1, 60):
                fx = frond_cx + int(np.cos(angle) * t * size * 0.3)
                fy = frond_cy + int(np.sin(angle) * t * size * 0.15 - t ** 2 * size * 0.1)
                droop = int(t ** 2 * size * 0.15)
                fy += droop
                if 0 <= fx < size and 0 <= fy < size:
                    w = max(1, int((1 - t) * 4))
                    for dy in range(-w, w + 1):
                        if 0 <= fy + dy < size:
                            data[fy + dy, fx] = [0, 0, 0, 1]

        self._add_stamp("tree_palm", "Trees", "Palm Tree", data)

        # --- Dead Tree ---
        data = np.zeros((size, size, 4), dtype=np.float32)
        self._draw_branch(data, center_x, size - 1, center_x, size // 3,
                          width=6, rng=np.random.RandomState(42))
        self._add_stamp("tree_dead", "Trees", "Dead Tree", data)

    def _draw_branch(self, data: np.ndarray, x0: int, y0: int, x1: int, y1: int,
                     width: int, rng, depth: int = 0, max_depth: int = 4):
        """Recursively draw a tree branch."""
        size = data.shape[0]

        # Draw line
        steps = max(abs(x1 - x0), abs(y1 - y0), 1) * 2
        for i in range(steps):
            t = i / steps
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            w = max(1, int(width * (1 - t * 0.5)))
            for dx in range(-w, w + 1):
                for dy in range(-w, w + 1):
                    if dx * dx + dy * dy <= w * w:
                        px, py = x + dx, y + dy
                        if 0 <= px < size and 0 <= py < size:
                            data[py, px] = [0, 0, 0, 1]

        if depth >= max_depth:
            return

        # Spawn sub-branches
        num_branches = rng.randint(1, 4)
        for _ in range(num_branches):
            branch_t = rng.uniform(0.3, 0.8)
            bx = int(x0 + (x1 - x0) * branch_t)
            by = int(y0 + (y1 - y0) * branch_t)

            angle = rng.uniform(-1.2, 1.2)
            length = int((y0 - y1) * rng.uniform(0.3, 0.6))

            ex = bx + int(np.sin(angle) * length)
            ey = by - int(np.cos(angle + 0.3) * length)
            ex = max(0, min(size - 1, ex))
            ey = max(0, min(size - 1, ey))

            self._draw_branch(data, bx, by, ex, ey,
                              max(1, width - 1), rng, depth + 1, max_depth)

    def _gen_mountains(self):
        """Generate mountain silhouette stamps."""
        size = 256
        wide = (size, size * 2)  # Mountains are wider

        # --- Mountain Range ---
        data = np.zeros((*wide, 4), dtype=np.float32)
        rng = np.random.RandomState(100)

        # Generate ridge line using midpoint displacement
        num_peaks = 5
        ridge = np.zeros(wide[1], dtype=np.float32)

        # Major peaks
        for i in range(num_peaks):
            peak_x = int(wide[1] * (i + 0.5) / num_peaks + rng.randint(-20, 20))
            peak_h = rng.uniform(0.3, 0.7) * wide[0]
            peak_w = rng.uniform(0.1, 0.2) * wide[1]

            for x in range(wide[1]):
                dist = abs(x - peak_x)
                if dist < peak_w:
                    t = 1 - dist / peak_w
                    ridge[x] = max(ridge[x], peak_h * t ** 1.5)

        # Add noise to ridge
        for x in range(wide[1]):
            ridge[x] += rng.uniform(-10, 10)

        # Fill below ridge
        for x in range(wide[1]):
            ridge_y = int(wide[0] - ridge[x])
            data[ridge_y:, x] = [0, 0, 0, 1]

        self._add_stamp("mountain_range", "Mountains", "Mountain Range", data)

        # --- Rolling Hills ---
        data = np.zeros((*wide, 4), dtype=np.float32)
        ridge = np.zeros(wide[1], dtype=np.float32)

        for x in range(wide[1]):
            ridge[x] = (
                np.sin(x * 0.02) * 30 +
                np.sin(x * 0.05) * 15 +
                np.sin(x * 0.01) * 50 + 80
            )

        for x in range(wide[1]):
            ridge_y = int(wide[0] - ridge[x])
            data[max(0, ridge_y):, x] = [0, 0, 0, 1]

        self._add_stamp("hills_rolling", "Mountains", "Rolling Hills", data)

    def _gen_buildings(self):
        """Generate building/cityscape stamps."""
        size = 256
        wide = (size, size * 2)

        # --- City Skyline ---
        data = np.zeros((*wide, 4), dtype=np.float32)
        rng = np.random.RandomState(200)

        x = 0
        while x < wide[1]:
            building_w = rng.randint(15, 50)
            building_h = rng.randint(40, 200)
            gap = rng.randint(0, 8)

            # Building body
            y_top = wide[0] - building_h
            x_end = min(x + building_w, wide[1])
            data[y_top:, x:x_end] = [0, 0, 0, 1]

            # Antenna or spire on some buildings
            if rng.random() > 0.6:
                spire_h = rng.randint(10, 30)
                spire_x = (x + x_end) // 2
                if 0 <= spire_x < wide[1]:
                    data[max(0, y_top - spire_h):y_top, spire_x] = [0, 0, 0, 1]
                    if spire_x + 1 < wide[1]:
                        data[max(0, y_top - spire_h):y_top, spire_x + 1] = [0, 0, 0, 1]

            # Windows (small lit rectangles)
            win_size = 3
            for wy in range(y_top + 5, wide[0] - 5, win_size * 3):
                for wx in range(x + 3, x_end - 3, win_size * 2):
                    if rng.random() > 0.3:
                        wy2 = min(wy + win_size, wide[0])
                        wx2 = min(wx + win_size, wide[1])
                        # Windows are slightly brighter (not pure black)
                        data[wy:wy2, wx:wx2] = [0.4, 0.35, 0.2, 1]

            x += building_w + gap

        self._add_stamp("city_skyline", "Buildings", "City Skyline", data)

    def _gen_nature(self):
        """Generate nature stamps (birds, grass, etc.)."""
        size = 128

        # --- Bird Flock ---
        data = np.zeros((size, size * 2, 4), dtype=np.float32)
        rng = np.random.RandomState(300)

        num_birds = 12
        for _ in range(num_birds):
            bx = rng.randint(20, size * 2 - 20)
            by = rng.randint(20, size - 20)
            wing_span = rng.randint(6, 15)
            wing_angle = rng.uniform(0.2, 0.6)

            # V-shaped bird
            for t in np.linspace(0, 1, wing_span * 2):
                # Left wing
                lx = bx - int(t * wing_span)
                ly = by - int(t * wing_span * wing_angle)
                if 0 <= lx < size * 2 and 0 <= ly < size:
                    data[ly, lx] = [0, 0, 0, 1]
                    if ly + 1 < size:
                        data[ly + 1, lx] = [0, 0, 0, 1]

                # Right wing
                rx = bx + int(t * wing_span)
                ry = by - int(t * wing_span * wing_angle)
                if 0 <= rx < size * 2 and 0 <= ry < size:
                    data[ry, rx] = [0, 0, 0, 1]
                    if ry + 1 < size:
                        data[ry + 1, rx] = [0, 0, 0, 1]

        self._add_stamp("birds_flock", "Birds", "Bird Flock", data)

        # --- Grass Silhouette ---
        data = np.zeros((size, size * 2, 4), dtype=np.float32)
        rng = np.random.RandomState(400)

        for x in range(0, size * 2, 2):
            blade_h = rng.randint(10, size - 20)
            lean = rng.uniform(-0.3, 0.3)

            for y_step in range(blade_h):
                t = y_step / blade_h
                bx = x + int(lean * y_step)
                by = size - 1 - y_step
                if 0 <= bx < size * 2 and 0 <= by < size:
                    data[by, bx] = [0, 0, 0, 1]

        self._add_stamp("grass_silhouette", "Foliage", "Grass", data)

    # ================================================================
    #  CUSTOM STAMP LOADING
    # ================================================================

    def _load_custom_stamps(self):
        """Load user-imported stamps from the custom directory."""
        custom_dir = Path(self._assets_dir) / "custom"
        if not custom_dir.exists():
            return

        for filepath in custom_dir.glob("*.png"):
            try:
                stamp_id = f"custom_{filepath.stem}"
                if stamp_id not in self.stamps:
                    img = Image.open(filepath).convert('RGBA')
                    data = np.array(img).astype(np.float32) / 255.0
                    name = filepath.stem.replace("_", " ").title()
                    asset = StampAsset(stamp_id, "Custom", name, data, str(filepath))
                    self.stamps[stamp_id] = asset
            except Exception as e:
                print(f"[StampLibrary] Failed to load {filepath}: {e}")


# ============================================================
#  STAMP RENDERER
# ============================================================

def render_stamp(canvas: np.ndarray, stamp_data: np.ndarray,
                 instance: StampInstance):
    """
    Render a single stamp instance onto a canvas.

    Args:
        canvas: Target RGBA float32 array (H, W, 4)
        stamp_data: Stamp RGBA float32 array
        instance: StampInstance with transform and color
    """
    h, w = canvas.shape[:2]
    sh, sw = stamp_data.shape[:2]

    # Apply scale
    scaled_w = int(sw * instance.scale)
    scaled_h = int(sh * instance.scale)
    if scaled_w < 1 or scaled_h < 1:
        return

    # Resize stamp
    img = Image.fromarray(
        (np.clip(stamp_data, 0, 1) * 255).astype(np.uint8), 'RGBA'
    )
    img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Apply flip
    if instance.flip_h:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # Apply rotation
    if abs(instance.rotation) > 0.1:
        img = img.rotate(-instance.rotation, expand=True, resample=Image.BICUBIC)

    stamp_arr = np.array(img).astype(np.float32) / 255.0
    rh, rw = stamp_arr.shape[:2]

    # Calculate position (centered on instance.x, instance.y)
    px = int(instance.x * w - rw // 2)
    py = int(instance.y * h - rh // 2)

    # Clamp to canvas bounds
    src_x0 = max(0, -px)
    src_y0 = max(0, -py)
    dst_x0 = max(0, px)
    dst_y0 = max(0, py)
    src_x1 = min(rw, w - px)
    src_y1 = min(rh, h - py)
    dst_x1 = min(w, px + rw)
    dst_y1 = min(h, py + rh)

    if dst_x1 <= dst_x0 or dst_y1 <= dst_y0:
        return

    # Get stamp region
    region = stamp_arr[src_y0:src_y1, src_x0:src_x1]
    alpha = region[:, :, 3:4] * instance.opacity

    if instance.silhouette_mode:
        # Use solid color for the stamp
        color = np.array([*instance.color, 1.0], dtype=np.float32)
        stamp_rgb = np.ones_like(region[:, :, :3]) * np.array(instance.color, dtype=np.float32)
    else:
        stamp_rgb = region[:, :, :3]

    # Alpha composite onto canvas
    dst_region = canvas[dst_y0:dst_y1, dst_x0:dst_x1]
    dst_region[:, :, :3] = dst_region[:, :, :3] * (1 - alpha) + stamp_rgb * alpha
    dst_region[:, :, 3] = np.clip(dst_region[:, :, 3] + alpha[:, :, 0], 0, 1)


def render_all_stamps(canvas: np.ndarray, stamps: List[StampInstance],
                      library: StampLibrary):
    """Render all stamp instances onto a canvas."""
    for instance in stamps:
        asset = library.get_stamp(instance.stamp_id)
        if asset is not None:
            render_stamp(canvas, asset.image_data, instance)
