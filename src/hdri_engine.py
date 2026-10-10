"""
HDRI Engine - Core data model and processing for the HDRI Maker tool.

Manages layers, compositing, undo/redo, and interfaces with the C++ DLL
for performance-critical operations.
"""

import os
import sys
import ctypes
import numpy as np
from enum import IntEnum
from typing import List, Optional, Tuple
from pathlib import Path

# ============================================================
#  BLEND MODES
# ============================================================

class BlendMode(IntEnum):
    NORMAL = 0
    ADD = 1
    MULTIPLY = 2
    SCREEN = 3
    OVERLAY = 4
    SOFT_LIGHT = 5


BLEND_MODE_NAMES = {
    BlendMode.NORMAL: "Normal",
    BlendMode.ADD: "Add",
    BlendMode.MULTIPLY: "Multiply",
    BlendMode.SCREEN: "Screen",
    BlendMode.OVERLAY: "Overlay",
    BlendMode.SOFT_LIGHT: "Soft Light",
}


# ============================================================
#  C++ DLL INTERFACE
# ============================================================

class CppProcessor:
    """
    Interface to the C++ hdri_processing DLL.
    Falls back to Python implementations if the DLL is not available.
    """

    def __init__(self):
        self._lib = None
        self._load_library()

    def _load_library(self):
        """Try to load the C++ shared library."""
        try:
            base_dir = Path(__file__).parent.parent
            if sys.platform == "win32":
                dll_path = base_dir / "hdri_processing.dll"
            else:
                dll_path = base_dir / "hdri_processing.so"

            if dll_path.exists():
                self._lib = ctypes.CDLL(str(dll_path))
                self._setup_functions()
                print(f"[HDRI Engine] C++ DLL loaded: {dll_path}")
            else:
                print(f"[HDRI Engine] C++ DLL not found at {dll_path}, using Python fallbacks")
        except Exception as e:
            print(f"[HDRI Engine] Failed to load C++ DLL: {e}, using Python fallbacks")

    def _setup_functions(self):
        """Set up ctypes function signatures."""
        if not self._lib:
            return

        F = ctypes.c_float
        I = ctypes.c_int
        U = ctypes.c_uint
        FP = ctypes.POINTER(ctypes.c_float)

        self._lib.gaussian_blur.argtypes = [FP, I, I, I, F]
        self._lib.gaussian_blur.restype = None

        self._lib.bloom_filter.argtypes = [FP, I, I, I, F, F, F]
        self._lib.bloom_filter.restype = None

        self._lib.tone_map_reinhard.argtypes = [FP, FP, I, I, I, F]
        self._lib.tone_map_reinhard.restype = None

        self._lib.tone_map_aces.argtypes = [FP, FP, I, I, I, F]
        self._lib.tone_map_aces.restype = None

        self._lib.composite_layers.argtypes = [FP, FP, FP, I, I, I, F, I]
        self._lib.composite_layers.restype = None

        self._lib.color_grade.argtypes = [FP, I, I, I, F, F, F, F, F, F, F, F, F]
        self._lib.color_grade.restype = None

        self._lib.add_noise.argtypes = [FP, I, I, I, F, U]
        self._lib.add_noise.restype = None

        self._lib.generate_sky.argtypes = [FP, I, I, I, F, F, F, F, F, F, F, F, F, F, F, F, F]
        self._lib.generate_sky.restype = None

    @property
    def available(self) -> bool:
        return self._lib is not None

    def _ptr(self, arr: np.ndarray):
        """Get a ctypes float pointer to a numpy array."""
        return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

    def gaussian_blur(self, data: np.ndarray, sigma: float):
        if self._lib:
            h, w, c = data.shape
            self._lib.gaussian_blur(self._ptr(data), w, h, c, sigma)
        else:
            _py_gaussian_blur(data, sigma)

    def bloom_filter(self, data: np.ndarray, threshold: float, intensity: float, radius: float):
        if self._lib:
            h, w, c = data.shape
            self._lib.bloom_filter(self._ptr(data), w, h, c, threshold, intensity, radius)
        else:
            _py_bloom_filter(data, threshold, intensity, radius)

    def tone_map_reinhard(self, src: np.ndarray, exposure: float) -> np.ndarray:
        dst = np.zeros_like(src)
        if self._lib:
            h, w, c = src.shape
            self._lib.tone_map_reinhard(self._ptr(src), self._ptr(dst), w, h, c, exposure)
        else:
            exp_scale = 2.0 ** exposure
            v = src[..., :3] * exp_scale
            dst[..., :3] = v / (1.0 + v)
            if src.shape[2] == 4:
                dst[..., 3] = src[..., 3]
        return dst

    def tone_map_aces(self, src: np.ndarray, exposure: float) -> np.ndarray:
        dst = np.zeros_like(src)
        if self._lib:
            h, w, c = src.shape
            self._lib.tone_map_aces(self._ptr(src), self._ptr(dst), w, h, c, exposure)
        else:
            exp_scale = 2.0 ** exposure
            v = src[..., :3] * exp_scale
            a, b, c_val, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
            dst[..., :3] = np.clip((v * (a * v + b)) / (v * (c_val * v + d) + e), 0, 1)
            if src.shape[2] == 4:
                dst[..., 3] = src[..., 3]
        return dst

    def composite_layers(self, base: np.ndarray, overlay: np.ndarray,
                          opacity: float, blend_mode: int) -> np.ndarray:
        result = np.zeros_like(base)
        if self._lib:
            h, w, c = base.shape
            self._lib.composite_layers(
                self._ptr(base), self._ptr(overlay), self._ptr(result),
                w, h, c, opacity, blend_mode
            )
        else:
            result = _py_composite(base, overlay, opacity, blend_mode)
        return result

    def color_grade(self, data: np.ndarray,
                     lift: Tuple[float, float, float],
                     gamma: Tuple[float, float, float],
                     gain: Tuple[float, float, float]):
        if self._lib:
            h, w, c = data.shape
            self._lib.color_grade(self._ptr(data), w, h, c,
                                   *lift, *gamma, *gain)
        else:
            _py_color_grade(data, lift, gamma, gain)

    def add_noise(self, data: np.ndarray, intensity: float, seed: int = 42):
        if self._lib:
            h, w, c = data.shape
            self._lib.add_noise(self._ptr(data), w, h, c, intensity, seed)
        else:
            noise = (np.random.RandomState(seed).random(data.shape).astype(np.float32) - 0.5) * 2.0 * intensity
            data[..., :3] += noise[..., :3]
            np.clip(data[..., :3], 0, None, out=data[..., :3])

    def generate_sky(self, data: np.ndarray,
                      horizon_color: Tuple[float, float, float],
                      zenith_color: Tuple[float, float, float],
                      ground_color: Tuple[float, float, float],
                      sun_intensity: float, sun_x: float, sun_y: float, sun_size: float):
        if self._lib:
            h, w, c = data.shape
            self._lib.generate_sky(self._ptr(data), w, h, c,
                                    *horizon_color, *zenith_color, *ground_color,
                                    sun_intensity, sun_x, sun_y, sun_size)
        else:
            _py_generate_sky(data, horizon_color, zenith_color, ground_color,
                              sun_intensity, sun_x, sun_y, sun_size)


# ============================================================
#  PYTHON FALLBACKS (used when C++ DLL is unavailable)
# ============================================================

def _py_gaussian_blur(data: np.ndarray, sigma: float):
    """Pure-Python Gaussian blur using separable convolution."""
    from scipy.ndimage import gaussian_filter
    try:
        for c in range(min(data.shape[2], 3)):
            data[:, :, c] = gaussian_filter(data[:, :, c], sigma=sigma, mode='wrap')
    except ImportError:
        # Very basic box blur fallback
        kernel_size = max(3, int(sigma * 3) | 1)
        pad = kernel_size // 2
        for c in range(min(data.shape[2], 3)):
            padded = np.pad(data[:, :, c], pad, mode='wrap')
            from numpy.lib.stride_tricks import sliding_window_view
            windows = sliding_window_view(padded, (kernel_size, kernel_size))
            data[:, :, c] = windows.mean(axis=(-1, -2))[:data.shape[0], :data.shape[1]]


def _py_bloom_filter(data: np.ndarray, threshold: float, intensity: float, radius: float):
    """Pure-Python bloom filter."""
    lum = 0.2126 * data[:, :, 0] + 0.7152 * data[:, :, 1] + 0.0722 * data[:, :, 2]
    mask = lum > threshold
    bright = data.copy()
    bright[~mask] = 0
    _py_gaussian_blur(bright, radius)
    data[:, :, :3] += bright[:, :, :3] * intensity


def _py_composite(base: np.ndarray, overlay: np.ndarray,
                   opacity: float, blend_mode: int) -> np.ndarray:
    """Pure-Python layer compositing."""
    result = base.copy()
    b = base[..., :3]
    o = overlay[..., :3]

    if overlay.shape[2] == 4:
        oa = overlay[..., 3:4] * opacity
    else:
        oa = np.full((*base.shape[:2], 1), opacity, dtype=np.float32)

    if blend_mode == BlendMode.NORMAL:
        blended = o
    elif blend_mode == BlendMode.ADD:
        blended = b + o
    elif blend_mode == BlendMode.MULTIPLY:
        blended = b * o
    elif blend_mode == BlendMode.SCREEN:
        blended = 1.0 - (1.0 - b) * (1.0 - o)
    elif blend_mode == BlendMode.OVERLAY:
        blended = np.where(b < 0.5, 2.0 * b * o, 1.0 - 2.0 * (1.0 - b) * (1.0 - o))
    else:
        blended = o

    result[..., :3] = b * (1.0 - oa) + blended * oa

    if base.shape[2] == 4:
        ba = base[..., 3:4]
        result[..., 3:4] = ba + oa * (1.0 - ba)

    return result


def _py_color_grade(data: np.ndarray, lift, gamma, gain):
    """Pure-Python color grading."""
    for c in range(3):
        v = data[:, :, c]
        v *= gain[c]
        v += lift[c] * (1.0 - v)
        mask = v > 0
        inv_gamma = 1.0 / max(gamma[c], 0.001)
        v[mask] = np.power(v[mask], inv_gamma)
        data[:, :, c] = v


def _py_generate_sky(data: np.ndarray, horizon, zenith, ground,
                      sun_intensity, sun_x, sun_y, sun_size):
    """Pure-Python procedural sky generation."""
    h, w, c = data.shape
    vs = np.linspace(0, 1, h)
    us = np.linspace(0, 1, w)
    uu, vv = np.meshgrid(us, vs)

    theta = uu * 2.0 * np.pi
    phi = vv * np.pi

    # Direction vectors
    dx = np.sin(phi) * np.cos(theta)
    dy = np.cos(phi)
    dz = np.sin(phi) * np.sin(theta)

    # Sun direction
    sun_theta = sun_x * 2.0 * np.pi
    sun_phi = sun_y * np.pi
    sun_dx = np.sin(sun_phi) * np.cos(sun_theta)
    sun_dy = np.cos(sun_phi)
    sun_dz = np.sin(sun_phi) * np.sin(sun_theta)

    sky_mask = vv < 0.5
    ground_mask = ~sky_mask

    # Sky gradient
    t_sky = np.clip(1.0 - vv / 0.5, 0, 1) ** 2
    t_ground = np.clip(np.sqrt((vv - 0.5) / 0.5), 0, 1)

    for ci in range(3):
        data[:, :, ci] = np.where(
            sky_mask,
            horizon[ci] + t_sky * (zenith[ci] - horizon[ci]),
            horizon[ci] + t_ground * (ground[ci] - horizon[ci])
        )

    # Sun disc
    dot = dx * sun_dx + dy * sun_dy + dz * sun_dz
    cos_size = np.cos(sun_size)
    sun_mask = dot > cos_size
    if np.any(sun_mask):
        sun_factor = ((dot[sun_mask] - cos_size) / (1.0 - cos_size)) ** 3
        data[:, :, 0][sun_mask] += sun_intensity * sun_factor
        data[:, :, 1][sun_mask] += sun_intensity * 0.95 * sun_factor
        data[:, :, 2][sun_mask] += sun_intensity * 0.85 * sun_factor

    # Sun glow
    glow_mask = dot > 0
    glow = np.power(np.clip(dot, 0, None), 64) * sun_intensity * 0.3
    data[:, :, 0] += glow * 1.0
    data[:, :, 1] += glow * 0.9
    data[:, :, 2] += glow * 0.7

    if c == 4:
        data[:, :, 3] = 1.0


# ============================================================
#  HDRI LAYER
# ============================================================

class HDRILayer:
    """A single layer in the HDRI project."""

    _counter = 0

    def __init__(self, width: int, height: int, name: str = None,
                 fill_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)):
        HDRILayer._counter += 1
        self.id = HDRILayer._counter
        self.name = name or f"Layer {self.id}"
        self.width = width
        self.height = height
        self.visible = True
        self.opacity = 1.0
        self.blend_mode = BlendMode.NORMAL
        self.locked = False

        # HDR RGBA float32 image data
        self.data = np.full((height, width, 4), fill_color, dtype=np.float32)

    def clear(self, color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)):
        """Clear the layer to a solid color."""
        self.data[:] = color

    def copy(self) -> 'HDRILayer':
        """Create a deep copy of this layer."""
        new_layer = HDRILayer(self.width, self.height, f"{self.name} (Copy)")
        new_layer.data = self.data.copy()
        new_layer.visible = self.visible
        new_layer.opacity = self.opacity
        new_layer.blend_mode = self.blend_mode
        return new_layer

    def get_thumbnail(self, size: int = 48) -> np.ndarray:
        """Generate a small thumbnail of this layer (LDR, uint8, RGBA)."""
        from PIL import Image

        # Tone map for display
        display = np.clip(self.data[..., :3], 0, 1)
        alpha = np.clip(self.data[..., 3:4], 0, 1)
        display = np.concatenate([display, alpha], axis=2)
        display = (display * 255).astype(np.uint8)

        img = Image.fromarray(display, 'RGBA')
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        return np.array(img)


# ============================================================
#  HDRI PROJECT
# ============================================================

class HDRIProject:
    """
    Manages the full HDRI project: layers, compositing, undo/redo.
    Default canvas size is 2048x1024 (2:1 equirectangular).
    """

    DEFAULT_WIDTH = 2048
    DEFAULT_HEIGHT = 1024

    def __init__(self, width: int = None, height: int = None):
        self.width = width or self.DEFAULT_WIDTH
        self.height = height or self.DEFAULT_HEIGHT
        self.layers: List[HDRILayer] = []
        self.active_layer_index: int = -1
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        self._max_undo = 30
        self.processor = CppProcessor()

        # Composited result cache
        self._composite_cache: Optional[np.ndarray] = None
        self._cache_dirty = True

        # Create initial background layer
        self.add_layer("Background", fill_color=(0.05, 0.05, 0.08, 1.0))

    @property
    def active_layer(self) -> Optional[HDRILayer]:
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    def invalidate_cache(self):
        """Mark the composite cache as dirty."""
        self._cache_dirty = True

    def add_layer(self, name: str = None,
                  fill_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                  above_active: bool = True) -> HDRILayer:
        """Add a new layer to the project."""
        layer = HDRILayer(self.width, self.height, name, fill_color)

        if above_active and self.active_layer_index >= 0:
            insert_idx = self.active_layer_index + 1
            self.layers.insert(insert_idx, layer)
            self.active_layer_index = insert_idx
        else:
            self.layers.append(layer)
            self.active_layer_index = len(self.layers) - 1

        self._cache_dirty = True
        return layer

    def add_image_layer(self, image_data: np.ndarray, name: str = "Imported") -> HDRILayer:
        """Add a layer from image data (resized to project dimensions)."""
        from PIL import Image

        layer = self.add_layer(name)

        # Resize if needed
        if image_data.shape[:2] != (self.height, self.width):
            if image_data.dtype == np.uint8:
                image_data = image_data.astype(np.float32) / 255.0

            channels = image_data.shape[2] if len(image_data.shape) > 2 else 1
            if channels == 1:
                image_data = np.stack([image_data] * 3 + [np.ones_like(image_data)], axis=-1)
            elif channels == 3:
                alpha = np.ones((*image_data.shape[:2], 1), dtype=np.float32)
                image_data = np.concatenate([image_data, alpha], axis=-1)

            img = Image.fromarray((np.clip(image_data, 0, 1) * 255).astype(np.uint8), 'RGBA')
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
            layer.data = np.array(img).astype(np.float32) / 255.0
        else:
            if image_data.dtype == np.uint8:
                layer.data = image_data.astype(np.float32) / 255.0
            else:
                layer.data = image_data.copy()

        self._cache_dirty = True
        return layer

    def remove_layer(self, index: int):
        """Remove a layer by index."""
        if len(self.layers) <= 1:
            return  # Must keep at least one layer
        if 0 <= index < len(self.layers):
            self.layers.pop(index)
            if self.active_layer_index >= len(self.layers):
                self.active_layer_index = len(self.layers) - 1
            self._cache_dirty = True

    def duplicate_layer(self, index: int) -> Optional[HDRILayer]:
        """Duplicate a layer."""
        if 0 <= index < len(self.layers):
            copy = self.layers[index].copy()
            self.layers.insert(index + 1, copy)
            self.active_layer_index = index + 1
            self._cache_dirty = True
            return copy
        return None

    def move_layer(self, from_index: int, to_index: int):
        """Move a layer from one position to another."""
        if 0 <= from_index < len(self.layers) and 0 <= to_index < len(self.layers):
            layer = self.layers.pop(from_index)
            self.layers.insert(to_index, layer)
            self.active_layer_index = to_index
            self._cache_dirty = True

    def merge_down(self, index: int):
        """Merge layer at index with the layer below it."""
        if index > 0 and index < len(self.layers):
            top = self.layers[index]
            bottom = self.layers[index - 1]

            result = self.processor.composite_layers(
                bottom.data, top.data, top.opacity, int(top.blend_mode)
            )
            bottom.data = result
            self.layers.pop(index)
            self.active_layer_index = index - 1
            self._cache_dirty = True

    def flatten(self) -> np.ndarray:
        """Flatten all layers into a single RGBA image."""
        return self.get_composite()

    def get_composite(self) -> np.ndarray:
        """Get the composited result of all visible layers."""
        if not self._cache_dirty and self._composite_cache is not None:
            return self._composite_cache

        if not self.layers:
            self._composite_cache = np.zeros((self.height, self.width, 4), dtype=np.float32)
            self._cache_dirty = False
            return self._composite_cache

        # Start from bottom layer
        result = None
        for layer in self.layers:
            if not layer.visible:
                continue

            if result is None:
                result = layer.data.copy()
                # Apply layer opacity
                if layer.opacity < 1.0:
                    result[..., :3] *= layer.opacity
                    result[..., 3] *= layer.opacity
            else:
                result = self.processor.composite_layers(
                    result, layer.data, layer.opacity, int(layer.blend_mode)
                )

        if result is None:
            result = np.zeros((self.height, self.width, 4), dtype=np.float32)

        self._composite_cache = result
        self._cache_dirty = False
        return result

    def save_undo_state(self, description: str = ""):
        """Save the current state for undo."""
        if len(self._undo_stack) >= self._max_undo:
            self._undo_stack.pop(0)

        state = {
            'description': description,
            'layers': [(l.data.copy(), l.name, l.visible, l.opacity,
                        int(l.blend_mode), l.locked) for l in self.layers],
            'active_index': self.active_layer_index
        }
        self._undo_stack.append(state)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Undo the last action."""
        if not self._undo_stack:
            return False

        # Save current state for redo
        current = {
            'layers': [(l.data.copy(), l.name, l.visible, l.opacity,
                        int(l.blend_mode), l.locked) for l in self.layers],
            'active_index': self.active_layer_index
        }
        self._redo_stack.append(current)

        # Restore previous state
        state = self._undo_stack.pop()
        self._restore_state(state)
        return True

    def redo(self) -> bool:
        """Redo the last undone action."""
        if not self._redo_stack:
            return False

        # Save current state for undo
        current = {
            'layers': [(l.data.copy(), l.name, l.visible, l.opacity,
                        int(l.blend_mode), l.locked) for l in self.layers],
            'active_index': self.active_layer_index
        }
        self._undo_stack.append(current)

        state = self._redo_stack.pop()
        self._restore_state(state)
        return True

    def _restore_state(self, state: dict):
        """Restore project state from a saved state dict."""
        self.layers.clear()
        for data, name, visible, opacity, blend_mode, locked in state['layers']:
            layer = HDRILayer(self.width, self.height, name)
            layer.data = data
            layer.visible = visible
            layer.opacity = opacity
            layer.blend_mode = BlendMode(blend_mode)
            layer.locked = locked
            self.layers.append(layer)
        self.active_layer_index = state['active_index']
        self._cache_dirty = True


# ============================================================
#  BRUSH ENGINE
# ============================================================

class BrushEngine:
    """Handles painting operations on layers."""

    def __init__(self):
        self.size = 30
        self.hardness = 0.8
        self.opacity = 1.0
        self.color = (1.0, 1.0, 1.0, 1.0)  # HDR RGBA
        self.intensity = 1.0  # HDR intensity multiplier
        self._stamp_cache = {}

    def get_stamp(self, size: int = None, hardness: float = None) -> np.ndarray:
        """Generate a circular brush stamp (alpha mask)."""
        size = size or self.size
        hardness = hardness or self.hardness
        key = (size, int(hardness * 100))

        if key in self._stamp_cache:
            return self._stamp_cache[key]

        diameter = size * 2 + 1
        stamp = np.zeros((diameter, diameter), dtype=np.float32)
        center = size

        for y in range(diameter):
            for x in range(diameter):
                dist = np.sqrt((x - center) ** 2 + (y - center) ** 2) / size
                if dist <= 1.0:
                    # Hardness controls falloff
                    if hardness >= 1.0:
                        stamp[y, x] = 1.0
                    else:
                        edge_start = hardness
                        if dist <= edge_start:
                            stamp[y, x] = 1.0
                        else:
                            t = (dist - edge_start) / (1.0 - edge_start)
                            stamp[y, x] = 1.0 - t * t  # Quadratic falloff

        self._stamp_cache[key] = stamp
        return stamp

    def paint_stroke(self, layer: HDRILayer, x: int, y: int, erase: bool = False):
        """Paint a single brush stamp at position (x, y) on the layer."""
        if layer.locked:
            return

        stamp = self.get_stamp()
        radius = self.size
        diameter = radius * 2 + 1

        # Calculate bounds with wrapping for equirectangular
        h, w = layer.height, layer.width

        for sy in range(diameter):
            for sx in range(diameter):
                if stamp[sy, sx] <= 0:
                    continue

                px = (x - radius + sx) % w  # Wrap horizontally
                py = y - radius + sy

                if py < 0 or py >= h:
                    continue

                alpha = stamp[sy, sx] * self.opacity

                if erase:
                    # Eraser: reduce alpha
                    layer.data[py, px, 3] *= (1.0 - alpha)
                else:
                    # Paint: blend color with HDR intensity
                    r = self.color[0] * self.intensity
                    g = self.color[1] * self.intensity
                    b = self.color[2] * self.intensity

                    old_a = layer.data[py, px, 3]
                    new_a = old_a + alpha * (1.0 - old_a)

                    if new_a > 0:
                        blend = alpha / new_a
                        layer.data[py, px, 0] = layer.data[py, px, 0] * (1.0 - blend) + r * blend
                        layer.data[py, px, 1] = layer.data[py, px, 1] * (1.0 - blend) + g * blend
                        layer.data[py, px, 2] = layer.data[py, px, 2] * (1.0 - blend) + b * blend
                        layer.data[py, px, 3] = new_a

    def paint_line(self, layer: HDRILayer, x0: int, y0: int, x1: int, y1: int, erase: bool = False):
        """Paint along a line from (x0,y0) to (x1,y1) using Bresenham-like stepping."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        dist = max(dx, dy, 1)

        # Step size based on brush size for smooth strokes
        step = max(1, self.size // 3)
        num_steps = max(dist // step, 1)

        for i in range(num_steps + 1):
            t = i / num_steps if num_steps > 0 else 0
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            self.paint_stroke(layer, x, y, erase)


# ============================================================
#  OBJ SPHERE GENERATOR
# ============================================================

def generate_sphere_obj(filepath: str, segments: int = 32, rings: int = 16, radius: float = 1.0):
    """Generate a UV sphere .obj file for 3D preview."""
    vertices = []
    normals = []
    uvs = []
    faces = []

    # Top vertex
    vertices.append((0, radius, 0))
    normals.append((0, 1, 0))
    uvs.append((0.5, 1.0))

    # Generate rings
    for ring in range(1, rings):
        phi = np.pi * ring / rings
        for seg in range(segments):
            theta = 2.0 * np.pi * seg / segments

            x = radius * np.sin(phi) * np.cos(theta)
            y = radius * np.cos(phi)
            z = radius * np.sin(phi) * np.sin(theta)

            nx = np.sin(phi) * np.cos(theta)
            ny = np.cos(phi)
            nz = np.sin(phi) * np.sin(theta)

            u = seg / segments
            v = 1.0 - ring / rings

            vertices.append((x, y, z))
            normals.append((nx, ny, nz))
            uvs.append((u, v))

    # Bottom vertex
    vertices.append((0, -radius, 0))
    normals.append((0, -1, 0))
    uvs.append((0.5, 0.0))

    # Top cap faces
    for seg in range(segments):
        next_seg = (seg + 1) % segments
        faces.append((1, seg + 2, next_seg + 2))

    # Middle ring faces
    for ring in range(rings - 2):
        for seg in range(segments):
            next_seg = (seg + 1) % segments
            current = 1 + ring * segments + seg + 1
            next_ring = 1 + (ring + 1) * segments + seg + 1
            current_next = 1 + ring * segments + next_seg + 1
            next_ring_next = 1 + (ring + 1) * segments + next_seg + 1

            faces.append((current, next_ring, next_ring_next))
            faces.append((current, next_ring_next, current_next))

    # Bottom cap faces
    bottom_idx = len(vertices)
    for seg in range(segments):
        next_seg = (seg + 1) % segments
        ring_start = 1 + (rings - 2) * segments
        faces.append((bottom_idx, ring_start + next_seg + 1, ring_start + seg + 1))

    # Write OBJ file
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write("# HDRI Maker - Sample Sphere\n")
        f.write(f"# Segments: {segments}, Rings: {rings}\n\n")

        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")

        f.write("\n")
        for vn in normals:
            f.write(f"vn {vn[0]:.6f} {vn[1]:.6f} {vn[2]:.6f}\n")

        f.write("\n")
        for vt in uvs:
            f.write(f"vt {vt[0]:.6f} {vt[1]:.6f}\n")

        f.write("\n")
        f.write("g sphere\n")
        for face in faces:
            f.write(f"f {face[0]}//{face[0]} {face[1]}//{face[1]} {face[2]}//{face[2]}\n")

    return filepath
