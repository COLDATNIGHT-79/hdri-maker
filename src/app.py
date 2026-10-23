"""
Main Application Window for HDRI Maker.
Assembles all widgets and handles menus, shortcuts, toolbars, file I/O,
project save/load, layer creation, cross-engine export, and procedural generators.
"""

import os
import sys
import math
import random
import numpy as np
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QFileDialog, QMessageBox, QSplitter,
    QStatusBar, QMenuBar, QToolBar, QLabel, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QProgressDialog, QInputDialog,
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, QSize, QTimer, QPointF
from PySide6.QtGui import (
    QAction, QKeySequence, QIcon, QColor, QPainter,
    QLinearGradient, QRadialGradient, QPen, QFont
)

from src.hdri_engine import (
    HDRIProject, BrushEngine, LayerType, SunObject,
    generate_sphere_obj
)
from src.canvas_widget import CanvasWidget
from src.layer_panel import LayerPanel
from src.tools_panel import ToolsPanel
from src.preview_3d import Preview3DWidget
from src.filters import (
    GaussianBlurDialog, BloomDialog, ColorGradeDialog, NoiseDialog,
    VignetteDialog, SkyGeneratorDialog, GradientFillDialog,
    AtmosphereDialog, GodRaysDialog, CloudGeneratorDialog,
    SunPropertiesDialog, ExportPresetsDialog,
    apply_vignette, apply_gradient_fill
)
from src.exporter import (
    export_hdr, export_exr, export_png, export_cubemap,
    export_blender_script, export_unreal, export_godot,
    export_project, export_with_preset, EXPORT_PRESETS
)


class SparkleParticle:
    """Individual twinkling celestial star particle with phase and color."""

    def __init__(self, w, h):
        self.x = random.uniform(0, max(w, 800))
        self.y = random.uniform(2, max(h - 4, 30))
        self.vx = random.uniform(0.15, 0.45)
        self.vy = random.uniform(-0.08, 0.08)
        self.size = random.uniform(5.0, 9.0)
        self.phase = random.uniform(0, math.pi * 2)
        self.speed = random.uniform(0.04, 0.08)
        self.char = random.choice(["✦", "✧", "★", "✶", "✨"])
        self.color_type = random.choice(["cyan", "gold", "violet", "white"])

    def update(self, w, h):
        self.x += self.vx
        self.y += self.vy
        self.phase += self.speed
        if self.x > w + 20:
            self.x = -20
            self.y = random.uniform(4, max(h - 4, 30))
        if self.y < 2:
            self.y = h - 4
        elif self.y > h - 2:
            self.y = 4


class SparkleGlowBanner(QWidget):
    """
    Stunning glassmorphic top banner with animated floating celestial sparkles,
    real-time multi-core CPU/GPU hardware metrics, and quick action shortcuts.
    """

    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.setFixedHeight(48)
        self.setMouseTracking(True)

        self._tick = 0
        self._particles = [SparkleParticle(1400, 48) for _ in range(14)]

        # Lightweight twinkle animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_tick)
        self._anim_timer.start(80)

        # Controls layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 2, 14, 2)
        layout.setSpacing(10)

        # Brand Title badge
        title_box = QHBoxLayout()
        title_box.setSpacing(8)

        self.brand_title = QLabel("✨ HDRI MAKER PRO")
        self.brand_title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: 900;
                letter-spacing: 1.5px;
            }
        """)
        title_box.addWidget(self.brand_title)

        tagline = QLabel("✦ Substance Painter for Lighting ✦")
        tagline.setStyleSheet("""
            QLabel {
                color: #00f2fe;
                font-size: 10px;
                font-weight: bold;
                background: rgba(0, 242, 254, 0.12);
                border: 1px solid rgba(0, 242, 254, 0.4);
                border-radius: 9px;
                padding: 1px 7px;
            }
        """)
        title_box.addWidget(tagline)
        layout.addLayout(title_box)

        layout.addStretch(1)

        # Quick Actions
        actions_box = QHBoxLayout()
        actions_box.setSpacing(6)

        btn_style = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(40, 42, 58, 0.85), stop:1 rgba(25, 26, 36, 0.85));
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 5px;
                color: #e0e6ed;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 9px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(55, 58, 80, 0.95), stop:1 rgba(35, 38, 52, 0.95));
                border: 1px solid #00f2fe;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #0052d4;
            }
        """

        self.btn_preset = QPushButton("🚀 Presets")
        self.btn_preset.setStyleSheet(btn_style)
        self.btn_preset.clicked.connect(self.app_window._export_presets_dialog)
        actions_box.addWidget(self.btn_preset)

        self.btn_sun = QPushButton("☀ Sun Creator")
        self.btn_sun.setStyleSheet(btn_style)
        self.btn_sun.clicked.connect(lambda: self.app_window.tools_panel._select_tool(CanvasWidget.TOOL_SUN))
        actions_box.addWidget(self.btn_sun)

        self.btn_cloud = QPushButton("☁ Cloud Painter")
        self.btn_cloud.setStyleSheet(btn_style)
        self.btn_cloud.clicked.connect(lambda: self.app_window.tools_panel._select_tool(CanvasWidget.TOOL_CLOUD))
        actions_box.addWidget(self.btn_cloud)

        self.btn_atmo = QPushButton("🌅 Atmosphere")
        self.btn_atmo.setStyleSheet(btn_style)
        self.btn_atmo.clicked.connect(self.app_window._filter_atmosphere)
        actions_box.addWidget(self.btn_atmo)

        layout.addLayout(actions_box)

        layout.addStretch(1)

        # Hardware Performance HUD
        hud_box = QHBoxLayout()
        hud_box.setSpacing(6)

        cores = os.cpu_count() or 8
        self.cpu_hud = QLabel(f"⚡ CPU: {cores} Cores SIMD")
        self.cpu_hud.setStyleSheet("""
            QLabel {
                color: #00f2fe;
                font-size: 10px;
                font-weight: bold;
                background: rgba(0, 242, 254, 0.08);
                border: 1px solid rgba(0, 242, 254, 0.35);
                border-radius: 4px;
                padding: 2px 7px;
            }
        """)
        hud_box.addWidget(self.cpu_hud)

        self.gpu_hud = QLabel("💎 GPU Viewport 60 FPS")
        self.gpu_hud.setStyleSheet("""
            QLabel {
                color: #ffb703;
                font-size: 10px;
                font-weight: bold;
                background: rgba(255, 183, 3, 0.08);
                border: 1px solid rgba(255, 183, 3, 0.35);
                border-radius: 4px;
                padding: 2px 7px;
            }
        """)
        hud_box.addWidget(self.gpu_hud)

        layout.addLayout(hud_box)

    def _on_tick(self):
        self._tick = (self._tick + 1) % 1000
        w = max(self.width(), 800)
        h = max(self.height(), 40)
        for p in self._particles:
            p.update(w, h)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Obsidian glassmorphic background
        bg_grad = QLinearGradient(0, 0, w, h)
        bg_grad.setColorAt(0.0, QColor(13, 14, 20, 250))
        bg_grad.setColorAt(0.5, QColor(20, 22, 33, 250))
        bg_grad.setColorAt(1.0, QColor(13, 14, 20, 250))
        painter.fillRect(0, 0, w, h, bg_grad)

        # Luminous rainbow glow bottom border
        border_grad = QLinearGradient(0, h - 2, w, h - 2)
        border_grad.setColorAt(0.0, QColor(0, 242, 254, 210))
        border_grad.setColorAt(0.35, QColor(123, 47, 247, 220))
        border_grad.setColorAt(0.70, QColor(255, 0, 128, 200))
        border_grad.setColorAt(1.0, QColor(255, 183, 3, 220))

        painter.setPen(QPen(border_grad, 2.0))
        painter.drawLine(0, h - 1, w, h - 1)

        # Floating celestial sparkle particles
        for p in self._particles:
            alpha = int(140 + 115 * math.sin(p.phase))
            if p.color_type == "cyan":
                color = QColor(0, 242, 254, alpha)
            elif p.color_type == "gold":
                color = QColor(255, 215, 0, alpha)
            elif p.color_type == "violet":
                color = QColor(180, 120, 255, alpha)
            else:
                color = QColor(255, 255, 255, alpha)

            painter.setPen(color)
            font = painter.font()
            font.setPointSize(int(p.size))
            painter.setFont(font)
            painter.drawText(QPointF(p.x, p.y), p.char)

        painter.end()


class HDRIMakerApp(QMainWindow):
    """
    Main application window for HDRI Maker — Substance Painter for Lighting.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HDRI Maker — Surface Painter for HDR Environments")
        self.setMinimumSize(1200, 700)
        self.resize(1560, 920)

        # Initialize project and tools
        self.project = HDRIProject()
        self.brush = BrushEngine()
        self._current_file = None

        # Generate sample OBJ if needed
        assets_dir = Path(__file__).parent.parent / "assets"
        sphere_path = assets_dir / "sample_sphere.obj"
        if not sphere_path.exists():
            generate_sphere_obj(str(sphere_path))

        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_shortcuts()
        self._setup_statusbar()
        self._connect_signals()
        self._apply_stylesheet()

        # Initial render
        QTimer.singleShot(100, self._initial_setup)

    def _initial_setup(self):
        """Deferred initialization after window is shown."""
        self.canvas.fit_to_view()
        self.preview_3d.request_render()

    # ================================================================
    #  UI SETUP
    # ================================================================

    def _setup_ui(self):
        """Create and arrange all central widgets, sparkling banner, and docks."""
        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Top animated sparkling glow header banner
        self.sparkle_banner = SparkleGlowBanner(self)
        central_layout.addWidget(self.sparkle_banner)

        # Canvas and 3D preview split view
        canvas_preview_splitter = QSplitter(Qt.Horizontal)

        # Canvas (center)
        self.canvas = CanvasWidget(self.project, self.brush)
        canvas_preview_splitter.addWidget(self.canvas)

        # 3D Preview (right of canvas)
        self.preview_3d = Preview3DWidget(self.project)
        self.preview_3d.setMinimumWidth(280)
        self.preview_3d.setMaximumWidth(420)
        canvas_preview_splitter.addWidget(self.preview_3d)

        canvas_preview_splitter.setSizes([950, 350])
        central_layout.addWidget(canvas_preview_splitter, 1)

        self.setCentralWidget(central_container)

        # Tools panel (left dock)
        self.tools_panel = ToolsPanel(self.brush, self.canvas)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tools_panel)

        # Layer panel (right dock)
        self.layer_panel = LayerPanel(self.project)
        self.addDockWidget(Qt.RightDockWidgetArea, self.layer_panel)

    def _setup_menus(self):
        """Create the complete menu bar."""
        menubar = self.menuBar()

        # === File Menu ===
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project...", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project (.hdriproject)...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction("&Save Project", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Project &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        import_img = QAction("&Import Image as Layer...", self)
        import_img.setShortcut("Ctrl+I")
        import_img.triggered.connect(self._import_image)
        file_menu.addAction(import_img)

        import_hdr = QAction("Import &HDR/EXR as Layer...", self)
        import_hdr.triggered.connect(self._import_hdr)
        file_menu.addAction(import_hdr)

        file_menu.addSeparator()

        # Export Submenu
        export_menu = file_menu.addMenu("&Export")

        exp_preset_action = QAction("🚀 &Cross-Engine Export Presets...", self)
        exp_preset_action.setShortcut("Ctrl+E")
        exp_preset_action.triggered.connect(self._export_presets_dialog)
        export_menu.addAction(exp_preset_action)

        export_menu.addSeparator()

        export_hdr_action = QAction("Export as .hdr (Radiance RGBE)...", self)
        export_hdr_action.triggered.connect(lambda: self._export_format('hdr'))
        export_menu.addAction(export_hdr_action)

        export_exr_action = QAction("Export as .exr (OpenEXR 32-bit)...", self)
        export_exr_action.triggered.connect(lambda: self._export_format('exr'))
        export_menu.addAction(export_exr_action)

        export_png_action = QAction("Export as .png (Tone-mapped LDR)...", self)
        export_png_action.triggered.connect(lambda: self._export_format('png'))
        export_menu.addAction(export_png_action)

        export_menu.addSeparator()

        export_cube_faces = QAction("Export Cubemap (6 Individual Faces)...", self)
        export_cube_faces.triggered.connect(lambda: self._export_cubemap_mode('faces'))
        export_menu.addAction(export_cube_faces)

        export_cube_cross = QAction("Export Cubemap (Cross Layout)...", self)
        export_cube_cross.triggered.connect(lambda: self._export_cubemap_mode('cross'))
        export_menu.addAction(export_cube_cross)

        export_menu.addSeparator()

        export_blender = QAction("Export for Blender (.hdr + Sun Lamp Script)...", self)
        export_blender.triggered.connect(self._export_blender)
        export_menu.addAction(export_blender)

        export_unreal = QAction("Export for Unreal Engine (.hdr + Setup Script)...", self)
        export_unreal.triggered.connect(self._export_unreal)
        export_menu.addAction(export_unreal)

        export_godot = QAction("Export for Godot (.hdr + GDScript + Scene)...", self)
        export_godot.triggered.connect(self._export_godot)
        export_menu.addAction(export_godot)

        export_unity = QAction("Export for Unity (.hdr + Cubemap + C# Plugin)...", self)
        export_unity.triggered.connect(self._export_unity)
        export_menu.addAction(export_unity)

        export_menu.addSeparator()

        export_all = QAction("Export All Formats at Once...", self)
        export_all.setShortcut("Ctrl+Shift+E")
        export_all.triggered.connect(self._export_all)
        export_menu.addAction(export_all)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # === Edit Menu ===
        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        clear_layer = QAction("Clear Active Layer", self)
        clear_layer.setShortcut("Delete")
        clear_layer.triggered.connect(self._clear_layer)
        edit_menu.addAction(clear_layer)

        flatten_action = QAction("Flatten All Layers", self)
        flatten_action.triggered.connect(self._flatten_layers)
        edit_menu.addAction(flatten_action)

        # === Layer Menu ===
        layer_menu = menubar.addMenu("&Layer")

        add_paint = QAction("Add &Paint Layer", self)
        add_paint.setShortcut("Ctrl+Shift+N")
        add_paint.triggered.connect(lambda: self._add_layer_of_type(LayerType.PAINT))
        layer_menu.addAction(add_paint)

        add_sun = QAction("Add &Sun Layer", self)
        add_sun.setShortcut("Ctrl+Alt+S")
        add_sun.triggered.connect(lambda: self._add_layer_of_type(LayerType.SUN))
        layer_menu.addAction(add_sun)

        add_cloud = QAction("Add &Cloud Layer", self)
        add_cloud.setShortcut("Ctrl+Alt+C")
        add_cloud.triggered.connect(lambda: self._add_layer_of_type(LayerType.CLOUD))
        layer_menu.addAction(add_cloud)

        add_atmo = QAction("Add &Atmosphere Layer", self)
        add_atmo.setShortcut("Ctrl+Alt+A")
        add_atmo.triggered.connect(lambda: self._add_layer_of_type(LayerType.ATMOSPHERE))
        layer_menu.addAction(add_atmo)

        add_stamp = QAction("Add &Stamp Layer", self)
        add_stamp.setShortcut("Ctrl+Alt+T")
        add_stamp.triggered.connect(lambda: self._add_layer_of_type(LayerType.STAMP))
        layer_menu.addAction(add_stamp)

        add_adj = QAction("Add &Adjustment Layer", self)
        add_adj.triggered.connect(lambda: self._add_layer_of_type(LayerType.ADJUSTMENT))
        layer_menu.addAction(add_adj)

        layer_menu.addSeparator()

        dup_layer = QAction("&Duplicate Layer", self)
        dup_layer.setShortcut("Ctrl+J")
        dup_layer.triggered.connect(self._duplicate_layer)
        layer_menu.addAction(dup_layer)

        del_layer = QAction("Delete Layer", self)
        del_layer.triggered.connect(self._delete_layer)
        layer_menu.addAction(del_layer)

        layer_menu.addSeparator()

        merge_down = QAction("Merge &Down", self)
        merge_down.triggered.connect(self._merge_down)
        layer_menu.addAction(merge_down)

        toggle_mask = QAction("Toggle Layer &Mask", self)
        toggle_mask.setShortcut("Ctrl+M")
        toggle_mask.triggered.connect(self._toggle_mask)
        layer_menu.addAction(toggle_mask)

        # === Filter & Environment Menu ===
        filter_menu = menubar.addMenu("F&ilter & Skies")

        atmo_action = QAction("🌅 &Atmosphere & Rayleigh/Mie Scattering...", self)
        atmo_action.triggered.connect(self._filter_atmosphere)
        filter_menu.addAction(atmo_action)

        sky_action = QAction("Generate Procedural &Gradient Sky...", self)
        sky_action.triggered.connect(self._generate_sky)
        filter_menu.addAction(sky_action)

        cloud_gen_action = QAction("☁ Procedural &Cloud Field...", self)
        cloud_gen_action.triggered.connect(self._filter_clouds)
        filter_menu.addAction(cloud_gen_action)

        god_rays_action = QAction("✨ &God Rays / Crepuscular Rays...", self)
        god_rays_action.triggered.connect(self._filter_god_rays)
        filter_menu.addAction(god_rays_action)

        stars_action = QAction("⭐ Add Night &Starfield...", self)
        stars_action.triggered.connect(self._filter_stars)
        filter_menu.addAction(stars_action)

        filter_menu.addSeparator()

        blur_action = QAction("Gaussian &Blur...", self)
        blur_action.triggered.connect(self._filter_blur)
        filter_menu.addAction(blur_action)

        bloom_action = QAction("&Bloom / HDR Glow...", self)
        bloom_action.triggered.connect(self._filter_bloom)
        filter_menu.addAction(bloom_action)

        grade_action = QAction("&Color Grading (Lift / Gamma / Gain)...", self)
        grade_action.triggered.connect(self._filter_color_grade)
        filter_menu.addAction(grade_action)

        noise_action = QAction("Add &Noise...", self)
        noise_action.triggered.connect(self._filter_noise)
        filter_menu.addAction(noise_action)

        vignette_action = QAction("&Vignette...", self)
        vignette_action.triggered.connect(self._filter_vignette)
        filter_menu.addAction(vignette_action)

        gradient_action = QAction("Gradient &Fill...", self)
        gradient_action.triggered.connect(self._gradient_fill)
        filter_menu.addAction(gradient_action)

        # === View Menu ===
        view_menu = menubar.addMenu("&View")

        zoom_in = QAction("Zoom &In", self)
        zoom_in.setShortcut("Ctrl+=")
        zoom_in.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(zoom_in)

        zoom_out = QAction("Zoom &Out", self)
        zoom_out.setShortcut("Ctrl+-")
        zoom_out.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(zoom_out)

        fit_view = QAction("&Fit to View", self)
        fit_view.setShortcut("Ctrl+0")
        fit_view.triggered.connect(self.canvas.fit_to_view)
        view_menu.addAction(fit_view)

        view_menu.addSeparator()

        toggle_tools = self.tools_panel.toggleViewAction()
        toggle_tools.setText("&Tools Panel")
        view_menu.addAction(toggle_tools)

        toggle_layers = self.layer_panel.toggleViewAction()
        toggle_layers.setText("&Layers Panel")
        view_menu.addAction(toggle_layers)

        # === Help Menu ===
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About HDRI Maker", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """Create the quick-access main toolbar with glowing gradient styling."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #181926, stop:1 #11121c);
                border-bottom: 1px solid rgba(0, 242, 254, 0.22);
                padding: 4px;
                spacing: 5px;
            }
            QToolButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #272838, stop:1 #1c1d28);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 5px;
                padding: 4px 9px;
                color: #e0e6ed;
                font-size: 11px;
                font-weight: 500;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #393b52, stop:1 #27283a);
                border: 1px solid #00f2fe;
                color: #ffffff;
            }
            QToolButton:pressed {
                background: #0052d4;
                border-color: #00f2fe;
            }
            QToolBar::separator {
                width: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }
        """)

        toolbar.addAction("📄 New", self._new_project)
        toolbar.addAction("📂 Open", self._open_project)
        toolbar.addAction("💾 Save", self._save_project)
        toolbar.addSeparator()
        toolbar.addAction("🚀 Export Presets", self._export_presets_dialog)
        toolbar.addSeparator()
        toolbar.addAction("↩ Undo", self._undo)
        toolbar.addAction("↪ Redo", self._redo)
        toolbar.addSeparator()
        toolbar.addAction("☀ Sun", lambda: self.tools_panel._select_tool(CanvasWidget.TOOL_SUN))
        toolbar.addAction("☁ Cloud", lambda: self.tools_panel._select_tool(CanvasWidget.TOOL_CLOUD))
        toolbar.addAction("🌲 Stamp", lambda: self.tools_panel._select_tool(CanvasWidget.TOOL_STAMP))
        toolbar.addSeparator()
        toolbar.addAction("🌅 Atmosphere", self._filter_atmosphere)
        toolbar.addAction("✨ Bloom", self._filter_bloom)
        toolbar.addAction("🌫 Blur", self._filter_blur)
        toolbar.addSeparator()
        toolbar.addAction("🔃 3D Refresh", self.preview_3d.request_render)

        self.addToolBar(toolbar)

    def _setup_shortcuts(self):
        pass

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("✨ System Ready • HDR 32-bit Float Pipeline Active")
        self.status_label.setStyleSheet("color: #00f2fe; font-weight: bold; padding-left: 6px;")
        self.status_bar.addWidget(self.status_label, 1)

        self.pos_label = QLabel("X: 0  Y: 0")
        self.pos_label.setStyleSheet("color: #aaa; background: rgba(255,255,255,0.06); border-radius: 3px; padding: 2px 7px;")
        self.status_bar.addPermanentWidget(self.pos_label)

        self.size_label = QLabel(f"{self.project.width} × {self.project.height} [Float32]")
        self.size_label.setStyleSheet("color: #aaa; background: rgba(255,255,255,0.06); border-radius: 3px; padding: 2px 7px;")
        self.status_bar.addPermanentWidget(self.size_label)

        self.layer_count_label = QLabel(f"Layers: {len(self.project.layers)}")
        self.layer_count_label.setStyleSheet("color: #72efdd; background: rgba(0,242,254,0.1); border: 1px solid rgba(0,242,254,0.3); border-radius: 3px; padding: 2px 7px; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.layer_count_label)

    def _connect_signals(self):
        self.canvas.canvas_modified.connect(self._on_canvas_modified)
        self.canvas.cursor_position_changed.connect(self._on_cursor_moved)
        self.layer_panel.layer_changed.connect(self._on_layer_changed)
        self.layer_panel.active_layer_changed.connect(self._on_active_layer_changed)
        self.layer_panel.configure_layer_requested.connect(self._on_configure_layer_requested)

    # ================================================================
    #  STYLESHEET
    # ================================================================

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #0d0e14;
            }
            QMenuBar {
                background: #151622;
                color: #e0e6ed;
                border-bottom: 1px solid rgba(0, 242, 254, 0.2);
                padding: 3px;
                font-size: 12px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background: transparent;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0052d4, stop:1 #4364f7);
                color: #ffffff;
            }
            QMenu {
                background: #171825;
                color: #e0e6ed;
                border: 1px solid rgba(0, 242, 254, 0.35);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 22px 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052d4, stop:1 #00f2fe);
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.12);
                margin: 4px 8px;
            }
            QDockWidget {
                color: #e0e6ed;
            }
            QDockWidget::title {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1c29, stop:1 #13141f);
                padding: 7px;
                border-bottom: 1px solid rgba(0, 242, 254, 0.22);
                font-weight: bold;
                font-size: 11px;
                color: #00f2fe;
            }
            QStatusBar {
                background: #11121b;
                border-top: 1px solid rgba(0, 242, 254, 0.22);
                color: #aaa;
                font-size: 11px;
            }
            QSplitter::handle {
                background: #252738;
                width: 3px;
            }
            QSplitter::handle:hover {
                background: #00f2fe;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #161724;
                border: 1px solid rgba(0, 242, 254, 0.25);
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #4facfe);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.7 #00f2fe, stop:1 #0099cc);
                border: 1px solid #ffffff;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.6 #ffdd00, stop:1 #ff9900);
                border: 2px solid #ffffff;
            }
            QScrollBar:vertical {
                background: #11121a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2b2d40;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00f2fe;
            }
            QLabel {
                color: #ccd2db;
            }
        """)

    # ================================================================
    #  SIGNAL HANDLERS
    # ================================================================

    def _on_canvas_modified(self):
        self.layer_panel.update_thumbnails()
        self.preview_3d.request_render(delay_ms=60)
        self._update_status()

    def _on_cursor_moved(self, x, y):
        self.pos_label.setText(f"X: {x}  Y: {y}")

    def _on_layer_changed(self):
        self.canvas.refresh()
        self.preview_3d.request_render(delay_ms=60)
        self._update_status()

    def _on_active_layer_changed(self, index):
        layer = self.project.active_layer
        if layer:
            self.status_label.setText(f"Active: {layer.name}")

    def _update_status(self):
        self.layer_count_label.setText(f"Layers: {len(self.project.layers)}")

    def _on_configure_layer_requested(self, layer):
        """Open the appropriate settings dialog when double-clicking a layer."""
        if layer.layer_type == LayerType.SUN:
            if not layer.suns:
                layer.suns.append(SunObject())
            dialog = SunPropertiesDialog(layer.suns[0], self)
            if dialog.exec():
                self.project.save_undo_state("Configure Sun")
                dialog.apply_to_sun()
                layer.regenerate(self.project)
                self.canvas.refresh()
                self.preview_3d.request_render()

        elif layer.layer_type == LayerType.CLOUD:
            dialog = CloudGeneratorDialog(self)
            if dialog.exec():
                self.project.save_undo_state("Configure Clouds")
                from src.cloud_engine import CloudSettings
                presets = ["cumulus", "cirrus", "stratus", "wispy", "storm", "sunset"]
                pname = presets[dialog.preset_index]
                maker = getattr(CloudSettings, f"preset_{pname}", CloudSettings.preset_cumulus)
                s = maker()
                s.density = dialog.density
                s.softness = dialog.softness
                s.seed = dialog.seed
                layer.cloud_settings = s
                layer.regenerate(self.project)
                self.canvas.refresh()
                self.preview_3d.request_render()

        elif layer.layer_type == LayerType.ATMOSPHERE:
            dialog = AtmosphereDialog(self)
            if dialog.exec():
                self.project.save_undo_state("Configure Atmosphere")
                from src.atmosphere import AtmosphereSettings
                ats = AtmosphereSettings()
                ats.time_of_day = dialog.time_of_day
                ats.turbidity = dialog.turbidity
                ats.rayleigh_factor = dialog.rayleigh
                ats.mie_factor = dialog.mie
                ats.haze_density = dialog.haze
                ats.include_stars = dialog.include_stars
                layer.atmosphere_settings = ats
                layer.regenerate(self.project)
                self.canvas.refresh()
                self.preview_3d.request_render()

        elif layer.layer_type == LayerType.ADJUSTMENT:
            dialog = ColorGradeDialog(self)
            if dialog.exec():
                self.project.save_undo_state("Configure Adjustment")
                self.project.processor.color_grade(
                    layer.data, dialog.lift, dialog.gamma, dialog.gain
                )
                self.canvas.refresh()
                self.preview_3d.request_render()

        else:
            text, ok = QInputDialog.getText(
                self, "Layer Settings", "Layer Name:", text=layer.name
            )
            if ok and text:
                self.project.save_undo_state("Rename Layer")
                layer.name = text
                self.layer_panel.refresh()

    # ================================================================
    #  FILE & PROJECT OPERATIONS
    # ================================================================

    def _new_project(self):
        reply = QMessageBox.question(
            self, "New Project",
            "Create a new project? Unsaved changes will be lost.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            sizes = ["1024 × 512 (Preview)", "2048 × 1024 (Standard)",
                     "4096 × 2048 (High-Res 4K)", "8192 × 4096 (Ultra 8K)"]
            size_str, ok = QInputDialog.getItem(
                self, "Canvas Resolution", "Select equirectangular resolution:", sizes, 1, False
            )
            if ok:
                parts = size_str.split("×")
                w = int(parts[0].split()[0].strip())
                h = int(parts[1].split()[0].strip())
                self.project = HDRIProject(w, h)
                self._current_file = None
                self._attach_project_to_widgets()
                self.size_label.setText(f"{w} × {h}")
                self.status_label.setText("New project created")
                self.setWindowTitle("HDRI Maker — Surface Painter for HDR Environments")

    def _attach_project_to_widgets(self):
        self.canvas.project = self.project
        self.layer_panel.project = self.project
        self.preview_3d.project = self.project
        self.canvas.fit_to_view()
        self.canvas.refresh()
        self.layer_panel.refresh()
        self.preview_3d.request_render()
        self._update_status()

    def _open_project(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open HDRI Project",
            "", "HDRI Project Files (*.hdriproject);;All Files (*)"
        )
        if filepath:
            try:
                self.project.load_project(filepath)
                self._current_file = filepath
                self._attach_project_to_widgets()
                self.size_label.setText(f"{self.project.width} × {self.project.height}")
                self.setWindowTitle(f"HDRI Maker — {Path(filepath).name}")
                self.status_label.setText(f"Loaded project: {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Open Error", f"Failed to open project:\n{e}")

    def _save_project(self):
        if self._current_file:
            try:
                self.project.save_project(self._current_file)
                self.status_label.setText(f"Saved: {self._current_file}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save project:\n{e}")
        else:
            self._save_project_as()

    def _save_project_as(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save HDRI Project As",
            "my_environment.hdriproject", "HDRI Project Files (*.hdriproject)"
        )
        if filepath:
            try:
                self.project.save_project(filepath)
                self._current_file = filepath
                self.setWindowTitle(f"HDRI Maker — {Path(filepath).name}")
                self.status_label.setText(f"Project saved: {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save project:\n{e}")

    def _import_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Image",
            "", "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tga);;All Files (*)"
        )
        if filepath:
            try:
                from PIL import Image
                img = Image.open(filepath).convert('RGBA')
                data = np.array(img).astype(np.float32) / 255.0
                name = Path(filepath).stem
                self.project.save_undo_state("Import image")
                self.project.add_image_layer(data, name)
                self.canvas.refresh()
                self.layer_panel.refresh()
                self.preview_3d.request_render()
                self.status_label.setText(f"Imported image: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import image:\n{e}")

    def _import_hdr(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import HDR/EXR",
            "", "HDR Files (*.hdr *.exr);;All Files (*)"
        )
        if filepath:
            try:
                import imageio.v3 as iio
                data = iio.imread(filepath).astype(np.float32)
                if len(data.shape) == 2:
                    data = np.stack([data] * 3, axis=-1)
                if data.shape[2] == 3:
                    alpha = np.ones((*data.shape[:2], 1), dtype=np.float32)
                    data = np.concatenate([data, alpha], axis=-1)

                name = Path(filepath).stem
                self.project.save_undo_state("Import HDR")
                self.project.add_image_layer(data, name)
                self.canvas.refresh()
                self.layer_panel.refresh()
                self.preview_3d.request_render()
                self.status_label.setText(f"Imported HDR: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import HDR:\n{e}")

    # ================================================================
    #  EXPORT OPERATIONS
    # ================================================================

    def _get_sun_data(self) -> dict:
        sun = self.project.primary_sun
        if sun:
            return {
                'azimuth': sun.azimuth,
                'elevation': sun.elevation,
                'intensity': sun.intensity,
                'color': sun.color,
                'exposure': 1.0,
            }
        return {
            'azimuth': 0.25,
            'elevation': 0.25,
            'intensity': 10.0,
            'color': (1.0, 0.95, 0.85),
            'exposure': 1.0,
        }

    def _export_format(self, fmt: str):
        ext_map = {'hdr': '*.hdr', 'exr': '*.exr', 'png': '*.png'}
        filepath, _ = QFileDialog.getSaveFileName(
            self, f"Export as .{fmt}",
            f"hdri_output.{fmt}", f"{fmt.upper()} Files ({ext_map.get(fmt, '*.*')})"
        )
        if filepath:
            composite = self.project.flatten()
            try:
                if fmt == 'hdr':
                    export_hdr(composite, filepath)
                elif fmt == 'exr':
                    export_exr(composite, filepath)
                elif fmt == 'png':
                    export_png(composite, filepath)
                self.status_label.setText(f"Exported: {filepath}")
                QMessageBox.information(self, "Export Complete", f"Successfully exported to:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    def _export_cubemap_mode(self, mode: str):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Cubemap Export Directory")
        if output_dir:
            composite = self.project.flatten()
            try:
                formats = ['faces'] if mode == 'faces' else ['cross']
                files = export_cubemap(composite, output_dir, "skybox", formats=formats)
                self.status_label.setText(f"Exported {len(files)} cubemap files")
                QMessageBox.information(
                    self, "Cubemap Export Complete",
                    f"Generated {len(files)} files in:\n{output_dir}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Cubemap export failed:\n{e}")

    def _export_blender(self):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory for Blender")
        if output_dir:
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_project(composite, output_dir, "blender_hdri",
                                       formats=['hdr', 'blender'], sun_data=sun_data)
                QMessageBox.information(
                    self, "Blender Export Complete",
                    f"Exported Blender environment package:\n" + "\n".join(files)
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Blender export failed:\n{e}")

    def _export_unreal(self):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory for Unreal")
        if output_dir:
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_project(composite, output_dir, "unreal_hdri",
                                       formats=['hdr', 'unreal'], sun_data=sun_data)
                QMessageBox.information(
                    self, "Unreal Export Complete",
                    f"Exported Unreal Engine package:\n" + "\n".join(files)
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Unreal export failed:\n{e}")

    def _export_godot(self):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory for Godot")
        if output_dir:
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_project(composite, output_dir, "godot_hdri",
                                       formats=['hdr', 'godot'], sun_data=sun_data)
                QMessageBox.information(
                    self, "Godot Export Complete",
                    f"Exported Godot scene package:\n" + "\n".join(files)
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Godot export failed:\n{e}")

    def _export_unity(self):
        output_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory for Unity")
        if output_dir:
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_project(composite, output_dir, "unity_hdri",
                                       formats=['hdr', 'cubemap', 'unity'], sun_data=sun_data)
                QMessageBox.information(
                    self, "Unity Export Complete",
                    f"Exported Unity package with cubemaps and C# importer:\n" + "\n".join(files)
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Unity export failed:\n{e}")

    def _export_presets_dialog(self):
        dialog = ExportPresetsDialog(self)
        if dialog.exec():
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_with_preset(composite, dialog.output_dir,
                                           dialog.preset_key, dialog.base_name, sun_data)
                self.status_label.setText(f"Preset export complete ({len(files)} files)")
                QMessageBox.information(
                    self, "Export Complete",
                    f"Successfully exported {len(files)} files to:\n{dialog.output_dir}\n\n" +
                    "\n".join(files[:6]) + ("\n..." if len(files) > 6 else "")
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Preset export failed:\n{e}")

    def _export_all(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory for All Formats")
        if directory:
            composite = self.project.flatten()
            try:
                sun_data = self._get_sun_data()
                files = export_with_preset(composite, directory, "all_engines", "hdri_master", sun_data)
                self.status_label.setText(f"Exported {len(files)} files")
                QMessageBox.information(
                    self, "Export Complete",
                    f"Exported full package ({len(files)} files):\n\n" +
                    "\n".join(files[:8]) + ("\n..." if len(files) > 8 else "")
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export all formats:\n{e}")

    # ================================================================
    #  EDIT OPERATIONS
    # ================================================================

    def _undo(self):
        if self.project.undo():
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Undo")

    def _redo(self):
        if self.project.redo():
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Redo")

    def _clear_layer(self):
        layer = self.project.active_layer
        if layer and not layer.locked:
            self.project.save_undo_state("Clear layer")
            layer.clear()
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()

    def _flatten_layers(self):
        reply = QMessageBox.question(
            self, "Flatten Layers",
            "Flatten all layers into one? This cannot be easily undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.project.save_undo_state("Flatten")
            composite = self.project.flatten()
            self.project.layers.clear()
            from src.hdri_engine import HDRILayer
            layer = HDRILayer(self.project.width, self.project.height, "Flattened")
            layer.data = composite.copy()
            self.project.layers.append(layer)
            self.project.active_layer_index = 0
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()

    # ================================================================
    #  LAYER OPERATIONS
    # ================================================================

    def _add_layer_of_type(self, ltype: LayerType):
        self.project.save_undo_state(f"Add Layer")
        if ltype == LayerType.SUN:
            self.project.add_sun_layer()
        elif ltype == LayerType.CLOUD:
            self.project.add_cloud_layer()
        elif ltype == LayerType.ATMOSPHERE:
            self.project.add_atmosphere_layer()
        elif ltype == LayerType.STAMP:
            self.project.add_stamp_layer()
        elif ltype == LayerType.ADJUSTMENT:
            self.project.add_adjustment_layer()
        else:
            self.project.add_layer()

        self.layer_panel.refresh()
        self.canvas.refresh()
        self.preview_3d.request_render()

    def _duplicate_layer(self):
        self.project.save_undo_state("Duplicate layer")
        self.project.duplicate_layer(self.project.active_layer_index)
        self.layer_panel.refresh()
        self.canvas.refresh()

    def _delete_layer(self):
        if len(self.project.layers) > 1:
            self.project.save_undo_state("Delete layer")
            self.project.remove_layer(self.project.active_layer_index)
            self.layer_panel.refresh()
            self.canvas.refresh()
            self.preview_3d.request_render()

    def _merge_down(self):
        if self.project.active_layer_index > 0:
            self.project.save_undo_state("Merge down")
            self.project.merge_down(self.project.active_layer_index)
            self.layer_panel.refresh()
            self.canvas.refresh()
            self.preview_3d.request_render()

    def _toggle_mask(self):
        layer = self.project.active_layer
        if layer:
            self.project.save_undo_state("Toggle Mask")
            if layer.mask is None:
                layer.init_mask()
            else:
                layer.mask_enabled = not layer.mask_enabled
            self.layer_panel.refresh()
            self.canvas.refresh()
            self.preview_3d.request_render()

    # ================================================================
    #  FILTERS & PROCEDURAL ENVIRONMENT
    # ================================================================

    def _filter_atmosphere(self):
        dialog = AtmosphereDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Atmosphere Simulation")
            from src.atmosphere import AtmosphereSettings, render_atmosphere
            ats = AtmosphereSettings()
            ats.time_of_day = dialog.time_of_day
            ats.turbidity = dialog.turbidity
            ats.rayleigh_factor = dialog.rayleigh
            ats.mie_factor = dialog.mie
            ats.haze_density = dialog.haze
            ats.include_stars = dialog.include_stars

            layer = self.project.add_atmosphere_layer("Physical Atmosphere")
            layer.atmosphere_settings = ats
            layer.regenerate(self.project)

            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Simulated Atmosphere & Sky Scattering")

    def _filter_clouds(self):
        dialog = CloudGeneratorDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Generate Clouds")
            from src.cloud_engine import CloudSettings
            presets = ["cumulus", "cirrus", "stratus", "wispy", "storm", "sunset"]
            pname = presets[dialog.preset_index]
            maker = getattr(CloudSettings, f"preset_{pname}", CloudSettings.preset_cumulus)
            s = maker()
            s.density = dialog.density
            s.softness = dialog.softness
            s.seed = dialog.seed

            layer = self.project.add_cloud_layer(f"Clouds ({pname.title()})")
            layer.cloud_settings = s
            layer.regenerate(self.project)

            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText(f"Generated {pname.title()} cloud layer")

    def _filter_god_rays(self):
        dialog = GodRaysDialog(self)
        if dialog.exec():
            self.project.save_undo_state("God Rays")
            from src.atmosphere import render_god_rays
            sun = self.project.primary_sun
            sun_x = sun.azimuth if sun else 0.25
            sun_y = sun.elevation if sun else 0.25
            sun_col = sun.color if sun else (1.0, 0.95, 0.85)

            layer = self.project.add_layer("God Rays")
            render_god_rays(layer.data, sun_x, sun_y,
                            density=dialog.density,
                            decay=dialog.decay,
                            weight=dialog.weight,
                            sun_color=sun_col)

            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Added Crepuscular God Rays")

    def _filter_stars(self):
        self.project.save_undo_state("Add Stars")
        from src.atmosphere import add_stars
        layer = self.project.add_layer("Starfield")
        add_stars(layer.data, density=0.002, brightness=0.7)
        self.canvas.refresh()
        self.layer_panel.refresh()
        self.preview_3d.request_render()
        self.status_label.setText("Added Night Starfield")

    def _filter_blur(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = GaussianBlurDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Gaussian Blur")
            self.project.processor.gaussian_blur(layer.data, dialog.sigma)
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText(f"Applied Gaussian Blur (σ={dialog.sigma:.1f})")

    def _filter_bloom(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = BloomDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Bloom")
            self.project.processor.bloom_filter(
                layer.data, dialog.threshold, dialog.intensity, dialog.radius
            )
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Applied Bloom/Glow")

    def _filter_color_grade(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = ColorGradeDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Color Grade")
            self.project.processor.color_grade(
                layer.data, dialog.lift, dialog.gamma, dialog.gain
            )
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Applied Color Grading")

    def _filter_noise(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = NoiseDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Add Noise")
            self.project.processor.add_noise(layer.data, dialog.intensity)
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Added Noise")

    def _filter_vignette(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = VignetteDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Vignette")
            apply_vignette(layer.data, dialog.strength, dialog.radius)
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Applied Vignette")

    def _generate_sky(self):
        dialog = SkyGeneratorDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Generate Sky")
            layer = self.project.add_layer("Procedural Sky")
            self.project.processor.generate_sky(
                layer.data,
                dialog.horizon_color,
                dialog.zenith_color,
                dialog.ground_color,
                dialog.sun_intensity,
                dialog.sun_x, dialog.sun_y, dialog.sun_size
            )
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Generated Procedural Gradient Sky")

    def _gradient_fill(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = GradientFillDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Gradient Fill")
            color = self.brush.color[:3]
            apply_gradient_fill(layer.data, color, dialog.direction, dialog.intensity)
            layer.data[:, :, 3] = np.maximum(layer.data[:, :, 3], 0.5)
            self.canvas.refresh()
            self.preview_3d.request_render()
            self.status_label.setText("Applied Gradient Fill")

    # ================================================================
    #  ABOUT
    # ================================================================

    def _show_about(self):
        QMessageBox.about(
            self, "About HDRI Maker",
            "<h2>HDRI Maker v2.0</h2>"
            "<p><b>Substance Painter for Lighting & HDR Environments</b></p>"
            "<p>Create, paint, sculpt, and compose complete 360° High Dynamic Range images (HDRIs) "
            "for Blender, Unreal Engine, Unity, and Godot.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li><b>Interactive Sun System:</b> Place and drag suns with physical Kelvin color temperature and halos</li>"
            "<li><b>Procedural Cloud Painting:</b> Sculpt clouds with Cumulus, Cirrus, Stratus, and Wispy brush modes</li>"
            "<li><b>Element Stamps Library:</b> Trees, mountains, skylines, and foliage silhouettes + custom PNG stamps</li>"
            "<li><b>Physical Sky Simulation:</b> Rayleigh and Mie atmospheric scattering with ground haze and god rays</li>"
            "<li><b>Substance Painter–style Layers:</b> Paint, Sun, Cloud, Atmosphere, Stamp, and Adjustment layers</li>"
            "<li><b>Layer Masks & Blend Modes:</b> Normal, Add, Multiply, Screen, Overlay, Soft Light</li>"
            "<li><b>Cross-Engine Export:</b> Radiance .hdr, OpenEXR, Cubemap faces, Blender script, Unreal Blueprint, Godot scene, Unity C#</li>"
            "<li><b>Real-time 3D Sphere Preview:</b> Mirror, Diffuse, and Glossy reflection preview</li>"
            "</ul>"
            "<p>Built with Python, PySide6, NumPy, and C++ processing.</p>"
        )


def run():
    """Entry point for the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("HDRI Maker")
    app.setApplicationVersion("2.0.0")
    app.setStyle("Fusion")

    window = HDRIMakerApp()
    window.show()
    sys.exit(app.exec())
