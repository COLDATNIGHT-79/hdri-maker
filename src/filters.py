"""
Filters module for HDRI Maker.
Provides dialog-based filter effects that can be applied to layers.
"""

from pathlib import Path
import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDialogButtonBox, QGroupBox, QComboBox, QFormLayout,
    QCheckBox, QPushButton, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, Signal
from typing import Tuple


class FilterDialog(QDialog):
    """Base dialog for filter parameters with live preview."""

    preview_requested = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)
        self._layout = QVBoxLayout(self)
        self._form = QFormLayout()
        self._layout.addLayout(self._form)

        # Buttons
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._layout.addWidget(self._buttons)

    def _add_slider(self, label: str, min_val: int, max_val: int,
                     default: int, callback=None) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        value_label = QLabel(str(default))
        value_label.setMinimumWidth(40)

        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(value_label)

        def on_change(val):
            value_label.setText(str(val))
            if callback:
                callback(val)
            self.preview_requested.emit()

        slider.valueChanged.connect(on_change)
        self._form.addRow(label, row)
        return slider


class GaussianBlurDialog(FilterDialog):
    """Gaussian blur filter settings."""

    def __init__(self, parent=None):
        super().__init__("Gaussian Blur", parent)
        self.sigma_slider = self._add_slider("Sigma:", 1, 100, 20)

    @property
    def sigma(self) -> float:
        return self.sigma_slider.value() / 10.0


class BloomDialog(FilterDialog):
    """Bloom/glow filter settings."""

    def __init__(self, parent=None):
        super().__init__("Bloom / Glow", parent)
        self.threshold_slider = self._add_slider("Threshold:", 1, 100, 50)
        self.intensity_slider = self._add_slider("Intensity:", 1, 100, 30)
        self.radius_slider = self._add_slider("Radius:", 1, 200, 50)

    @property
    def threshold(self) -> float:
        return self.threshold_slider.value() / 10.0

    @property
    def intensity(self) -> float:
        return self.intensity_slider.value() / 10.0

    @property
    def radius(self) -> float:
        return self.radius_slider.value() / 10.0


class ColorGradeDialog(FilterDialog):
    """Color grading (Lift/Gamma/Gain) dialog."""

    def __init__(self, parent=None):
        super().__init__("Color Grading", parent)

        # Lift (shadows)
        group_lift = QGroupBox("Lift (Shadows)")
        lift_layout = QFormLayout()
        self.lift_r = self._make_grading_slider(lift_layout, "Red:", 0)
        self.lift_g = self._make_grading_slider(lift_layout, "Green:", 0)
        self.lift_b = self._make_grading_slider(lift_layout, "Blue:", 0)
        group_lift.setLayout(lift_layout)
        self._layout.insertWidget(self._layout.count() - 1, group_lift)

        # Gamma (midtones)
        group_gamma = QGroupBox("Gamma (Midtones)")
        gamma_layout = QFormLayout()
        self.gamma_r = self._make_grading_slider(gamma_layout, "Red:", 100)
        self.gamma_g = self._make_grading_slider(gamma_layout, "Green:", 100)
        self.gamma_b = self._make_grading_slider(gamma_layout, "Blue:", 100)
        group_gamma.setLayout(gamma_layout)
        self._layout.insertWidget(self._layout.count() - 1, group_gamma)

        # Gain (highlights)
        group_gain = QGroupBox("Gain (Highlights)")
        gain_layout = QFormLayout()
        self.gain_r = self._make_grading_slider(gain_layout, "Red:", 100)
        self.gain_g = self._make_grading_slider(gain_layout, "Green:", 100)
        self.gain_b = self._make_grading_slider(gain_layout, "Blue:", 100)
        group_gain.setLayout(gain_layout)
        self._layout.insertWidget(self._layout.count() - 1, group_gain)

    def _make_grading_slider(self, layout, label, default):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(-100, 200)
        slider.setValue(default)
        val_label = QLabel(f"{default / 100:.2f}")
        val_label.setMinimumWidth(45)

        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(val_label)

        slider.valueChanged.connect(lambda v: val_label.setText(f"{v / 100:.2f}"))
        slider.valueChanged.connect(lambda: self.preview_requested.emit())
        layout.addRow(label, row)
        return slider

    @property
    def lift(self) -> Tuple[float, float, float]:
        return (self.lift_r.value() / 100.0,
                self.lift_g.value() / 100.0,
                self.lift_b.value() / 100.0)

    @property
    def gamma(self) -> Tuple[float, float, float]:
        return (max(self.gamma_r.value() / 100.0, 0.01),
                max(self.gamma_g.value() / 100.0, 0.01),
                max(self.gamma_b.value() / 100.0, 0.01))

    @property
    def gain(self) -> Tuple[float, float, float]:
        return (self.gain_r.value() / 100.0,
                self.gain_g.value() / 100.0,
                self.gain_b.value() / 100.0)


class NoiseDialog(FilterDialog):
    """Add noise dialog."""

    def __init__(self, parent=None):
        super().__init__("Add Noise", parent)
        self.intensity_slider = self._add_slider("Intensity:", 1, 100, 10)

    @property
    def intensity(self) -> float:
        return self.intensity_slider.value() / 100.0


class VignetteDialog(FilterDialog):
    """Vignette effect dialog."""

    def __init__(self, parent=None):
        super().__init__("Vignette", parent)
        self.strength_slider = self._add_slider("Strength:", 1, 100, 50)
        self.radius_slider = self._add_slider("Radius:", 10, 100, 70)

    @property
    def strength(self) -> float:
        return self.strength_slider.value() / 100.0

    @property
    def radius(self) -> float:
        return self.radius_slider.value() / 100.0


class SkyGeneratorDialog(FilterDialog):
    """Procedural sky generation dialog."""

    def __init__(self, parent=None):
        super().__init__("Generate Procedural Sky", parent)
        self.setMinimumWidth(400)

        # Preset selector
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Clear Day", "Golden Hour", "Sunset", "Overcast",
            "Night Sky", "Alien World", "Custom"
        ])
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        self._form.addRow("Preset:", self.preset_combo)

        # Sun settings
        sun_group = QGroupBox("Sun")
        sun_layout = QFormLayout()
        self.sun_intensity_slider = self._add_slider_to(sun_layout, "Intensity:", 0, 500, 100)
        self.sun_x_slider = self._add_slider_to(sun_layout, "Azimuth:", 0, 100, 25)
        self.sun_y_slider = self._add_slider_to(sun_layout, "Elevation:", 0, 100, 25)
        self.sun_size_slider = self._add_slider_to(sun_layout, "Size:", 1, 50, 5)
        sun_group.setLayout(sun_layout)
        self._layout.insertWidget(self._layout.count() - 1, sun_group)

        self._apply_preset(0)  # Default: Clear Day

    def _add_slider_to(self, layout, label, min_v, max_v, default):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_v, max_v)
        slider.setValue(default)
        val_label = QLabel(str(default))
        val_label.setMinimumWidth(40)

        row = QHBoxLayout()
        row.addWidget(slider)
        row.addWidget(val_label)

        slider.valueChanged.connect(lambda v: val_label.setText(str(v)))
        layout.addRow(label, row)
        return slider

    def _apply_preset(self, index):
        presets = {
            0: {  # Clear Day
                'horizon': (0.6, 0.7, 0.9),
                'zenith': (0.2, 0.4, 0.9),
                'ground': (0.15, 0.12, 0.08),
                'sun_intensity': 100, 'sun_x': 25, 'sun_y': 25, 'sun_size': 5
            },
            1: {  # Golden Hour
                'horizon': (0.9, 0.5, 0.2),
                'zenith': (0.3, 0.3, 0.6),
                'ground': (0.12, 0.08, 0.04),
                'sun_intensity': 80, 'sun_x': 50, 'sun_y': 40, 'sun_size': 8
            },
            2: {  # Sunset
                'horizon': (0.95, 0.3, 0.1),
                'zenith': (0.15, 0.15, 0.4),
                'ground': (0.08, 0.05, 0.03),
                'sun_intensity': 60, 'sun_x': 30, 'sun_y': 45, 'sun_size': 10
            },
            3: {  # Overcast
                'horizon': (0.5, 0.52, 0.55),
                'zenith': (0.4, 0.42, 0.48),
                'ground': (0.12, 0.11, 0.1),
                'sun_intensity': 10, 'sun_x': 50, 'sun_y': 30, 'sun_size': 20
            },
            4: {  # Night Sky
                'horizon': (0.02, 0.03, 0.06),
                'zenith': (0.005, 0.005, 0.02),
                'ground': (0.01, 0.01, 0.01),
                'sun_intensity': 5, 'sun_x': 70, 'sun_y': 20, 'sun_size': 3
            },
            5: {  # Alien World
                'horizon': (0.3, 0.8, 0.4),
                'zenith': (0.5, 0.1, 0.6),
                'ground': (0.2, 0.15, 0.1),
                'sun_intensity': 150, 'sun_x': 15, 'sun_y': 30, 'sun_size': 12
            },
        }
        if index in presets:
            p = presets[index]
            self._current_horizon = p['horizon']
            self._current_zenith = p['zenith']
            self._current_ground = p['ground']
            self.sun_intensity_slider.setValue(p['sun_intensity'])
            self.sun_x_slider.setValue(p['sun_x'])
            self.sun_y_slider.setValue(p['sun_y'])
            self.sun_size_slider.setValue(p['sun_size'])
        else:
            self._current_horizon = (0.5, 0.5, 0.5)
            self._current_zenith = (0.3, 0.3, 0.5)
            self._current_ground = (0.1, 0.1, 0.1)

    @property
    def horizon_color(self):
        return self._current_horizon

    @property
    def zenith_color(self):
        return self._current_zenith

    @property
    def ground_color(self):
        return self._current_ground

    @property
    def sun_intensity(self) -> float:
        return self.sun_intensity_slider.value() / 10.0

    @property
    def sun_x(self) -> float:
        return self.sun_x_slider.value() / 100.0

    @property
    def sun_y(self) -> float:
        return self.sun_y_slider.value() / 100.0

    @property
    def sun_size(self) -> float:
        return self.sun_size_slider.value() / 100.0


class GradientFillDialog(FilterDialog):
    """Gradient fill dialog for creating smooth color transitions."""

    def __init__(self, parent=None):
        super().__init__("Gradient Fill", parent)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems([
            "Top to Bottom", "Bottom to Top",
            "Left to Right", "Right to Left",
            "Radial (Center Out)", "Radial (Edges In)"
        ])
        self._form.addRow("Direction:", self.direction_combo)

        self.intensity_slider = self._add_slider("Intensity:", 1, 200, 10)

    @property
    def direction(self) -> int:
        return self.direction_combo.currentIndex()

    @property
    def intensity(self) -> float:
        return self.intensity_slider.value() / 10.0


# ============================================================
#  FILTER APPLY FUNCTIONS
# ============================================================

def apply_vignette(data: np.ndarray, strength: float, radius: float):
    """Apply vignette effect to the image data (in-place)."""
    h, w = data.shape[:2]
    y_coords = np.linspace(-1, 1, h)
    x_coords = np.linspace(-1, 1, w)
    xx, yy = np.meshgrid(x_coords, y_coords)
    dist = np.sqrt(xx ** 2 + yy ** 2)

    # Create vignette mask
    mask = 1.0 - np.clip((dist - radius) / (1.0 - radius + 0.001), 0, 1) * strength
    mask = mask[:, :, np.newaxis]

    data[:, :, :3] *= mask


def apply_gradient_fill(data: np.ndarray, color: Tuple[float, float, float],
                         direction: int, intensity: float):
    """Apply a gradient fill to the image data (additive)."""
    h, w = data.shape[:2]

    if direction == 0:  # Top to bottom
        grad = np.linspace(1, 0, h)[:, np.newaxis]
    elif direction == 1:  # Bottom to top
        grad = np.linspace(0, 1, h)[:, np.newaxis]
    elif direction == 2:  # Left to right
        grad = np.linspace(1, 0, w)[np.newaxis, :]
    elif direction == 3:  # Right to left
        grad = np.linspace(0, 1, w)[np.newaxis, :]
    elif direction == 4:  # Radial center out
        y = np.linspace(-1, 1, h)[:, np.newaxis]
        x = np.linspace(-1, 1, w)[np.newaxis, :]
        grad = 1.0 - np.sqrt(x ** 2 + y ** 2) / np.sqrt(2)
        grad = np.clip(grad, 0, 1)
    else:  # Radial edges in
        y = np.linspace(-1, 1, h)[:, np.newaxis]
        x = np.linspace(-1, 1, w)[np.newaxis, :]
        grad = np.sqrt(x ** 2 + y ** 2) / np.sqrt(2)
        grad = np.clip(grad, 0, 1)

    for c in range(3):
        data[:, :, c] += grad * color[c] * intensity


# ============================================================
#  ADVANCED ENVIRONMENT & EXPORT DIALOGS
# ============================================================

class AtmosphereDialog(FilterDialog):
    """Dialog for physically-based Rayleigh and Mie atmospheric scattering."""

    def __init__(self, parent=None):
        super().__init__("Atmosphere & Sky Scattering", parent)

        self.time_slider = self._add_slider("Time of Day (h):", 0, 240, 120)  # 0 - 24 hours
        self.turbidity_slider = self._add_slider("Turbidity (Haze):", 10, 80, 25)
        self.rayleigh_slider = self._add_slider("Rayleigh Scattering:", 2, 30, 10)
        self.mie_slider = self._add_slider("Mie Scattering:", 2, 30, 10)
        self.haze_slider = self._add_slider("Ground Haze:", 0, 100, 20)

        self.stars_check = QCheckBox("Add Night Stars")
        self.stars_check.setChecked(False)
        self._form.addRow("", self.stars_check)

    @property
    def time_of_day(self) -> float:
        return self.time_slider.value() / 10.0

    @property
    def turbidity(self) -> float:
        return self.turbidity_slider.value() / 10.0

    @property
    def rayleigh(self) -> float:
        return self.rayleigh_slider.value() / 10.0

    @property
    def mie(self) -> float:
        return self.mie_slider.value() / 10.0

    @property
    def haze(self) -> float:
        return self.haze_slider.value() / 100.0

    @property
    def include_stars(self) -> bool:
        return self.stars_check.isChecked()


class GodRaysDialog(FilterDialog):
    """Dialog for crepuscular light rays through atmosphere."""

    def __init__(self, parent=None):
        super().__init__("God Rays / Crepuscular Rays", parent)

        self.intensity_slider = self._add_slider("Ray Intensity:", 5, 200, 50)
        self.decay_slider = self._add_slider("Ray Decay:", 80, 99, 95)
        self.density_slider = self._add_slider("Ray Density:", 10, 150, 80)
        self.weight_slider = self._add_slider("Ray Weight:", 10, 100, 50)

    @property
    def intensity(self) -> float:
        return self.intensity_slider.value() / 100.0

    @property
    def decay(self) -> float:
        return self.decay_slider.value() / 100.0

    @property
    def density(self) -> float:
        return self.density_slider.value() / 100.0

    @property
    def weight(self) -> float:
        return self.weight_slider.value() / 100.0


class CloudGeneratorDialog(FilterDialog):
    """Dialog for procedural cloud field generation."""

    def __init__(self, parent=None):
        super().__init__("Procedural Cloud Generator", parent)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Cumulus (Fluffy / Sunny)",
            "Cirrus (High / Wispy)",
            "Stratus (Overcast / Low)",
            "Wispy (Ethereal)",
            "Storm (Heavy / Ominous)",
            "Sunset (Golden Glow)"
        ])
        self._form.addRow("Preset:", self.preset_combo)

        self.coverage_slider = self._add_slider("Cloud Coverage:", 10, 100, 50)
        self.density_slider = self._add_slider("Cloud Density:", 10, 200, 100)
        self.softness_slider = self._add_slider("Edge Softness:", 0, 100, 40)
        self.seed_slider = self._add_slider("Random Seed:", 1, 999, 42)

        self.auto_sun_check = QCheckBox("Sun Directional Illumination")
        self.auto_sun_check.setChecked(True)
        self._form.addRow("", self.auto_sun_check)

    @property
    def preset_index(self) -> int:
        return self.preset_combo.currentIndex()

    @property
    def coverage(self) -> float:
        return self.coverage_slider.value() / 100.0

    @property
    def density(self) -> float:
        return self.density_slider.value() / 100.0

    @property
    def softness(self) -> float:
        return self.softness_slider.value() / 100.0

    @property
    def seed(self) -> int:
        return self.seed_slider.value()

    @property
    def auto_sun(self) -> bool:
        return self.auto_sun_check.isChecked()


class SunPropertiesDialog(FilterDialog):
    """Dialog to inspect and configure sun settings."""

    def __init__(self, sun, parent=None):
        super().__init__("Sun Light Properties", parent)
        self.sun = sun

        self.temp_slider = self._add_slider("Temperature (Kelvin):", 1800, 12000, int(sun.temperature))
        self.intensity_slider = self._add_slider("Intensity:", 1, 200, int(sun.intensity * 2))
        self.disc_slider = self._add_slider("Disc Size:", 2, 60, int(sun.disc_size * 500))
        self.halo_r_slider = self._add_slider("Halo Radius:", 10, 200, int(sun.halo_radius * 1000))
        self.halo_i_slider = self._add_slider("Halo Intensity:", 0, 100, int(sun.halo_intensity * 100))

        self.flare_check = QCheckBox("Enable Starburst Flare")
        self.flare_check.setChecked(sun.flare_enabled)
        self._form.addRow("", self.flare_check)

    def apply_to_sun(self):
        self.sun.temperature = float(self.temp_slider.value())
        self.sun.intensity = self.intensity_slider.value() / 2.0
        self.sun.disc_size = self.disc_slider.value() / 500.0
        self.sun.halo_radius = self.halo_r_slider.value() / 1000.0
        self.sun.halo_intensity = self.halo_i_slider.value() / 100.0
        self.sun.flare_enabled = self.flare_check.isChecked()


class ExportPresetsDialog(FilterDialog):
    """Dialog for one-click cross-engine export presets."""

    def __init__(self, parent=None):
        super().__init__("Cross-Engine Export Preset", parent)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Blender (.hdr + Python Scene Setup)",
            "Unity (.hdr + Cubemap 6-Face + C# Importer)",
            "Unreal Engine (.hdr + Setup Script + Light Config)",
            "Godot (.hdr + GDScript + WorldEnvironment)",
            "All Engines (Full Package for All Engines)",
            "Web / Preview (Tone-mapped PNG + Cubemap)"
        ])
        self._form.addRow("Target Engine:", self.preset_combo)

        # Output folder
        from PySide6.QtWidgets import QLineEdit
        self.dir_edit = QLineEdit(str(Path.home() / "Desktop"))
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_edit)
        dir_row.addWidget(btn_browse)
        self._form.addRow("Export Folder:", dir_row)

        self.name_edit = QLineEdit("hdri_environment")
        self._form.addRow("Filename:", self.name_edit)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #aaa; font-size: 10px; margin-top: 6px;")
        self._form.addRow(self.desc_label)

        self.preset_combo.currentIndexChanged.connect(self._update_desc)
        self._update_desc(0)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _update_desc(self, idx):
        descriptions = [
            "Exports Radiance .hdr file and a Python script that sets up world environment, sun lamp rotation, and Cycles/EEVEE render parameters in Blender.",
            "Exports .hdr file, 6 cubemap face textures (+X, -X, +Y, -Y, +Z, -Z), and copies the Unity C# importer script.",
            "Exports .hdr file, Unreal Python setup script, and directional light configuration matching HDRI sun angle.",
            "Exports .hdr file, Godot GDScript, and WorldEnvironment node setup for PanoramaSkyMaterial.",
            "Exports all formats simultaneously: .hdr, .exr, .png, cubemaps, Blender script, Unreal script, and Godot script.",
            "Exports tone-mapped LDR .png and cubemap textures for lightweight web preview."
        ]
        self.desc_label.setText(descriptions[idx])

    @property
    def preset_key(self) -> str:
        keys = ["blender", "unity", "unreal", "godot", "all_engines", "web"]
        return keys[self.preset_combo.currentIndex()]

    @property
    def output_dir(self) -> str:
        return self.dir_edit.text()

    @property
    def base_name(self) -> str:
        return self.name_edit.text().strip() or "hdri_environment"

