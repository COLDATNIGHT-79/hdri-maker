"""
Filters module for HDRI Maker.
Provides dialog-based filter effects that can be applied to layers.
"""

import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDialogButtonBox, QGroupBox, QComboBox, QFormLayout,
    QCheckBox, QPushButton
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
