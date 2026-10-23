"""
HDRI Engine - Core data model and processing for the HDRI Maker tool.

Manages layers, compositing, undo/redo, and interfaces with the C++ DLL
for performance-critical operations. Supports multiple layer types:
paint, sun, cloud, atmosphere, stamp, adjustment, and group layers.
"""

import os
import sys
import math
import ctypes
import json
import numpy as np
from enum import IntEnum
from typing import List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

_NUM_CORES = max(2, min(os.cpu_count() or 4, 16))
_HDRI_EXECUTOR = ThreadPoolExecutor(max_workers=_NUM_CORES)

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
#  LAYER TYPES
# ============================================================

class LayerType(IntEnum):
    PAINT = 0
    SUN = 1
    CLOUD = 2
    ATMOSPHERE = 3
    STAMP = 4
    ADJUSTMENT = 5
    GROUP = 6


LAYER_TYPE_NAMES = {
    LayerType.PAINT: "Paint",
    LayerType.SUN: "☀ Sun",
    LayerType.CLOUD: "☁ Cloud",
    LayerType.ATMOSPHERE: "🌅 Atmosphere",
    LayerType.STAMP: "🌲 Stamp",
    LayerType.ADJUSTMENT: "⚙ Adjustment",
    LayerType.GROUP: "📁 Group",
}

LAYER_TYPE_ICONS = {
    LayerType.PAINT: "🎨",
    LayerType.SUN: "☀",
    LayerType.CLOUD: "☁",
    LayerType.ATMOSPHERE: "🌅",
    LayerType.STAMP: "🌲",
    LayerType.ADJUSTMENT: "⚙",
    LayerType.GROUP: "📁",
}


# ============================================================
#  SUN OBJECT
# ============================================================

class SunObject:
    """Represents a sun/light source in the environment."""

    _counter = 0

    def __init__(self):
        SunObject._counter += 1
        self.id = SunObject._counter
        self.name = f"Sun {self.id}"

        # Position (normalized 0-1)
        self.azimuth = 0.25    # Horizontal position
        self.elevation = 0.25  # Vertical position (0=top, 0.5=horizon)

        # Light properties
        self.intensity = 10.0
        self.temperature = 5500  # Kelvin (1800-12000)
        self.color_override = None  # If set, overrides temperature-based color
        self.disc_size = 0.02  # Angular size in radians

        # Halo
        self.halo_radius = 0.08
        self.halo_intensity = 0.5
        self.halo_falloff = 2.0

        # Advanced
        self.limb_darkening = 0.5
        self.flare_enabled = False
        self.flare_intensity = 0.3
        self.flare_rays = 6

    @property
    def color(self) -> Tuple[float, float, float]:
        """Get sun color from temperature or override."""
        if self.color_override:
            return self.color_override
        from src.atmosphere import kelvin_to_rgb
        return kelvin_to_rgb(self.temperature)

    def copy(self) -> 'SunObject':
        s = SunObject()
        s.name = f"{self.name} (Copy)"
        s.azimuth = self.azimuth
        s.elevation = self.elevation
        s.intensity = self.intensity
        s.temperature = self.temperature
        s.color_override = self.color_override
        s.disc_size = self.disc_size
        s.halo_radius = self.halo_radius
        s.halo_intensity = self.halo_intensity
        s.halo_falloff = self.halo_falloff
        s.limb_darkening = self.limb_darkening
        s.flare_enabled = self.flare_enabled
        s.flare_intensity = self.flare_intensity
        s.flare_rays = self.flare_rays
        return s

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'azimuth': self.azimuth,
            'elevation': self.elevation,
            'intensity': self.intensity,
            'temperature': self.temperature,
            'color_override': self.color_override,
            'disc_size': self.disc_size,
            'halo_radius': self.halo_radius,
            'halo_intensity': self.halo_intensity,
            'halo_falloff': self.halo_falloff,
            'limb_darkening': self.limb_darkening,
            'flare_enabled': self.flare_enabled,
            'flare_intensity': self.flare_intensity,
            'flare_rays': self.flare_rays,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'SunObject':
        s = cls()
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


# ============================================================
#  ADJUSTMENT SETTINGS
# ============================================================

class AdjustmentSettings:
    """Settings for an adjustment layer."""

    def __init__(self):
        self.brightness = 0.0    # -1 to 1
        self.contrast = 0.0      # -1 to 1
        self.saturation = 1.0    # 0 to 2
        self.hue_shift = 0.0     # -180 to 180 degrees
        self.temperature = 0.0   # -1 (cool) to 1 (warm)
        self.gamma = 1.0         # 0.1 to 3.0

    def copy(self) -> 'AdjustmentSettings':
        a = AdjustmentSettings()
        a.brightness = self.brightness
        a.contrast = self.contrast
        a.saturation = self.saturation
        a.hue_shift = self.hue_shift
        a.temperature = self.temperature
        a.gamma = self.gamma
        return a

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> 'AdjustmentSettings':
        a = cls()
        for k, v in d.items():
            if hasattr(a, k):
                setattr(a, k, v)
        return a

    def apply(self, data: np.ndarray) -> np.ndarray:
        """Apply adjustment to image data (returns new array)."""
        result = data.copy()
        rgb = result[..., :3]

        # Brightness
        if abs(self.brightness) > 0.001:
            rgb += self.brightness

        # Contrast
        if abs(self.contrast) > 0.001:
            mid = 0.5
            factor = (1.0 + self.contrast)
            rgb[:] = (rgb - mid) * factor + mid

        # Saturation
        if abs(self.saturation - 1.0) > 0.001:
            lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
            lum = lum[..., np.newaxis]
            rgb[:] = lum + (rgb - lum) * self.saturation

        # Temperature (warm/cool shift)
        if abs(self.temperature) > 0.001:
            rgb[..., 0] += self.temperature * 0.1   # Red channel
            rgb[..., 2] -= self.temperature * 0.1   # Blue channel

        # Gamma
        if abs(self.gamma - 1.0) > 0.001:
            mask = rgb > 0
            rgb[mask] = np.power(rgb[mask], 1.0 / self.gamma)

        result[..., :3] = np.clip(rgb, 0, None)
        return result


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


def _composite_slice(base_slice: np.ndarray, overlay_slice: np.ndarray,
                     opacity: float, blend_mode: int) -> np.ndarray:
    b = base_slice[..., :3]
    o = overlay_slice[..., :3]

    if overlay_slice.shape[2] == 4:
        oa = overlay_slice[..., 3:4] * opacity
    else:
        oa = np.full((*base_slice.shape[:2], 1), opacity, dtype=np.float32)

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
    elif blend_mode == BlendMode.SOFT_LIGHT:
        blended = (1.0 - 2.0 * o) * (b ** 2) + 2.0 * b * o
    else:
        blended = o

    res = np.empty_like(base_slice)
    res[..., :3] = b * (1.0 - oa) + blended * oa

    if base_slice.shape[2] == 4:
        ba = base_slice[..., 3:4]
        res[..., 3:4] = ba + oa * (1.0 - ba)

    return res


def _py_composite(base: np.ndarray, overlay: np.ndarray,
                   opacity: float, blend_mode: int) -> np.ndarray:
    """Vectorized SIMD layer compositing without thread scheduling overhead."""
    return _composite_slice(base, overlay, opacity, blend_mode)


_EQUIRECT_GRID_CACHE = {}


def get_equirect_grid(w: int, h: int):
    """Cached spherical equirectangular unit vector directions and UV mesh."""
    key = (w, h)
    if key not in _EQUIRECT_GRID_CACHE:
        us = np.linspace(0, 1, w, dtype=np.float32)
        vs = np.linspace(0, 1, h, dtype=np.float32)
        uu, vv = np.meshgrid(us, vs)
        theta = uu * (2.0 * np.pi)
        phi = vv * np.pi
        dx = np.sin(phi) * np.cos(theta)
        dy = np.cos(phi)
        dz = np.sin(phi) * np.sin(theta)
        _EQUIRECT_GRID_CACHE[key] = (uu, vv, dx, dy, dz)
    return _EQUIRECT_GRID_CACHE[key]


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
    uu, vv, dx, dy, dz = get_equirect_grid(w, h)

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
#  SUN RENDERER
# ============================================================

def render_sun(data: np.ndarray, sun: SunObject):
    """
    Render a sun object into an RGBA float32 array (in-place).
    Includes disc, limb darkening, halo, and optional flare.
    Uses cached equirectangular spherical directions for instant execution.
    """
    h, w, c = data.shape
    uu, vv, dx, dy, dz = get_equirect_grid(w, h)

    sun_theta = sun.azimuth * 2.0 * np.pi
    sun_phi = sun.elevation * np.pi
    sun_dx = np.sin(sun_phi) * np.cos(sun_theta)
    sun_dy = np.cos(sun_phi)
    sun_dz = np.sin(sun_phi) * np.sin(sun_theta)

    dot = dx * sun_dx + dy * sun_dy + dz * sun_dz
    color = sun.color

    # Sun disc with limb darkening
    cos_disc = math.cos(sun.disc_size)
    disc_mask = dot > cos_disc
    if np.any(disc_mask):
        disc_factor = (dot[disc_mask] - cos_disc) / (1.0 - cos_disc)
        # Limb darkening: center is brighter than edges
        limb = (1.0 - sun.limb_darkening) + sun.limb_darkening * disc_factor
        brightness = disc_factor ** 0.5 * limb * sun.intensity

        data[:, :, 0][disc_mask] += color[0] * brightness
        data[:, :, 1][disc_mask] += color[1] * brightness
        data[:, :, 2][disc_mask] += color[2] * brightness

    # Halo
    if sun.halo_intensity > 0:
        cos_halo = math.cos(sun.halo_radius)
        halo_mask = (dot > cos_halo) & (~disc_mask)
        if np.any(halo_mask):
            halo_factor = (dot[halo_mask] - cos_halo) / (cos_disc - cos_halo)
            halo_factor = halo_factor ** sun.halo_falloff
            brightness = halo_factor * sun.halo_intensity * sun.intensity * 0.1

            data[:, :, 0][halo_mask] += color[0] * brightness
            data[:, :, 1][halo_mask] += color[1] * brightness
            data[:, :, 2][halo_mask] += color[2] * brightness

    # Atmospheric glow (wide)
    glow = np.power(np.clip(dot, 0, None), 48) * sun.intensity * 0.08
    data[:, :, 0] += glow * color[0]
    data[:, :, 1] += glow * color[1]
    data[:, :, 2] += glow * color[2]

    # Flare (starburst)
    if sun.flare_enabled and sun.flare_intensity > 0:
        # Sun position in UV space
        su = sun.azimuth
        sv = sun.elevation

        for ray_idx in range(sun.flare_rays):
            angle = ray_idx * math.pi / sun.flare_rays
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            # Direction along flare ray
            dist_u = (uu - su) * cos_a + (vv - sv) * sin_a
            dist_perp = -(uu - su) * sin_a + (vv - sv) * cos_a

            # Thin line along ray direction
            line_mask = np.abs(dist_perp) < 0.003
            line_falloff = np.exp(-np.abs(dist_u) * 30) * np.exp(-np.abs(dist_perp) * 500)
            flare_val = line_falloff * sun.flare_intensity * sun.intensity * 0.05

            data[:, :, 0] += flare_val * color[0]
            data[:, :, 1] += flare_val * color[1]
            data[:, :, 2] += flare_val * color[2]

    # Set alpha where we painted
    alpha_contrib = np.clip(
        data[:, :, 0] + data[:, :, 1] + data[:, :, 2], 0, 1
    )
    data[:, :, 3] = np.maximum(data[:, :, 3], alpha_contrib)


# ============================================================
#  HDRI LAYER
# ============================================================

class HDRILayer:
    """A single layer in the HDRI project. Supports multiple layer types."""

    _counter = 0

    def __init__(self, width: int, height: int, name: str = None,
                 fill_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                 layer_type: LayerType = LayerType.PAINT):
        HDRILayer._counter += 1
        self.id = HDRILayer._counter
        self.name = name or f"Layer {self.id}"
        self.width = width
        self.height = height
        self.visible = True
        self.opacity = 1.0
        self.blend_mode = BlendMode.NORMAL
        self.locked = False
        self.layer_type = layer_type

        # HDR RGBA float32 image data
        self.data = np.full((height, width, 4), fill_color, dtype=np.float32)

        # Layer mask (optional)
        self.mask = None  # np.ndarray (H, W), float32, 0-1
        self.mask_enabled = False

        # Type-specific data
        self.suns: List[SunObject] = []  # For SUN layers
        self.cloud_settings = None       # For CLOUD layers
        self.atmosphere_settings = None  # For ATMOSPHERE layers
        self.stamps = []                 # For STAMP layers (list of StampInstance)
        self.adjustment = None           # For ADJUSTMENT layers

        # Group layer children
        self.children: List['HDRILayer'] = []
        self.collapsed = False  # For group UI

        # Per-layer effects
        self.effects: List[dict] = []

        # Fast thumbnail cache
        self._cached_thumb: Optional[np.ndarray] = None
        self._thumb_dirty: bool = True

    def clear(self, color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)):
        """Clear the layer to a solid color."""
        self.data[:] = color
        self._thumb_dirty = True

    def regenerate(self, project=None):
        """
        Regenerate layer content from type-specific settings.
        Called when settings change on Sun/Cloud/Atmosphere/Stamp layers.
        """
        if self.layer_type == LayerType.SUN:
            self.data[:] = 0
            for sun in self.suns:
                render_sun(self.data, sun)

        elif self.layer_type == LayerType.CLOUD:
            if self.cloud_settings:
                self.data[:] = 0
                from src.cloud_engine import render_clouds
                # Find sun position from project context
                sun_az, sun_el, sun_col = 0.25, 0.25, (1.0, 0.95, 0.85)
                if project:
                    for layer in project.layers:
                        if layer.layer_type == LayerType.SUN and layer.suns:
                            s = layer.suns[0]
                            sun_az = s.azimuth
                            sun_el = s.elevation
                            sun_col = s.color
                            break
                render_clouds(self.data, self.cloud_settings, sun_az, sun_el, sun_col)

        elif self.layer_type == LayerType.ATMOSPHERE:
            if self.atmosphere_settings:
                self.data[:] = 0
                from src.atmosphere import render_atmosphere
                sun_az, sun_el, sun_int, sun_col = 0.25, 0.25, 10.0, (1.0, 0.95, 0.85)
                if project:
                    for layer in project.layers:
                        if layer.layer_type == LayerType.SUN and layer.suns:
                            s = layer.suns[0]
                            sun_az = s.azimuth
                            sun_el = s.elevation
                            sun_int = s.intensity
                            sun_col = s.color
                            break
                render_atmosphere(self.data, self.atmosphere_settings,
                                   sun_az, sun_el, sun_int, sun_col)

        elif self.layer_type == LayerType.STAMP:
            if self.stamps:
                self.data[:] = 0
                from src.stamp_library import render_all_stamps
                if project and hasattr(project, 'stamp_library'):
                    render_all_stamps(self.data, self.stamps, project.stamp_library)

    def init_mask(self):
        """Initialize a white (fully visible) layer mask."""
        self.mask = np.ones((self.height, self.width), dtype=np.float32)
        self.mask_enabled = True

    def remove_mask(self):
        """Remove the layer mask."""
        self.mask = None
        self.mask_enabled = False

    def get_masked_data(self) -> np.ndarray:
        """Get layer data with mask applied."""
        if self.mask is not None and self.mask_enabled:
            result = self.data.copy()
            result[..., 3] *= self.mask
            return result
        return self.data

    def copy(self) -> 'HDRILayer':
        """Create a deep copy of this layer."""
        new_layer = HDRILayer(self.width, self.height, f"{self.name} (Copy)",
                              layer_type=self.layer_type)
        new_layer.data = self.data.copy()
        new_layer.visible = self.visible
        new_layer.opacity = self.opacity
        new_layer.blend_mode = self.blend_mode

        if self.mask is not None:
            new_layer.mask = self.mask.copy()
            new_layer.mask_enabled = self.mask_enabled

        # Copy type-specific data
        new_layer.suns = [s.copy() for s in self.suns]
        if self.cloud_settings:
            new_layer.cloud_settings = self.cloud_settings.copy()
        if self.atmosphere_settings:
            new_layer.atmosphere_settings = self.atmosphere_settings.copy()
        new_layer.stamps = [s.copy() for s in self.stamps]
        if self.adjustment:
            new_layer.adjustment = self.adjustment.copy()
        new_layer.children = [c.copy() for c in self.children]

        return new_layer

    def get_thumbnail(self, size: int = 48) -> np.ndarray:
        """Generate a small thumbnail of this layer (ultra-fast strided subsampling + cache)."""
        if not self._thumb_dirty and self._cached_thumb is not None:
            return self._cached_thumb

        from PIL import Image

        # Fast strided subsampling directly in NumPy (avoids processing millions of pixels!)
        step_y = max(1, self.height // (size * 2))
        step_x = max(1, self.width // (size * 2))
        sub = self.data[::step_y, ::step_x]

        rgb = np.clip(sub[..., :3], 0.0, 1.0)
        alpha = np.clip(sub[..., 3:4], 0.0, 1.0)
        rgba = (np.dstack([rgb, alpha]) * 255).astype(np.uint8)

        img = Image.fromarray(rgba, 'RGBA')
        img = img.resize((size, size), Image.Resampling.BILINEAR)
        self._cached_thumb = np.array(img)
        self._thumb_dirty = False
        return self._cached_thumb


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

        # Stamp library (shared across layers)
        self.stamp_library = None
        self._init_stamp_library()

        # Global sun objects (accessible from all layers for lighting)
        self._primary_sun: Optional[SunObject] = None

        # Create initial background layer
        self.add_layer("Background", fill_color=(0.05, 0.05, 0.08, 1.0))

    def _init_stamp_library(self):
        """Initialize the stamp library."""
        try:
            from src.stamp_library import StampLibrary
            self.stamp_library = StampLibrary()
        except Exception as e:
            print(f"[HDRI Engine] Failed to initialize stamp library: {e}")

    @property
    def active_layer(self) -> Optional[HDRILayer]:
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    @property
    def primary_sun(self) -> Optional[SunObject]:
        """Get the primary sun object from all sun layers."""
        for layer in self.layers:
            if layer.layer_type == LayerType.SUN and layer.suns:
                return layer.suns[0]
        return self._primary_sun

    def invalidate_cache(self):
        """Mark the composite cache as dirty."""
        self._cache_dirty = True

    def add_layer(self, name: str = None,
                  fill_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                  above_active: bool = True,
                  layer_type: LayerType = LayerType.PAINT) -> HDRILayer:
        """Add a new layer to the project."""
        layer = HDRILayer(self.width, self.height, name, fill_color, layer_type)

        if above_active and self.active_layer_index >= 0:
            insert_idx = self.active_layer_index + 1
            self.layers.insert(insert_idx, layer)
            self.active_layer_index = insert_idx
        else:
            self.layers.append(layer)
            self.active_layer_index = len(self.layers) - 1

        self._cache_dirty = True
        return layer

    def add_sun_layer(self, name: str = "Sun") -> HDRILayer:
        """Add a new sun layer with a default sun object."""
        layer = self.add_layer(name, layer_type=LayerType.SUN)
        sun = SunObject()
        layer.suns.append(sun)
        layer.regenerate(self)
        return layer

    def add_cloud_layer(self, name: str = "Clouds", preset: str = "cumulus") -> HDRILayer:
        """Add a new cloud layer with default settings."""
        from src.cloud_engine import CloudSettings
        layer = self.add_layer(name, layer_type=LayerType.CLOUD)
        settings = CloudSettings()
        settings.preset = preset
        layer.cloud_settings = settings
        layer.regenerate(self)
        return layer

    def add_atmosphere_layer(self, name: str = "Atmosphere") -> HDRILayer:
        """Add a new atmosphere layer."""
        from src.atmosphere import AtmosphereSettings
        layer = self.add_layer(name, layer_type=LayerType.ATMOSPHERE)
        layer.atmosphere_settings = AtmosphereSettings()
        layer.regenerate(self)
        return layer

    def add_stamp_layer(self, name: str = "Stamps") -> HDRILayer:
        """Add a new stamp layer."""
        layer = self.add_layer(name, layer_type=LayerType.STAMP)
        return layer

    def add_adjustment_layer(self, name: str = "Adjustment") -> HDRILayer:
        """Add an adjustment layer."""
        layer = self.add_layer(name, layer_type=LayerType.ADJUSTMENT)
        layer.adjustment = AdjustmentSettings()
        # Adjustment layers start fully white (no effect by default)
        layer.data[:] = (1.0, 1.0, 1.0, 1.0)
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

            top_data = top.get_masked_data()
            result = self.processor.composite_layers(
                bottom.data, top_data, top.opacity, int(top.blend_mode)
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

            # Get layer data (with mask applied)
            layer_data = layer.get_masked_data()

            # Handle adjustment layers
            if layer.layer_type == LayerType.ADJUSTMENT and layer.adjustment:
                if result is not None:
                    result = layer.adjustment.apply(result)
                continue

            if result is None:
                result = layer_data.copy()
                # Apply layer opacity
                if layer.opacity < 1.0:
                    result[..., :3] *= layer.opacity
                    result[..., 3] *= layer.opacity
            else:
                result = self.processor.composite_layers(
                    result, layer_data, layer.opacity, int(layer.blend_mode)
                )

        if result is None:
            result = np.zeros((self.height, self.width, 4), dtype=np.float32)

        self._composite_cache = result
        self._cache_dirty = False
        return result

    def regenerate_procedural_layers(self):
        """Regenerate all procedural layers (sun, cloud, atmosphere, stamp)."""
        for layer in self.layers:
            if layer.layer_type in (LayerType.SUN, LayerType.CLOUD,
                                     LayerType.ATMOSPHERE, LayerType.STAMP):
                layer.regenerate(self)
        self._cache_dirty = True

    def save_undo_state(self, description: str = ""):
        """Save the current state for undo."""
        if len(self._undo_stack) >= self._max_undo:
            self._undo_stack.pop(0)

        state = {
            'description': description,
            'layers': [],
            'active_index': self.active_layer_index
        }
        for l in self.layers:
            layer_state = {
                'data': l.data.copy(),
                'name': l.name,
                'visible': l.visible,
                'opacity': l.opacity,
                'blend_mode': int(l.blend_mode),
                'locked': l.locked,
                'layer_type': int(l.layer_type),
                'mask': l.mask.copy() if l.mask is not None else None,
                'mask_enabled': l.mask_enabled,
                'suns': [s.to_dict() for s in l.suns],
                'cloud_settings': l.cloud_settings.to_dict() if l.cloud_settings else None,
                'atmosphere_settings': l.atmosphere_settings.to_dict() if l.atmosphere_settings else None,
                'stamps': [s.to_dict() for s in l.stamps],
                'adjustment': l.adjustment.to_dict() if l.adjustment else None,
            }
            state['layers'].append(layer_state)

        self._undo_stack.append(state)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Undo the last action."""
        if not self._undo_stack:
            return False

        # Save current state for redo
        current = self._create_state_snapshot()
        self._redo_stack.append(current)

        # Restore previous state
        state = self._undo_stack.pop()
        self._restore_state(state)
        return True

    def redo(self) -> bool:
        """Redo the last undone action."""
        if not self._redo_stack:
            return False

        current = self._create_state_snapshot()
        self._undo_stack.append(current)

        state = self._redo_stack.pop()
        self._restore_state(state)
        return True

    def _create_state_snapshot(self) -> dict:
        """Create a full state snapshot for undo/redo."""
        state = {'layers': [], 'active_index': self.active_layer_index}
        for l in self.layers:
            layer_state = {
                'data': l.data.copy(),
                'name': l.name,
                'visible': l.visible,
                'opacity': l.opacity,
                'blend_mode': int(l.blend_mode),
                'locked': l.locked,
                'layer_type': int(l.layer_type),
                'mask': l.mask.copy() if l.mask is not None else None,
                'mask_enabled': l.mask_enabled,
                'suns': [s.to_dict() for s in l.suns],
                'cloud_settings': l.cloud_settings.to_dict() if l.cloud_settings else None,
                'atmosphere_settings': l.atmosphere_settings.to_dict() if l.atmosphere_settings else None,
                'stamps': [s.to_dict() for s in l.stamps],
                'adjustment': l.adjustment.to_dict() if l.adjustment else None,
            }
            state['layers'].append(layer_state)
        return state

    def _restore_state(self, state: dict):
        """Restore project state from a saved state dict."""
        from src.cloud_engine import CloudSettings
        from src.atmosphere import AtmosphereSettings
        from src.stamp_library import StampInstance

        self.layers.clear()
        for ls in state['layers']:
            layer = HDRILayer(self.width, self.height, ls['name'],
                              layer_type=LayerType(ls.get('layer_type', 0)))
            layer.data = ls['data']
            layer.visible = ls['visible']
            layer.opacity = ls['opacity']
            layer.blend_mode = BlendMode(ls['blend_mode'])
            layer.locked = ls['locked']
            layer.mask = ls.get('mask')
            layer.mask_enabled = ls.get('mask_enabled', False)
            layer.suns = [SunObject.from_dict(d) for d in ls.get('suns', [])]
            cs = ls.get('cloud_settings')
            layer.cloud_settings = CloudSettings.from_dict(cs) if cs else None
            ats = ls.get('atmosphere_settings')
            layer.atmosphere_settings = AtmosphereSettings.from_dict(ats) if ats else None
            layer.stamps = [StampInstance.from_dict(d) for d in ls.get('stamps', [])]
            adj = ls.get('adjustment')
            layer.adjustment = AdjustmentSettings.from_dict(adj) if adj else None
            self.layers.append(layer)

        self.active_layer_index = state['active_index']
        self._cache_dirty = True

    def save_project(self, filepath: str):
        """Save project to a .hdriproject file (ZIP archive)."""
        import zipfile
        import io

        meta = {
            'width': self.width,
            'height': self.height,
            'active_index': self.active_layer_index,
            'layers': []
        }

        with zipfile.ZipFile(filepath, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for idx, l in enumerate(self.layers):
                layer_info = {
                    'name': l.name,
                    'visible': l.visible,
                    'opacity': l.opacity,
                    'blend_mode': int(l.blend_mode),
                    'locked': l.locked,
                    'layer_type': int(l.layer_type),
                    'mask_enabled': l.mask_enabled,
                    'has_mask': l.mask is not None,
                    'suns': [s.to_dict() for s in l.suns],
                    'cloud_settings': l.cloud_settings.to_dict() if l.cloud_settings else None,
                    'atmosphere_settings': l.atmosphere_settings.to_dict() if l.atmosphere_settings else None,
                    'stamps': [s.to_dict() for s in l.stamps],
                    'adjustment': l.adjustment.to_dict() if l.adjustment else None,
                }
                meta['layers'].append(layer_info)

                # Save layer data as numpy bytes
                data_buf = io.BytesIO()
                np.save(data_buf, l.data)
                zf.writestr(f"layer_{idx}_data.npy", data_buf.getvalue())

                # Save mask data if present
                if l.mask is not None:
                    mask_buf = io.BytesIO()
                    np.save(mask_buf, l.mask)
                    zf.writestr(f"layer_{idx}_mask.npy", mask_buf.getvalue())

            zf.writestr("project.json", json.dumps(meta, indent=2))

    def load_project(self, filepath: str):
        """Load project from a .hdriproject file."""
        import zipfile
        import io
        from src.cloud_engine import CloudSettings
        from src.atmosphere import AtmosphereSettings
        from src.stamp_library import StampInstance

        with zipfile.ZipFile(filepath, 'r') as zf:
            meta = json.loads(zf.read("project.json").decode('utf-8'))
            self.width = meta.get('width', self.DEFAULT_WIDTH)
            self.height = meta.get('height', self.DEFAULT_HEIGHT)
            self.layers.clear()

            for idx, linfo in enumerate(meta['layers']):
                layer = HDRILayer(self.width, self.height, linfo['name'],
                                  layer_type=LayerType(linfo.get('layer_type', 0)))
                data_bytes = zf.read(f"layer_{idx}_data.npy")
                layer.data = np.load(io.BytesIO(data_bytes))
                layer.visible = linfo.get('visible', True)
                layer.opacity = linfo.get('opacity', 1.0)
                layer.blend_mode = BlendMode(linfo.get('blend_mode', 0))
                layer.locked = linfo.get('locked', False)
                layer.mask_enabled = linfo.get('mask_enabled', False)
                if linfo.get('has_mask', False):
                    mask_bytes = zf.read(f"layer_{idx}_mask.npy")
                    layer.mask = np.load(io.BytesIO(mask_bytes))
                layer.suns = [SunObject.from_dict(d) for d in linfo.get('suns', [])]
                cs = linfo.get('cloud_settings')
                layer.cloud_settings = CloudSettings.from_dict(cs) if cs else None
                ats = linfo.get('atmosphere_settings')
                layer.atmosphere_settings = AtmosphereSettings.from_dict(ats) if ats else None
                layer.stamps = [StampInstance.from_dict(d) for d in linfo.get('stamps', [])]
                adj = linfo.get('adjustment')
                layer.adjustment = AdjustmentSettings.from_dict(adj) if adj else None
                self.layers.append(layer)

            self.active_layer_index = meta.get('active_index', 0)
            self._undo_stack.clear()
            self._redo_stack.clear()
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
        """Generate a circular brush stamp with SIMD array math."""
        size = size or self.size
        hardness = hardness or self.hardness
        key = (size, int(hardness * 100))

        if key in self._stamp_cache:
            return self._stamp_cache[key]

        diameter = size * 2 + 1
        y, x = np.ogrid[-size:size + 1, -size:size + 1]
        dist = np.sqrt(x * x + y * y) / float(max(size, 1))

        stamp = np.zeros((diameter, diameter), dtype=np.float32)
        if hardness >= 1.0:
            stamp[dist <= 1.0] = 1.0
        else:
            stamp[dist <= hardness] = 1.0
            falloff_mask = (dist > hardness) & (dist <= 1.0)
            t = (dist[falloff_mask] - hardness) / max(1e-5, (1.0 - hardness))
            stamp[falloff_mask] = 1.0 - t * t

        self._stamp_cache[key] = stamp
        return stamp

    def _apply_slice_blend(self, target_data: np.ndarray, stamp_slice: np.ndarray,
                           color_rgb: np.ndarray, opacity: float, erase: bool):
        """Vectorized alpha-blending for an image slice."""
        alpha = stamp_slice[..., np.newaxis] * opacity
        if erase:
            target_data[..., 3:4] *= (1.0 - alpha)
        else:
            old_a = target_data[..., 3:4]
            new_a = np.clip(old_a + alpha * (1.0 - old_a), 0.0, 1.0)
            blend = np.where(new_a > 1e-6, alpha / np.maximum(new_a, 1e-6), 0.0)
            target_data[..., :3] = target_data[..., :3] * (1.0 - blend) + color_rgb * blend
            target_data[..., 3:4] = new_a

    def _apply_slice_mask(self, target_mask: np.ndarray, stamp_slice: np.ndarray,
                          opacity: float, erase: bool, mask_value: float):
        """Vectorized mask brush application."""
        alpha = stamp_slice * opacity
        if erase:
            target_mask[:] = np.maximum(0.0, target_mask - alpha)
        else:
            target_mask[:] = np.minimum(1.0, target_mask + alpha * mask_value)

    def paint_stroke(self, layer: HDRILayer, x: int, y: int, erase: bool = False,
                     paint_mask: bool = False, mask_value: float = 1.0):
        """Paint a single brush stamp at position (x, y) with pure SIMD array slicing."""
        if layer.locked:
            return

        stamp = self.get_stamp()
        radius = self.size
        diameter = radius * 2 + 1
        h, w = layer.height, layer.width

        # Vertical range
        y0 = y - radius
        y1 = y + radius + 1
        py0 = max(0, y0)
        py1 = min(h, y1)
        if py0 >= py1:
            return
        sy0 = py0 - y0
        sy1 = sy0 + (py1 - py0)

        color_rgb = np.array(self.color[:3], dtype=np.float32) * self.intensity

        # Horizontal wrapping handling
        x0 = x - radius
        x1 = x + radius + 1

        segments = []
        if x0 < 0:
            segments.append((w + x0, w, 0, -x0))
            segments.append((0, min(w, x1), -x0, diameter))
        elif x1 > w:
            segments.append((x0, w, 0, w - x0))
            segments.append((0, x1 - w, w - x0, diameter))
        else:
            segments.append((x0, x1, 0, diameter))

        for tx0, tx1, sx0, sx1 in segments:
            if tx0 >= tx1 or sx0 >= sx1:
                continue
            stamp_sub = stamp[sy0:sy1, sx0:sx1]
            if paint_mask and layer.mask is not None:
                self._apply_slice_mask(layer.mask[py0:py1, tx0:tx1], stamp_sub,
                                       self.opacity, erase, mask_value)
            else:
                self._apply_slice_blend(layer.data[py0:py1, tx0:tx1], stamp_sub,
                                        color_rgb, self.opacity, erase)

        layer._thumb_dirty = True

    def paint_line(self, layer: HDRILayer, x0: int, y0: int, x1: int, y1: int,
                   erase: bool = False, paint_mask: bool = False, mask_value: float = 1.0):
        """Paint along a line from (x0,y0) to (x1,y1) using stepped interpolation."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        dist = max(dx, dy, 1)

        step = max(2, self.size // 3)
        num_steps = max(dist // step, 1)

        for i in range(num_steps + 1):
            t = i / num_steps if num_steps > 0 else 0
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            self.paint_stroke(layer, x, y, erase, paint_mask, mask_value)

    def paint_cloud_stroke(self, layer: HDRILayer, x: int, y: int,
                           cloud_settings=None, sun_az: float = 0.25, sun_el: float = 0.25,
                           sun_color=(1.0, 0.95, 0.85)):
        """Paint a procedural cloud brush dab onto the layer with SIMD vectorization."""
        if layer.locked:
            return
        from src.cloud_engine import render_cloud_brush_stamp, CloudSettings
        if cloud_settings is None:
            cloud_settings = CloudSettings.preset_cumulus()

        radius = max(8, self.size)
        diameter = radius * 2
        stamp = render_cloud_brush_stamp(diameter, cloud_settings, sun_az, sun_el, sun_color)

        h, w = layer.height, layer.width
        y0 = y - radius
        y1 = y + radius
        py0 = max(0, y0)
        py1 = min(h, y1)
        if py0 >= py1:
            return
        sy0 = py0 - y0
        sy1 = sy0 + (py1 - py0)

        x0 = x - radius
        x1 = x + radius

        segments = []
        if x0 < 0:
            segments.append((w + x0, w, 0, -x0))
            segments.append((0, min(w, x1), -x0, diameter))
        elif x1 > w:
            segments.append((x0, w, 0, w - x0))
            segments.append((0, x1 - w, w - x0, diameter))
        else:
            segments.append((x0, x1, 0, diameter))

        for tx0, tx1, sx0, sx1 in segments:
            if tx0 >= tx1 or sx0 >= sx1:
                continue
            stamp_sub = stamp[sy0:sy1, sx0:sx1]
            alpha = stamp_sub[..., 3:4] * self.opacity
            rgb = stamp_sub[..., :3] * self.intensity

            target = layer.data[py0:py1, tx0:tx1]
            old_a = target[..., 3:4]
            new_a = np.clip(old_a + alpha * (1.0 - old_a), 0.0, 1.0)
            blend = np.where(new_a > 1e-6, alpha / np.maximum(new_a, 1e-6), 0.0)
            target[..., :3] = target[..., :3] * (1.0 - blend) + rgb * blend
            target[..., 3:4] = new_a

        layer._thumb_dirty = True

    def paint_cloud_line(self, layer: HDRILayer, x0: int, y0: int, x1: int, y1: int,
                         cloud_settings=None, sun_az: float = 0.25, sun_el: float = 0.25,
                         sun_color=(1.0, 0.95, 0.85)):
        """Paint cloud brush smoothly along a line."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        dist = max(dx, dy, 1)
        step = max(6, self.size // 2)
        num_steps = max(dist // step, 1)
        for i in range(num_steps + 1):
            t = i / num_steps if num_steps > 0 else 0
            x = int(x0 + (x1 - x0) * t)
            y = int(y0 + (y1 - y0) * t)
            self.paint_cloud_stroke(layer, x, y, cloud_settings, sun_az, sun_el, sun_color)


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
