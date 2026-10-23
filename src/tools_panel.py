"""
Tools Panel for HDRI Maker.
Provides tool selection, brush settings, HDR color picker with intensity slider,
sun placement controls, procedural cloud brush controls, and stamp asset library.
"""

import math
import numpy as np
from pathlib import Path

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QGroupBox, QFormLayout, QColorDialog,
    QFrame, QSizePolicy, QDoubleSpinBox, QSpinBox, QToolButton,
    QStackedWidget, QComboBox, QCheckBox, QScrollArea, QFileDialog,
    QListWidget, QListWidgetItem, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon, QLinearGradient, QImage

from src.hdri_engine import BrushEngine, LayerType, SunObject
from src.canvas_widget import CanvasWidget
from src.atmosphere import kelvin_to_rgb
from src.cloud_engine import CloudSettings
from src.stamp_library import StampLibrary, StampAsset, StampInstance


class ColorPreviewWidget(QWidget):
    """Widget showing the current HDR color with intensity."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = (1.0, 1.0, 1.0)
        self.intensity = 1.0
        self.setFixedSize(54, 54)
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, r, g, b, intensity=1.0):
        self.color = (r, g, b)
        self.intensity = intensity
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Clamped display color
        r = min(self.color[0] * self.intensity, 1.0)
        g = min(self.color[1] * self.intensity, 1.0)
        b = min(self.color[2] * self.intensity, 1.0)

        painter.setPen(QColor(100, 100, 100))
        painter.setBrush(QColor(int(r * 255), int(g * 255), int(b * 255)))
        painter.drawRoundedRect(2, 2, 50, 50, 6, 6)

        # Inner base color
        painter.setBrush(QColor(
            int(min(self.color[0], 1.0) * 255),
            int(min(self.color[1], 1.0) * 255),
            int(min(self.color[2], 1.0) * 255)
        ))
        painter.drawRoundedRect(14, 14, 26, 26, 4, 4)

        if self.intensity > 1.0:
            painter.setPen(QColor(255, 215, 0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(1, 1, 52, 52, 6, 6)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class ToolsPanel(QDockWidget):
    """
    Comprehensive tool selection and properties dock panel:
    - Paint tools: Brush, Eraser, Fill, Eyedropper
    - Procedural tools: Sun, Clouds, Stamps
    - Contextual properties pages for each tool
    - View controls (Exposure, Fit, Grid)
    """

    tool_changed = Signal(int)
    color_changed = Signal(float, float, float, float)

    def __init__(self, brush: BrushEngine, canvas: CanvasWidget, parent=None):
        super().__init__("Tools & Elements", parent)
        self.brush = brush
        self.canvas = canvas
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)

        # Scroll area for compact height
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self.main_layout = QVBoxLayout(container)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(10)

        # Setup sections
        self._setup_tool_selector()
        self._setup_stacked_settings()
        self._setup_view_controls()

        self.main_layout.addStretch()
        scroll.setWidget(container)
        self.setWidget(scroll)

        # Connect canvas signals
        self.canvas.sun_moved.connect(self._on_canvas_sun_moved)
        self.canvas.stamp_placed.connect(self._on_canvas_stamp_placed)

        # Select brush initially
        self._select_tool(CanvasWidget.TOOL_BRUSH)

    # ================================================================
    #  TOOL SELECTOR
    # ================================================================

    def _setup_tool_selector(self):
        tools_group = QGroupBox("Tools & Elements")
        tools_group.setStyleSheet(self._group_style())
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(4, 8, 4, 4)

        self._tool_buttons = {}
        tool_defs = [
            (CanvasWidget.TOOL_BRUSH, "🖌", "Brush (B)", 0, 0),
            (CanvasWidget.TOOL_ERASER, "🧹", "Eraser (E)", 0, 1),
            (CanvasWidget.TOOL_FILL, "🪣", "Fill (G)", 0, 2),
            (CanvasWidget.TOOL_EYEDROPPER, "💧", "Eyedropper (I)", 0, 3),
            (CanvasWidget.TOOL_SUN, "☀", "Sun Creator (S)", 1, 0),
            (CanvasWidget.TOOL_CLOUD, "☁", "Cloud Painter (C)", 1, 1),
            (CanvasWidget.TOOL_STAMP, "🌲", "Stamps / Silhouettes (T)", 1, 2),
        ]

        for tid, icon, tip, r, c in tool_defs:
            btn = QPushButton(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(38, 36)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: #333; border: 1px solid #555;
                    border-radius: 5px; font-size: 16px; color: #ddd;
                }
                QPushButton:checked {
                    background: #4682B4; border-color: #72a9e0;
                }
                QPushButton:hover {
                    background: #444; border-color: #888;
                }
            """)
            btn.clicked.connect(lambda checked, t=tid: self._select_tool(t))
            grid.addWidget(btn, r, c)
            self._tool_buttons[tid] = btn

        tools_group.setLayout(grid)
        self.main_layout.addWidget(tools_group)

    # ================================================================
    #  SETTINGS STACK
    # ================================================================

    def _setup_stacked_settings(self):
        self.stack = QStackedWidget()

        # Page 0: Brush / Eraser / Fill settings
        self.page_brush = self._create_brush_settings_page()
        self.stack.addWidget(self.page_brush)

        # Page 1: Sun Creator settings
        self.page_sun = self._create_sun_settings_page()
        self.stack.addWidget(self.page_sun)

        # Page 2: Cloud Painter settings
        self.page_cloud = self._create_cloud_settings_page()
        self.stack.addWidget(self.page_cloud)

        # Page 3: Stamp Library settings
        self.page_stamp = self._create_stamp_settings_page()
        self.stack.addWidget(self.page_stamp)

        self.main_layout.addWidget(self.stack)

    # ----------------------------------------------------------------
    # Page 0: Brush Settings
    # ----------------------------------------------------------------

    def _create_brush_settings_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Brush properties group
        bgroup = QGroupBox("Brush Properties")
        bgroup.setStyleSheet(self._group_style())
        flayout = QFormLayout()
        flayout.setSpacing(6)

        # Size
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 250)
        self.size_slider.setValue(self.brush.size)
        self.size_label = QLabel(str(self.brush.size))
        self.size_label.setFixedWidth(30)
        self.size_label.setStyleSheet("color: #ddd;")
        s_row = QHBoxLayout()
        s_row.addWidget(self.size_slider)
        s_row.addWidget(self.size_label)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        flayout.addRow("Size:", s_row)

        # Hardness
        self.hardness_slider = QSlider(Qt.Horizontal)
        self.hardness_slider.setRange(0, 100)
        self.hardness_slider.setValue(int(self.brush.hardness * 100))
        self.hardness_label = QLabel(f"{int(self.brush.hardness * 100)}%")
        self.hardness_label.setFixedWidth(30)
        self.hardness_label.setStyleSheet("color: #ddd;")
        h_row = QHBoxLayout()
        h_row.addWidget(self.hardness_slider)
        h_row.addWidget(self.hardness_label)
        self.hardness_slider.valueChanged.connect(self._on_hardness_changed)
        flayout.addRow("Hardness:", h_row)

        # Opacity
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(int(self.brush.opacity * 100))
        self.opacity_label = QLabel(f"{int(self.brush.opacity * 100)}%")
        self.opacity_label.setFixedWidth(30)
        self.opacity_label.setStyleSheet("color: #ddd;")
        o_row = QHBoxLayout()
        o_row.addWidget(self.opacity_slider)
        o_row.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        flayout.addRow("Opacity:", o_row)

        bgroup.setLayout(flayout)
        layout.addWidget(bgroup)

        # HDR Color Picker group
        cgroup = QGroupBox("HDR Light Color")
        cgroup.setStyleSheet(self._group_style())
        clayout = QVBoxLayout()
        clayout.setSpacing(6)

        preview_row = QHBoxLayout()
        self.color_preview = ColorPreviewWidget()
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)
        self.color_preview.clicked.connect(self._pick_color)
        preview_row.addWidget(self.color_preview)

        # Quick palette
        pal_vbox = QVBoxLayout()
        pal_vbox.setSpacing(2)
        row1 = QHBoxLayout()
        row1.setSpacing(2)
        for c, name in [((1, 1, 1), "White"), ((0, 0, 0), "Black"),
                        ((1, 0, 0), "Red"), ((0, 1, 0), "Green"), ((0, 0, 1), "Blue")]:
            b = self._make_palette_btn(c, name)
            row1.addWidget(b)
        row2 = QHBoxLayout()
        row2.setSpacing(2)
        for c, name in [((1.0, 0.9, 0.7), "Warm White"), ((1.0, 0.6, 0.2), "Sunset Orange"),
                        ((0.5, 0.8, 1.0), "Sky Blue"), ((0.2, 0.15, 0.3), "Purple Dusk"),
                        ((0.8, 0.7, 0.5), "Sand")]:
            b = self._make_palette_btn(c, name)
            row2.addWidget(b)
        pal_vbox.addLayout(row1)
        pal_vbox.addLayout(row2)
        preview_row.addLayout(pal_vbox)
        clayout.addLayout(preview_row)

        # Intensity slider
        i_row = QHBoxLayout()
        i_lbl = QLabel("Intensity:")
        i_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        self.intensity_slider = QSlider(Qt.Horizontal)
        self.intensity_slider.setRange(1, 500)
        self.intensity_slider.setValue(int(self.brush.intensity * 10))
        self.intensity_val = QLabel(f"{self.brush.intensity:.1f}")
        self.intensity_val.setFixedWidth(35)
        self.intensity_val.setStyleSheet("color: #ddd; font-size: 11px;")
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        i_row.addWidget(i_lbl)
        i_row.addWidget(self.intensity_slider)
        i_row.addWidget(self.intensity_val)
        clayout.addLayout(i_row)

        tip = QLabel("💡 Intensity > 1.0 creates glowing, light-emitting HDRI areas.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        clayout.addWidget(tip)

        cgroup.setLayout(clayout)
        layout.addWidget(cgroup)

        return widget

    def _make_palette_btn(self, color, name) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(20, 20)
        btn.setToolTip(name)
        r, g, b = int(color[0]*255), int(color[1]*255), int(color[2]*255)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: rgb({r},{g},{b});
                border: 1px solid #666; border-radius: 3px;
            }}
            QPushButton:hover {{ border-color: white; }}
        """)
        btn.clicked.connect(lambda _, c=color: self._set_quick_color(c))
        return btn

    # ----------------------------------------------------------------
    # Page 1: Sun Creator Settings
    # ----------------------------------------------------------------

    def _create_sun_settings_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        sgroup = QGroupBox("Sun Parameters")
        sgroup.setStyleSheet(self._group_style())
        flayout = QFormLayout()
        flayout.setSpacing(6)

        # Position info
        self.sun_pos_lbl = QLabel("Azimuth: 90° | Elevation: 45°")
        self.sun_pos_lbl.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 11px;")
        flayout.addRow("Position:", self.sun_pos_lbl)

        # Temperature Kelvin
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(1800, 12000)
        self.temp_slider.setValue(5500)
        self.temp_lbl = QLabel("5500K")
        self.temp_lbl.setFixedWidth(45)
        self.temp_lbl.setStyleSheet("color: #ddd;")
        self.temp_preview = QLabel()
        self.temp_preview.setFixedSize(18, 18)
        self._update_temp_swatch(5500)

        t_row = QHBoxLayout()
        t_row.addWidget(self.temp_slider)
        t_row.addWidget(self.temp_lbl)
        t_row.addWidget(self.temp_preview)
        self.temp_slider.valueChanged.connect(self._on_sun_temp_changed)
        flayout.addRow("Kelvin:", t_row)

        # Sun Intensity
        self.sun_int_slider = QSlider(Qt.Horizontal)
        self.sun_int_slider.setRange(1, 200)
        self.sun_int_slider.setValue(20)  # 10.0
        self.sun_int_lbl = QLabel("10.0")
        self.sun_int_lbl.setFixedWidth(40)
        self.sun_int_lbl.setStyleSheet("color: #ddd;")
        si_row = QHBoxLayout()
        si_row.addWidget(self.sun_int_slider)
        si_row.addWidget(self.sun_int_lbl)
        self.sun_int_slider.valueChanged.connect(self._on_sun_int_changed)
        flayout.addRow("Intensity:", si_row)

        # Disc size
        self.disc_slider = QSlider(Qt.Horizontal)
        self.disc_slider.setRange(2, 60)
        self.disc_slider.setValue(15)
        self.disc_lbl = QLabel("0.020")
        self.disc_lbl.setFixedWidth(40)
        self.disc_lbl.setStyleSheet("color: #ddd;")
        d_row = QHBoxLayout()
        d_row.addWidget(self.disc_slider)
        d_row.addWidget(self.disc_lbl)
        self.disc_slider.valueChanged.connect(self._on_sun_disc_changed)
        flayout.addRow("Disc Size:", d_row)

        # Halo radius & intensity
        self.halo_r_slider = QSlider(Qt.Horizontal)
        self.halo_r_slider.setRange(10, 200)
        self.halo_r_slider.setValue(80)
        self.halo_r_lbl = QLabel("0.08")
        self.halo_r_lbl.setFixedWidth(40)
        self.halo_r_lbl.setStyleSheet("color: #ddd;")
        hr_row = QHBoxLayout()
        hr_row.addWidget(self.halo_r_slider)
        hr_row.addWidget(self.halo_r_lbl)
        self.halo_r_slider.valueChanged.connect(self._on_sun_halo_r_changed)
        flayout.addRow("Halo Radius:", hr_row)

        self.halo_i_slider = QSlider(Qt.Horizontal)
        self.halo_i_slider.setRange(0, 100)
        self.halo_i_slider.setValue(50)
        self.halo_i_lbl = QLabel("0.50")
        self.halo_i_lbl.setFixedWidth(40)
        self.halo_i_lbl.setStyleSheet("color: #ddd;")
        hi_row = QHBoxLayout()
        hi_row.addWidget(self.halo_i_slider)
        hi_row.addWidget(self.halo_i_lbl)
        self.halo_i_slider.valueChanged.connect(self._on_sun_halo_i_changed)
        flayout.addRow("Halo Bright:", hi_row)

        # Starburst Flare
        self.flare_check = QCheckBox("Starburst Flare Rays")
        self.flare_check.setChecked(False)
        self.flare_check.toggled.connect(self._on_sun_flare_toggled)
        flayout.addRow("", self.flare_check)

        sgroup.setLayout(flayout)
        layout.addWidget(sgroup)

        # Sun actions
        actions_group = QGroupBox("Sun Actions")
        actions_group.setStyleSheet(self._group_style())
        act_layout = QVBoxLayout()
        act_layout.setSpacing(4)

        btn_add_sun = QPushButton("➕ Add New Sun Layer")
        btn_add_sun.setStyleSheet(self._action_btn_style())
        btn_add_sun.clicked.connect(self._add_sun_layer)
        act_layout.addWidget(btn_add_sun)

        hint = QLabel("Click and drag on the canvas to place or move the sun.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        act_layout.addWidget(hint)

        actions_group.setLayout(act_layout)
        layout.addWidget(actions_group)

        return widget

    def _update_temp_swatch(self, kelvin: int):
        r, g, b = kelvin_to_rgb(kelvin)
        ir, ig, ib = int(r * 255), int(g * 255), int(b * 255)
        self.temp_preview.setStyleSheet(
            f"background: rgb({ir},{ig},{ib}); border: 1px solid #777; border-radius: 3px;"
        )

    # ----------------------------------------------------------------
    # Page 2: Cloud Painter Settings
    # ----------------------------------------------------------------

    def _create_cloud_settings_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        cgroup = QGroupBox("Cloud Properties")
        cgroup.setStyleSheet(self._group_style())
        flayout = QFormLayout()
        flayout.setSpacing(6)

        # Preset
        self.cloud_preset_combo = QComboBox()
        self.cloud_preset_combo.addItems([
            "Cumulus (Fluffy)", "Cirrus (Wispy/High)",
            "Stratus (Flat/Overcast)", "Wispy (Ethereal)",
            "Storm (Dark/Moody)", "Sunset (Golden Rim)"
        ])
        self.cloud_preset_combo.currentIndexChanged.connect(self._on_cloud_preset_changed)
        flayout.addRow("Preset:", self.cloud_preset_combo)

        # Brush size
        self.cloud_size_slider = QSlider(Qt.Horizontal)
        self.cloud_size_slider.setRange(10, 300)
        self.cloud_size_slider.setValue(self.brush.size)
        self.cloud_size_lbl = QLabel(str(self.brush.size))
        self.cloud_size_lbl.setFixedWidth(30)
        self.cloud_size_lbl.setStyleSheet("color: #ddd;")
        cs_row = QHBoxLayout()
        cs_row.addWidget(self.cloud_size_slider)
        cs_row.addWidget(self.cloud_size_lbl)
        self.cloud_size_slider.valueChanged.connect(self._on_cloud_size_changed)
        flayout.addRow("Brush Size:", cs_row)

        # Cloud Density
        self.cloud_density_slider = QSlider(Qt.Horizontal)
        self.cloud_density_slider.setRange(10, 200)
        self.cloud_density_slider.setValue(100)
        self.cloud_density_lbl = QLabel("1.0")
        self.cloud_density_lbl.setFixedWidth(30)
        self.cloud_density_lbl.setStyleSheet("color: #ddd;")
        cd_row = QHBoxLayout()
        cd_row.addWidget(self.cloud_density_slider)
        cd_row.addWidget(self.cloud_density_lbl)
        self.cloud_density_slider.valueChanged.connect(self._on_cloud_density_changed)
        flayout.addRow("Density:", cd_row)

        # Cloud Softness
        self.cloud_soft_slider = QSlider(Qt.Horizontal)
        self.cloud_soft_slider.setRange(0, 100)
        self.cloud_soft_slider.setValue(40)
        self.cloud_soft_lbl = QLabel("0.4")
        self.cloud_soft_lbl.setFixedWidth(30)
        self.cloud_soft_lbl.setStyleSheet("color: #ddd;")
        cso_row = QHBoxLayout()
        cso_row.addWidget(self.cloud_soft_slider)
        cso_row.addWidget(self.cloud_soft_lbl)
        self.cloud_soft_slider.valueChanged.connect(self._on_cloud_soft_changed)
        flayout.addRow("Softness:", cso_row)

        # Cloud Opacity
        self.cloud_op_slider = QSlider(Qt.Horizontal)
        self.cloud_op_slider.setRange(5, 100)
        self.cloud_op_slider.setValue(80)
        self.cloud_op_lbl = QLabel("80%")
        self.cloud_op_lbl.setFixedWidth(30)
        self.cloud_op_lbl.setStyleSheet("color: #ddd;")
        co_row = QHBoxLayout()
        co_row.addWidget(self.cloud_op_slider)
        co_row.addWidget(self.cloud_op_lbl)
        self.cloud_op_slider.valueChanged.connect(self._on_cloud_opacity_changed)
        flayout.addRow("Brush Opacity:", co_row)

        # Sun-lit toggle
        self.cloud_sunlit_check = QCheckBox("Auto-illuminate by Sun")
        self.cloud_sunlit_check.setChecked(True)
        self.cloud_sunlit_check.toggled.connect(self._on_cloud_sunlit_toggled)
        flayout.addRow("", self.cloud_sunlit_check)

        cgroup.setLayout(flayout)
        layout.addWidget(cgroup)

        # Cloud Actions
        act_group = QGroupBox("Cloud Actions")
        act_group.setStyleSheet(self._group_style())
        act_layout = QVBoxLayout()
        act_layout.setSpacing(4)

        btn_full_sky = QPushButton("☁ Generate Full Sky Cloud Layer")
        btn_full_sky.setStyleSheet(self._action_btn_style())
        btn_full_sky.clicked.connect(self._generate_full_cloud_layer)
        act_layout.addWidget(btn_full_sky)

        hint = QLabel("Paint with the cloud brush directly on the canvas to sculpt fluffy or wispy clouds.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        act_layout.addWidget(hint)

        act_group.setLayout(act_layout)
        layout.addWidget(act_group)

        return widget

    # ----------------------------------------------------------------
    # Page 3: Stamp Library Settings
    # ----------------------------------------------------------------

    def _create_stamp_settings_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Category & stamp picker
        sgroup = QGroupBox("Element Stamps")
        sgroup.setStyleSheet(self._group_style())
        slayout = QVBoxLayout()
        slayout.setSpacing(6)

        cat_row = QHBoxLayout()
        cat_lbl = QLabel("Category:")
        cat_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        self.stamp_cat_combo = QComboBox()
        self.stamp_cat_combo.addItems([
            "Trees", "Mountains", "Buildings", "Foliage",
            "Power Lines", "Birds", "Nature", "Custom"
        ])
        self.stamp_cat_combo.currentIndexChanged.connect(self._on_stamp_cat_changed)
        cat_row.addWidget(cat_lbl)
        cat_row.addWidget(self.stamp_cat_combo)
        slayout.addLayout(cat_row)

        # Stamp list/grid
        self.stamp_list = QListWidget()
        self.stamp_list.setIconSize(QSize(48, 48))
        self.stamp_list.setFixedHeight(120)
        self.stamp_list.setStyleSheet("""
            QListWidget {
                background: #252528; border: 1px solid #444; border-radius: 4px;
            }
            QListWidget::item {
                padding: 4px; border-bottom: 1px solid #333; color: #ddd;
            }
            QListWidget::item:selected {
                background: rgba(70, 130, 220, 0.4);
            }
        """)
        self.stamp_list.currentRowChanged.connect(self._on_stamp_selected)
        slayout.addWidget(self.stamp_list)

        sgroup.setLayout(slayout)
        layout.addWidget(sgroup)

        # Transform & color properties
        tgroup = QGroupBox("Placement & Appearance")
        tgroup.setStyleSheet(self._group_style())
        flayout = QFormLayout()
        flayout.setSpacing(6)

        # Scale
        self.stamp_scale_slider = QSlider(Qt.Horizontal)
        self.stamp_scale_slider.setRange(20, 400)
        self.stamp_scale_slider.setValue(100)
        self.stamp_scale_lbl = QLabel("1.0x")
        self.stamp_scale_lbl.setFixedWidth(35)
        self.stamp_scale_lbl.setStyleSheet("color: #ddd;")
        sc_row = QHBoxLayout()
        sc_row.addWidget(self.stamp_scale_slider)
        sc_row.addWidget(self.stamp_scale_lbl)
        self.stamp_scale_slider.valueChanged.connect(self._on_stamp_scale_changed)
        flayout.addRow("Scale:", sc_row)

        # Rotation
        self.stamp_rot_slider = QSlider(Qt.Horizontal)
        self.stamp_rot_slider.setRange(-180, 180)
        self.stamp_rot_slider.setValue(0)
        self.stamp_rot_lbl = QLabel("0°")
        self.stamp_rot_lbl.setFixedWidth(35)
        self.stamp_rot_lbl.setStyleSheet("color: #ddd;")
        rot_row = QHBoxLayout()
        rot_row.addWidget(self.stamp_rot_slider)
        rot_row.addWidget(self.stamp_rot_lbl)
        self.stamp_rot_slider.valueChanged.connect(self._on_stamp_rot_changed)
        flayout.addRow("Rotation:", rot_row)

        # Flip Horizontal
        self.stamp_flip_check = QCheckBox("Flip Horizontally")
        self.stamp_flip_check.toggled.connect(self._on_stamp_flip_toggled)
        flayout.addRow("", self.stamp_flip_check)

        # Silhouette Mode & Color
        self.stamp_sil_check = QCheckBox("Silhouette Mode")
        self.stamp_sil_check.setChecked(True)
        self.stamp_sil_check.toggled.connect(self._on_stamp_sil_toggled)
        flayout.addRow("", self.stamp_sil_check)

        sil_color_row = QHBoxLayout()
        self.stamp_col_btn = QPushButton()
        self.stamp_col_btn.setFixedSize(24, 24)
        self.stamp_col_btn.setStyleSheet("background: #000; border: 1px solid #666; border-radius: 3px;")
        self.stamp_col_btn.clicked.connect(self._pick_stamp_color)
        sil_color_row.addWidget(self.stamp_col_btn)
        sil_color_row.addWidget(QLabel("Silhouette Color"))
        flayout.addRow("Color:", sil_color_row)

        tgroup.setLayout(flayout)
        layout.addWidget(tgroup)

        # Import button
        btn_import = QPushButton("📥 Import Custom Stamp (PNG)...")
        btn_import.setStyleSheet(self._action_btn_style())
        btn_import.clicked.connect(self._import_custom_stamp)
        layout.addWidget(btn_import)

        hint = QLabel("Select an element above, then click anywhere on the canvas or horizon line to place it.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        layout.addWidget(hint)

        # Populate initial stamps
        self._populate_stamps("Trees")

        return widget

    # ================================================================
    #  VIEW CONTROLS
    # ================================================================

    def _setup_view_controls(self):
        view_group = QGroupBox("View Controls")
        view_group.setStyleSheet(self._group_style())
        vlayout = QFormLayout()
        vlayout.setSpacing(6)

        # Exposure slider
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(-50, 50)
        self.exposure_slider.setValue(0)
        self.exposure_label = QLabel("0.0")
        self.exposure_label.setFixedWidth(35)
        self.exposure_label.setStyleSheet("color: #ddd;")
        exp_row = QHBoxLayout()
        exp_row.addWidget(self.exposure_slider)
        exp_row.addWidget(self.exposure_label)
        self.exposure_slider.valueChanged.connect(self._on_exposure_changed)
        vlayout.addRow("Exposure:", exp_row)

        # Fit & Grid buttons
        btn_row = QHBoxLayout()
        self.btn_fit = QPushButton("Fit View")
        self.btn_fit.clicked.connect(self.canvas.fit_to_view)
        self.btn_grid = QPushButton("Grid / Horizon")
        self.btn_grid.setCheckable(True)
        self.btn_grid.toggled.connect(self.canvas.set_show_grid)

        for btn in [self.btn_fit, self.btn_grid]:
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3a3a3a; border: 1px solid #555;
                    border-radius: 4px; color: #ddd; font-size: 11px;
                }
                QPushButton:hover { background: #4a4a4a; }
                QPushButton:checked { background: #4682B4; }
            """)
            btn_row.addWidget(btn)

        vlayout.addRow(btn_row)
        view_group.setLayout(vlayout)
        self.main_layout.addWidget(view_group)

    # ================================================================
    #  STYLES
    # ================================================================

    def _group_style(self):
        return """
            QGroupBox {
                color: #ccc; font-size: 11px; font-weight: bold;
                border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
                margin-top: 8px; padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px;
            }
        """

    def _action_btn_style(self):
        return """
            QPushButton {
                background: #383838; border: 1px solid #555;
                border-radius: 4px; color: #eee; padding: 6px; font-size: 11px;
            }
            QPushButton:hover {
                background: #4a4a4a; border-color: #4682B4;
            }
            QPushButton:pressed {
                background: #4682B4;
            }
        """

    # ================================================================
    #  SLOTS & HANDLERS
    # ================================================================

    def _select_tool(self, tool_id: int):
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)

        self.canvas.tool = tool_id

        # Switch settings stack page
        if tool_id in (CanvasWidget.TOOL_BRUSH, CanvasWidget.TOOL_ERASER,
                       CanvasWidget.TOOL_FILL, CanvasWidget.TOOL_EYEDROPPER):
            self.stack.setCurrentIndex(0)
        elif tool_id == CanvasWidget.TOOL_SUN:
            self.stack.setCurrentIndex(1)
            self._sync_sun_ui_from_project()
        elif tool_id == CanvasWidget.TOOL_CLOUD:
            self.stack.setCurrentIndex(2)
        elif tool_id == CanvasWidget.TOOL_STAMP:
            self.stack.setCurrentIndex(3)

        self.canvas.update()
        self.tool_changed.emit(tool_id)

    # Brush handlers
    def _on_size_changed(self, value):
        self.brush.size = value
        self.brush._stamp_cache.clear()
        self.size_label.setText(str(value))
        self.cloud_size_slider.blockSignals(True)
        self.cloud_size_slider.setValue(value)
        self.cloud_size_slider.blockSignals(False)
        self.cloud_size_lbl.setText(str(value))

    def _on_hardness_changed(self, value):
        self.brush.hardness = value / 100.0
        self.brush._stamp_cache.clear()
        self.hardness_label.setText(f"{value}%")

    def _on_opacity_changed(self, value):
        self.brush.opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")

    def _on_intensity_changed(self, value):
        self.brush.intensity = value / 10.0
        self.intensity_val.setText(f"{value / 10.0:.1f}")
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)

    def _on_exposure_changed(self, value):
        exp = value / 10.0
        self.exposure_label.setText(f"{exp:.1f}")
        self.canvas.set_exposure(exp)

    def _pick_color(self):
        c = QColor(
            int(min(self.brush.color[0], 1.0) * 255),
            int(min(self.brush.color[1], 1.0) * 255),
            int(min(self.brush.color[2], 1.0) * 255)
        )
        picked = QColorDialog.getColor(c, self, "Pick HDR Light Color")
        if picked.isValid():
            r, g, b = picked.redF(), picked.greenF(), picked.blueF()
            self.brush.color = (r, g, b, 1.0)
            self.color_preview.set_color(r, g, b, self.brush.intensity)
            self.color_changed.emit(r, g, b, self.brush.intensity)

    def _set_quick_color(self, color_tuple):
        r, g, b = color_tuple
        self.brush.color = (r, g, b, 1.0)
        self.color_preview.set_color(r, g, b, self.brush.intensity)
        self.color_changed.emit(r, g, b, self.brush.intensity)

    # Sun handlers
    def _sync_sun_ui_from_project(self):
        sun = self.canvas.project.primary_sun
        if not sun:
            return
        az_deg = int(sun.azimuth * 360)
        el_deg = int((0.5 - sun.elevation) * 180)
        self.sun_pos_lbl.setText(f"Azimuth: {az_deg}° | Elevation: {el_deg}°")

        self.temp_slider.blockSignals(True)
        self.temp_slider.setValue(int(sun.temperature))
        self.temp_lbl.setText(f"{int(sun.temperature)}K")
        self._update_temp_swatch(int(sun.temperature))
        self.temp_slider.blockSignals(False)

        self.sun_int_slider.blockSignals(True)
        self.sun_int_slider.setValue(int(sun.intensity * 2))
        self.sun_int_lbl.setText(f"{sun.intensity:.1f}")
        self.sun_int_slider.blockSignals(False)

    def _on_canvas_sun_moved(self, az: float, el: float):
        az_deg = int(az * 360)
        el_deg = int((0.5 - el) * 180)
        self.sun_pos_lbl.setText(f"Azimuth: {az_deg}° | Elevation: {el_deg}°")

    def _on_sun_temp_changed(self, value):
        self.temp_lbl.setText(f"{value}K")
        self._update_temp_swatch(value)
        sun = self.canvas.project.primary_sun
        if sun:
            sun.temperature = float(value)
            self._update_active_sun_layer()

    def _on_sun_int_changed(self, value):
        val = value / 2.0
        self.sun_int_lbl.setText(f"{val:.1f}")
        sun = self.canvas.project.primary_sun
        if sun:
            sun.intensity = val
            self._update_active_sun_layer()

    def _on_sun_disc_changed(self, value):
        rad = value / 1000.0 * 2.0
        self.disc_lbl.setText(f"{rad:.3f}")
        sun = self.canvas.project.primary_sun
        if sun:
            sun.disc_size = rad
            self._update_active_sun_layer()

    def _on_sun_halo_r_changed(self, value):
        val = value / 1000.0
        self.halo_r_lbl.setText(f"{val:.2f}")
        sun = self.canvas.project.primary_sun
        if sun:
            sun.halo_radius = val
            self._update_active_sun_layer()

    def _on_sun_halo_i_changed(self, value):
        val = value / 100.0
        self.halo_i_lbl.setText(f"{val:.2f}")
        sun = self.canvas.project.primary_sun
        if sun:
            sun.halo_intensity = val
            self._update_active_sun_layer()

    def _on_sun_flare_toggled(self, checked):
        sun = self.canvas.project.primary_sun
        if sun:
            sun.flare_enabled = checked
            self._update_active_sun_layer()

    def _update_active_sun_layer(self):
        layer = self.canvas.project.active_layer
        if layer and layer.layer_type == LayerType.SUN:
            layer.regenerate(self.canvas.project)
            self.canvas.project.invalidate_cache()
            self.canvas.refresh()
            self.canvas.canvas_modified.emit()

    def _add_sun_layer(self):
        self.canvas.project.save_undo_state("Add Sun Layer")
        self.canvas.project.add_sun_layer("Sun")
        self.canvas.refresh()
        self.canvas.canvas_modified.emit()
        self._sync_sun_ui_from_project()

    # Cloud handlers
    def _on_cloud_preset_changed(self, index):
        presets = ["cumulus", "cirrus", "stratus", "wispy", "storm", "sunset"]
        preset_name = presets[index]
        maker = getattr(CloudSettings, f"preset_{preset_name}", CloudSettings.preset_cumulus)
        self.canvas.cloud_settings = maker()

        # Update UI sliders to reflect preset
        self.cloud_density_slider.blockSignals(True)
        self.cloud_density_slider.setValue(int(self.canvas.cloud_settings.density * 100))
        self.cloud_density_lbl.setText(f"{self.canvas.cloud_settings.density:.1f}")
        self.cloud_density_slider.blockSignals(False)

        self.cloud_soft_slider.blockSignals(True)
        self.cloud_soft_slider.setValue(int(self.canvas.cloud_settings.softness * 100))
        self.cloud_soft_lbl.setText(f"{self.canvas.cloud_settings.softness:.1f}")
        self.cloud_soft_slider.blockSignals(False)

    def _on_cloud_size_changed(self, value):
        self.brush.size = value
        self.cloud_size_lbl.setText(str(value))
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(value)
        self.size_slider.blockSignals(False)
        self.size_label.setText(str(value))

    def _on_cloud_density_changed(self, value):
        val = value / 100.0
        self.cloud_density_lbl.setText(f"{val:.1f}")
        self.canvas.cloud_settings.density = val

    def _on_cloud_soft_changed(self, value):
        val = value / 100.0
        self.cloud_soft_lbl.setText(f"{val:.1f}")
        self.canvas.cloud_settings.softness = val

    def _on_cloud_opacity_changed(self, value):
        self.cloud_op_lbl.setText(f"{value}%")
        self.brush.opacity = value / 100.0

    def _on_cloud_sunlit_toggled(self, checked):
        pass  # Brush automatically samples sun position if checked

    def _generate_full_cloud_layer(self):
        self.canvas.project.save_undo_state("Generate Cloud Layer")
        layer = self.canvas.project.add_cloud_layer("Clouds")
        layer.cloud_settings = self.canvas.cloud_settings.copy()
        layer.regenerate(self.canvas.project)
        self.canvas.refresh()
        self.canvas.canvas_modified.emit()

    # Stamp handlers
    def _populate_stamps(self, category: str):
        self.stamp_list.clear()
        if not self.canvas.project.stamp_library:
            return

        stamps = self.canvas.project.stamp_library.get_by_category(category)
        for s in stamps:
            item = QListWidgetItem(s.name)
            thumb = s.get_thumbnail(48)
            h, w = thumb.shape[:2]
            img = QImage(thumb.tobytes(), w, h, w * 4, QImage.Format_RGBA8888)
            item.setIcon(QIcon(QPixmap.fromImage(img)))
            item.setData(Qt.UserRole, s.stamp_id)
            self.stamp_list.addItem(item)

        if self.stamp_list.count() > 0:
            self.stamp_list.setCurrentRow(0)

    def _on_stamp_cat_changed(self, index):
        cat = self.stamp_cat_combo.currentText()
        self._populate_stamps(cat)

    def _on_stamp_selected(self, row):
        if row < 0 or not self.canvas.project.stamp_library:
            return
        item = self.stamp_list.item(row)
        if item:
            sid = item.data(Qt.UserRole)
            asset = self.canvas.project.stamp_library.get_stamp(sid)
            self.canvas.selected_stamp = asset

    def _on_stamp_scale_changed(self, value):
        scale = value / 100.0
        self.stamp_scale_lbl.setText(f"{scale:.1f}x")
        self.canvas.stamp_scale = scale
        self.canvas.update()

    def _on_stamp_rot_changed(self, value):
        self.stamp_rot_lbl.setText(f"{value}°")
        self.canvas.stamp_rotation = float(value)
        self.canvas.update()

    def _on_stamp_flip_toggled(self, checked):
        self.canvas.stamp_flip_h = checked

    def _on_stamp_sil_toggled(self, checked):
        self.canvas.stamp_silhouette_mode = checked

    def _pick_stamp_color(self):
        c = QColorDialog.getColor(Qt.black, self, "Pick Silhouette Color")
        if c.isValid():
            r, g, b = c.redF(), c.greenF(), c.blueF()
            self.canvas.stamp_color = (r, g, b)
            self.stamp_col_btn.setStyleSheet(
                f"background: rgb({c.red()},{c.green()},{c.blue()}); border: 1px solid #777; border-radius: 3px;"
            )

    def _import_custom_stamp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Stamp Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path and self.canvas.project.stamp_library:
            asset = self.canvas.project.stamp_library.import_stamp(path, category="Custom")
            if asset:
                self.stamp_cat_combo.setCurrentText("Custom")
                self._populate_stamps("Custom")

    def _on_canvas_stamp_placed(self, x: float, y: float):
        pass

    def update_from_brush(self):
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)
        self.intensity_slider.blockSignals(True)
        self.intensity_slider.setValue(int(self.brush.intensity * 10))
        self.intensity_slider.blockSignals(False)
        self.intensity_val.setText(f"{self.brush.intensity:.1f}")
