"""
Atmosphere Engine for HDRI Maker.
Physically-based sky rendering using simplified Preetham/Hosek-Wilkie model.
Supports color temperature conversion, atmospheric scattering, and time-of-day.
"""

import numpy as np
import math
from typing import Tuple, Optional


# ============================================================
#  COLOR TEMPERATURE
# ============================================================

def kelvin_to_rgb(temperature: float) -> Tuple[float, float, float]:
    """
    Convert color temperature in Kelvin to RGB values (0-1 range).
    Uses Tanner Helland's algorithm, valid for 1000K–40000K.
    """
    temp = max(1000, min(40000, temperature)) / 100.0

    # Red
    if temp <= 66:
        r = 1.0
    else:
        r = temp - 60
        r = 329.698727446 * (r ** -0.1332047592) / 255.0
        r = max(0.0, min(1.0, r))

    # Green
    if temp <= 66:
        g = 99.4708025861 * math.log(temp) - 161.1195681661
        g = max(0.0, min(255.0, g)) / 255.0
    else:
        g = temp - 60
        g = 288.1221695283 * (g ** -0.0755148492) / 255.0
        g = max(0.0, min(1.0, g))

    # Blue
    if temp >= 66:
        b = 1.0
    elif temp <= 19:
        b = 0.0
    else:
        b = temp - 10
        b = 138.5177312231 * math.log(b) - 305.0447927307
        b = max(0.0, min(255.0, b)) / 255.0

    return (r, g, b)


# ============================================================
#  ATMOSPHERE DATA
# ============================================================

class AtmosphereSettings:
    """Configuration for atmosphere/sky rendering."""

    def __init__(self):
        # Sky colors
        self.zenith_color = (0.15, 0.3, 0.8)
        self.horizon_color = (0.6, 0.7, 0.9)
        self.ground_color = (0.12, 0.1, 0.08)

        # Scattering
        self.rayleigh_intensity = 1.0
        self.mie_intensity = 0.5
        self.mie_directionality = 0.76  # Henyey-Greenstein g parameter

        # Haze / fog
        self.haze_density = 0.0
        self.haze_color = (0.7, 0.75, 0.8)
        self.haze_height = 0.5  # Height of haze layer

        # Time of day
        self.time_of_day = 12.0  # 0-24 hours
        self.use_physical = True  # Use physical sky model vs manual colors

        # Exposure
        self.sky_intensity = 1.0

    def copy(self) -> 'AtmosphereSettings':
        a = AtmosphereSettings()
        a.zenith_color = self.zenith_color
        a.horizon_color = self.horizon_color
        a.ground_color = self.ground_color
        a.rayleigh_intensity = self.rayleigh_intensity
        a.mie_intensity = self.mie_intensity
        a.mie_directionality = self.mie_directionality
        a.haze_density = self.haze_density
        a.haze_color = self.haze_color
        a.haze_height = self.haze_height
        a.time_of_day = self.time_of_day
        a.use_physical = self.use_physical
        a.sky_intensity = self.sky_intensity
        return a

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> 'AtmosphereSettings':
        a = cls()
        for k, v in d.items():
            if hasattr(a, k):
                setattr(a, k, v)
        return a


# ============================================================
#  TIME OF DAY PRESETS
# ============================================================

TIME_PRESETS = {
    "dawn": {
        "time": 5.5,
        "sun_elevation": 0.42,
        "sun_temperature": 2200,
        "sky_intensity": 0.4,
        "zenith": (0.15, 0.12, 0.25),
        "horizon": (0.8, 0.4, 0.2),
        "ground": (0.05, 0.04, 0.03),
    },
    "morning": {
        "time": 8.0,
        "sun_elevation": 0.32,
        "sun_temperature": 4000,
        "sky_intensity": 0.8,
        "zenith": (0.2, 0.35, 0.75),
        "horizon": (0.7, 0.65, 0.6),
        "ground": (0.1, 0.09, 0.07),
    },
    "noon": {
        "time": 12.0,
        "sun_elevation": 0.2,
        "sun_temperature": 5500,
        "sky_intensity": 1.0,
        "zenith": (0.15, 0.3, 0.85),
        "horizon": (0.55, 0.65, 0.85),
        "ground": (0.12, 0.11, 0.09),
    },
    "afternoon": {
        "time": 15.0,
        "sun_elevation": 0.28,
        "sun_temperature": 5000,
        "sky_intensity": 0.9,
        "zenith": (0.18, 0.32, 0.8),
        "horizon": (0.6, 0.6, 0.7),
        "ground": (0.11, 0.1, 0.08),
    },
    "golden_hour": {
        "time": 17.5,
        "sun_elevation": 0.38,
        "sun_temperature": 3200,
        "sky_intensity": 0.7,
        "zenith": (0.2, 0.25, 0.55),
        "horizon": (0.9, 0.55, 0.25),
        "ground": (0.1, 0.07, 0.04),
    },
    "sunset": {
        "time": 18.5,
        "sun_elevation": 0.44,
        "sun_temperature": 2500,
        "sky_intensity": 0.5,
        "zenith": (0.12, 0.12, 0.35),
        "horizon": (0.95, 0.35, 0.1),
        "ground": (0.06, 0.04, 0.03),
    },
    "dusk": {
        "time": 19.5,
        "sun_elevation": 0.48,
        "sun_temperature": 2000,
        "sky_intensity": 0.2,
        "zenith": (0.06, 0.05, 0.15),
        "horizon": (0.4, 0.15, 0.08),
        "ground": (0.03, 0.02, 0.02),
    },
    "night": {
        "time": 22.0,
        "sun_elevation": 0.7,
        "sun_temperature": 8000,
        "sky_intensity": 0.02,
        "zenith": (0.005, 0.005, 0.015),
        "horizon": (0.01, 0.01, 0.02),
        "ground": (0.005, 0.005, 0.005),
    },
}


def time_to_sun_position(time_of_day: float, latitude: float = 45.0) -> Tuple[float, float]:
    """
    Convert time of day (0-24) to sun azimuth and elevation (both 0-1 normalized).

    Returns:
        (azimuth, elevation) — azimuth 0-1, elevation 0-1 (0=top/zenith, 0.5=horizon)
    """
    # Simple sinusoidal model
    hour_angle = (time_of_day - 12.0) / 24.0 * 2.0 * math.pi

    lat_rad = math.radians(latitude)
    declination = math.radians(23.44)  # Summer solstice

    sin_alt = (math.sin(lat_rad) * math.sin(declination) +
               math.cos(lat_rad) * math.cos(declination) * math.cos(hour_angle))
    altitude = math.asin(max(-1, min(1, sin_alt)))

    # Azimuth
    cos_az = ((math.sin(declination) - math.sin(altitude) * math.sin(lat_rad)) /
              max(math.cos(altitude) * math.cos(lat_rad), 0.001))
    cos_az = max(-1, min(1, cos_az))
    azimuth = math.acos(cos_az)
    if hour_angle > 0:
        azimuth = 2 * math.pi - azimuth

    # Normalize to 0-1
    az_norm = azimuth / (2 * math.pi)
    # Convert altitude to elevation (0=zenith, 0.5=horizon, 1=nadir)
    el_norm = 0.5 - altitude / math.pi

    return (az_norm, max(0.05, min(0.95, el_norm)))


# ============================================================
#  PHYSICAL SKY RENDERER
# ============================================================

def render_atmosphere(data: np.ndarray, settings: AtmosphereSettings,
                      sun_azimuth: float = 0.25, sun_elevation: float = 0.25,
                      sun_intensity: float = 10.0,
                      sun_color: Tuple[float, float, float] = (1.0, 0.95, 0.85)):
    """
    Render a physically-inspired atmosphere into an RGBA float32 array.

    Uses simplified Rayleigh + Mie scattering for the sky gradient,
    with sun disc and atmospheric glow.

    Args:
        data: Output array (H, W, 4), float32
        settings: AtmosphereSettings configuration
        sun_azimuth: Sun horizontal position (0-1)
        sun_elevation: Sun vertical position (0-1, 0=top)
        sun_intensity: Sun disc brightness
        sun_color: Sun base color
    """
    h, w, c = data.shape

    us = np.linspace(0, 1, w, dtype=np.float32)
    vs = np.linspace(0, 1, h, dtype=np.float32)
    uu, vv = np.meshgrid(us, vs)

    # Convert to spherical direction vectors
    theta = uu * 2.0 * np.pi
    phi = vv * np.pi

    dx = np.sin(phi) * np.cos(theta)
    dy = np.cos(phi)
    dz = np.sin(phi) * np.sin(theta)

    # Sun direction
    sun_theta = sun_azimuth * 2.0 * np.pi
    sun_phi = sun_elevation * np.pi
    sun_dx = np.sin(sun_phi) * np.cos(sun_theta)
    sun_dy = np.cos(sun_phi)
    sun_dz = np.sin(sun_phi) * np.sin(sun_theta)

    # Dot product with sun
    cos_angle = dx * sun_dx + dy * sun_dy + dz * sun_dz

    # Sky/ground mask
    sky_mask = vv < 0.5
    ground_mask = ~sky_mask

    if settings.use_physical:
        # === Physical sky ===
        # Rayleigh scattering: ~1/λ^4, stronger blue scatter
        # Simplified: blue is stronger at high angles from sun
        rayleigh_factor = (1 + cos_angle ** 2) * 0.75
        rayleigh = np.zeros((h, w, 3), dtype=np.float32)
        # More blue scattering
        rayleigh[:, :, 0] = rayleigh_factor * 0.3 * settings.rayleigh_intensity
        rayleigh[:, :, 1] = rayleigh_factor * 0.5 * settings.rayleigh_intensity
        rayleigh[:, :, 2] = rayleigh_factor * 1.0 * settings.rayleigh_intensity

        # Mie scattering: forward scattering, creates bright halo around sun
        g = settings.mie_directionality
        mie_phase = (1 - g ** 2) / ((4 * np.pi) * (1 + g ** 2 - 2 * g * cos_angle) ** 1.5)
        mie = np.zeros((h, w, 3), dtype=np.float32)
        mie[:, :, 0] = mie_phase * sun_color[0] * settings.mie_intensity
        mie[:, :, 1] = mie_phase * sun_color[1] * settings.mie_intensity
        mie[:, :, 2] = mie_phase * sun_color[2] * settings.mie_intensity

        # Height-based color gradient (zenith to horizon)
        zenith_factor = np.clip(1.0 - vv / 0.5, 0, 1) ** 1.5
        horizon_factor = 1.0 - zenith_factor

        sky_color = np.zeros((h, w, 3), dtype=np.float32)
        for ci in range(3):
            sky_color[:, :, ci] = (
                settings.zenith_color[ci] * zenith_factor +
                settings.horizon_color[ci] * horizon_factor
            )

        # Combine sky components
        total_sky = (sky_color + rayleigh * 0.3 + mie * 0.5) * settings.sky_intensity

        # Ground color
        ground_factor = np.clip(np.sqrt(np.maximum(0.0, (vv - 0.5) / 0.5)), 0, 1)

        for ci in range(3):
            data[:, :, ci] = np.where(
                sky_mask,
                total_sky[:, :, ci],
                settings.horizon_color[ci] + ground_factor * (
                    settings.ground_color[ci] - settings.horizon_color[ci]
                )
            )
    else:
        # === Manual color mode ===
        t_sky = np.clip(1.0 - vv / 0.5, 0, 1) ** 2
        t_ground = np.clip(np.sqrt((vv - 0.5) / 0.5), 0, 1)

        for ci in range(3):
            data[:, :, ci] = np.where(
                sky_mask,
                settings.horizon_color[ci] + t_sky * (
                    settings.zenith_color[ci] - settings.horizon_color[ci]
                ),
                settings.horizon_color[ci] + t_ground * (
                    settings.ground_color[ci] - settings.horizon_color[ci]
                )
            ) * settings.sky_intensity

    # === Sun disc ===
    sun_disc_size = 0.02
    cos_disc = np.cos(sun_disc_size)
    sun_mask_disc = cos_angle > cos_disc

    if np.any(sun_mask_disc):
        sun_factor = ((cos_angle[sun_mask_disc] - cos_disc) / (1.0 - cos_disc)) ** 2
        # Limb darkening
        limb = 0.7 + 0.3 * sun_factor
        data[:, :, 0][sun_mask_disc] += sun_intensity * sun_color[0] * sun_factor * limb
        data[:, :, 1][sun_mask_disc] += sun_intensity * sun_color[1] * sun_factor * limb
        data[:, :, 2][sun_mask_disc] += sun_intensity * sun_color[2] * sun_factor * limb

    # === Sun glow ===
    glow = np.power(np.clip(cos_angle, 0, None), 32) * sun_intensity * 0.15
    data[:, :, 0] += glow * sun_color[0]
    data[:, :, 1] += glow * sun_color[1]
    data[:, :, 2] += glow * sun_color[2]

    # === Haze ===
    if settings.haze_density > 0:
        # Haze concentrated near horizon
        haze_factor = np.exp(-np.abs(vv - settings.haze_height) * 10) * settings.haze_density
        for ci in range(3):
            data[:, :, ci] += haze_factor * settings.haze_color[ci] * settings.sky_intensity

    # Alpha
    data[:, :, 3] = 1.0


def render_god_rays(data: np.ndarray, sun_x: float, sun_y: float,
                    intensity: float = 0.3, num_rays: int = 64,
                    ray_length: float = 0.4):
    """
    Add crepuscular rays (god rays) emanating from sun position.

    Args:
        data: RGBA float32 array to modify (in-place)
        sun_x: Sun horizontal position (0-1)
        sun_y: Sun vertical position (0-1)
        intensity: Ray brightness
        num_rays: Number of sampling rays
        ray_length: Maximum ray length (normalized)
    """
    h, w, c = data.shape

    us = np.linspace(0, 1, w, dtype=np.float32)
    vs = np.linspace(0, 1, h, dtype=np.float32)
    uu, vv = np.meshgrid(us, vs)

    # Direction from each pixel towards sun
    dx = sun_x - uu
    dy = sun_y - vv
    dist = np.sqrt(dx ** 2 + dy ** 2)
    dist_norm = dist / max(ray_length, 0.01)

    # Radial blur effect
    ray_accumulator = np.zeros((h, w), dtype=np.float32)

    for i in range(num_rays):
        t = (i + 1) / num_rays * ray_length
        safe_dist = np.maximum(dist, 0.001)
        sample_x = (uu + dx * t / safe_dist * t)
        sample_y = (vv + dy * t / safe_dist * t)

        # Clamp and sample
        sx = np.clip((sample_x * w).astype(int), 0, w - 1)
        sy = np.clip((sample_y * h).astype(int), 0, h - 1)

        # Sample luminance
        lum = 0.2126 * data[sy, sx, 0] + 0.7152 * data[sy, sx, 1] + 0.0722 * data[sy, sx, 2]
        ray_accumulator += lum

    ray_accumulator /= num_rays

    # Falloff with distance from sun
    falloff = np.exp(-dist_norm * 3)

    ray_contribution = ray_accumulator * falloff * intensity

    data[:, :, 0] += ray_contribution * 1.0
    data[:, :, 1] += ray_contribution * 0.95
    data[:, :, 2] += ray_contribution * 0.8


def add_stars(data: np.ndarray, density: float = 0.001, brightness: float = 0.5,
              seed: int = 42):
    """Add procedural stars to a night sky."""
    h, w, c = data.shape
    rng = np.random.RandomState(seed)

    # Only add stars above horizon and in dark areas
    vs = np.linspace(0, 1, h)
    sky_mask = vs < 0.48

    num_stars = int(w * h * density)
    star_x = rng.randint(0, w, num_stars)
    star_y = rng.randint(0, int(h * 0.48), num_stars)
    star_brightness = rng.random(num_stars).astype(np.float32) ** 3 * brightness

    # Star color temperature variation
    star_temps = rng.uniform(3000, 12000, num_stars)

    for i in range(num_stars):
        x, y = star_x[i], star_y[i]
        b = star_brightness[i]
        temp = star_temps[i]
        r, g, bl = kelvin_to_rgb(temp)

        # Only add if sky is dark enough at this position
        existing_lum = (data[y, x, 0] * 0.2126 + data[y, x, 1] * 0.7152 +
                        data[y, x, 2] * 0.0722)
        if existing_lum < 0.1:
            data[y, x, 0] += r * b
            data[y, x, 1] += g * b
            data[y, x, 2] += bl * b

            # Add tiny bloom to bright stars
            if b > brightness * 0.5 and x > 0 and x < w - 1 and y > 0 and y < h - 1:
                bloom = b * 0.2
                data[y - 1, x, :3] += np.array([r, g, bl]) * bloom
                data[y + 1, x, :3] += np.array([r, g, bl]) * bloom
                data[y, x - 1, :3] += np.array([r, g, bl]) * bloom
                data[y, x + 1, :3] += np.array([r, g, bl]) * bloom
