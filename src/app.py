"""
Main Application Window for HDRI Maker.
Assembles all widgets and handles menus, shortcuts, and file I/O.
"""

import os
import sys
import numpy as np
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QApplication, QFileDialog, QMessageBox, QSplitter,
    QStatusBar, QMenuBar, QToolBar, QLabel, QDockWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QProgressDialog, QInputDialog
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon, QColor

from src.hdri_engine import HDRIProject, BrushEngine, generate_sphere_obj
from src.canvas_widget import CanvasWidget
from src.layer_panel import LayerPanel
from src.tools_panel import ToolsPanel
from src.preview_3d import Preview3DWidget
from src.filters import (
    GaussianBlurDialog, BloomDialog, ColorGradeDialog, NoiseDialog,
    VignetteDialog, SkyGeneratorDialog, GradientFillDialog,
    apply_vignette, apply_gradient_fill
)
from src.exporter import export_hdr, export_exr, export_png, export_project, export_blender_script


class HDRIMakerApp(QMainWindow):
    """Main application window for HDRI Maker."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HDRI Maker — Surface Painter for HDR Environments")
        self.setMinimumSize(1200, 700)
        self.resize(1500, 900)

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
        """Deferred initialization."""
        self.canvas.fit_to_view()
        self.preview_3d.request_render()

    # ================================================================
    #  UI SETUP
    # ================================================================

    def _setup_ui(self):
        """Create and arrange all widgets."""
        # Central area with splitter
        central_splitter = QSplitter(Qt.Horizontal)

        # Canvas (center)
        self.canvas = CanvasWidget(self.project, self.brush)

        # 3D Preview (right of canvas)
        self.preview_3d = Preview3DWidget(self.project)
        self.preview_3d.setMaximumWidth(350)

        canvas_preview_splitter = QSplitter(Qt.Horizontal)
        canvas_preview_splitter.addWidget(self.canvas)
        canvas_preview_splitter.addWidget(self.preview_3d)
        canvas_preview_splitter.setSizes([800, 300])

        self.setCentralWidget(canvas_preview_splitter)

        # Tools panel (left dock)
        self.tools_panel = ToolsPanel(self.brush, self.canvas)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tools_panel)

        # Layer panel (right dock)
        self.layer_panel = LayerPanel(self.project)
        self.addDockWidget(Qt.RightDockWidgetArea, self.layer_panel)

    def _setup_menus(self):
        """Create the menu bar."""
        menubar = self.menuBar()

        # === File Menu ===
        file_menu = menubar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        file_menu.addSeparator()

        import_img = QAction("&Import Image as Layer", self)
        import_img.setShortcut("Ctrl+I")
        import_img.triggered.connect(self._import_image)
        file_menu.addAction(import_img)

        import_hdr = QAction("Import &HDR/EXR", self)
        import_hdr.triggered.connect(self._import_hdr)
        file_menu.addAction(import_hdr)

        file_menu.addSeparator()

        export_menu = file_menu.addMenu("&Export")

        export_hdr_action = QAction("Export as .hdr (Radiance)", self)
        export_hdr_action.triggered.connect(lambda: self._export_format('hdr'))
        export_menu.addAction(export_hdr_action)

        export_exr_action = QAction("Export as .exr (OpenEXR)", self)
        export_exr_action.triggered.connect(lambda: self._export_format('exr'))
        export_menu.addAction(export_exr_action)

        export_png_action = QAction("Export as .png (Tone-mapped)", self)
        export_png_action.triggered.connect(lambda: self._export_format('png'))
        export_menu.addAction(export_png_action)

        export_menu.addSeparator()

        export_all = QAction("Export All Formats", self)
        export_all.setShortcut("Ctrl+Shift+E")
        export_all.triggered.connect(self._export_all)
        export_menu.addAction(export_all)

        export_blender = QAction("Generate Blender Import Script", self)
        export_blender.triggered.connect(self._export_blender)
        export_menu.addAction(export_blender)

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

        clear_layer = QAction("Clear Layer", self)
        clear_layer.setShortcut("Delete")
        clear_layer.triggered.connect(self._clear_layer)
        edit_menu.addAction(clear_layer)

        flatten_action = QAction("Flatten All Layers", self)
        flatten_action.triggered.connect(self._flatten_layers)
        edit_menu.addAction(flatten_action)

        # === Layer Menu ===
        layer_menu = menubar.addMenu("&Layer")

        add_layer = QAction("Add &New Layer", self)
        add_layer.setShortcut("Ctrl+Shift+N")
        add_layer.triggered.connect(self._add_layer)
        layer_menu.addAction(add_layer)

        dup_layer = QAction("&Duplicate Layer", self)
        dup_layer.setShortcut("Ctrl+J")
        dup_layer.triggered.connect(self._duplicate_layer)
        layer_menu.addAction(dup_layer)

        del_layer = QAction("Delete Layer", self)
        del_layer.triggered.connect(self._delete_layer)
        layer_menu.addAction(del_layer)

        layer_menu.addSeparator()

        merge_down = QAction("Merge &Down", self)
        merge_down.setShortcut("Ctrl+E")
        merge_down.triggered.connect(self._merge_down)
        layer_menu.addAction(merge_down)

        # === Filter Menu ===
        filter_menu = menubar.addMenu("F&ilter")

        blur_action = QAction("Gaussian &Blur...", self)
        blur_action.triggered.connect(self._filter_blur)
        filter_menu.addAction(blur_action)

        bloom_action = QAction("Bloom / &Glow...", self)
        bloom_action.triggered.connect(self._filter_bloom)
        filter_menu.addAction(bloom_action)

        filter_menu.addSeparator()

        grade_action = QAction("&Color Grading...", self)
        grade_action.triggered.connect(self._filter_color_grade)
        filter_menu.addAction(grade_action)

        noise_action = QAction("Add &Noise...", self)
        noise_action.triggered.connect(self._filter_noise)
        filter_menu.addAction(noise_action)

        vignette_action = QAction("&Vignette...", self)
        vignette_action.triggered.connect(self._filter_vignette)
        filter_menu.addAction(vignette_action)

        filter_menu.addSeparator()

        sky_action = QAction("Generate Procedural &Sky...", self)
        sky_action.triggered.connect(self._generate_sky)
        filter_menu.addAction(sky_action)

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
        """Create the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: #2a2a2a;
                border-bottom: 1px solid #444;
                padding: 4px;
                spacing: 4px;
            }
            QToolButton {
                background: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #ddd;
                font-size: 12px;
            }
            QToolButton:hover {
                background: #4a4a4a;
                border-color: #777;
            }
            QToolButton:pressed {
                background: #555;
            }
        """)

        # Quick access buttons
        toolbar.addAction("📄 New", self._new_project)
        toolbar.addAction("📥 Import", self._import_image)
        toolbar.addAction("💾 Export", self._export_all)
        toolbar.addSeparator()
        toolbar.addAction("↩ Undo", self._undo)
        toolbar.addAction("↪ Redo", self._redo)
        toolbar.addSeparator()
        toolbar.addAction("🌅 Sky", self._generate_sky)
        toolbar.addAction("✨ Bloom", self._filter_bloom)
        toolbar.addAction("🌫 Blur", self._filter_blur)
        toolbar.addSeparator()
        toolbar.addAction("🔃 Refresh 3D", self.preview_3d.request_render)

        self.addToolBar(toolbar)

    def _setup_shortcuts(self):
        """Additional keyboard shortcuts."""
        pass  # Most shortcuts are set in menu actions

    def _setup_statusbar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #aaa;")
        self.status_bar.addWidget(self.status_label, 1)

        self.pos_label = QLabel("X: 0  Y: 0")
        self.pos_label.setStyleSheet("color: #888;")
        self.status_bar.addPermanentWidget(self.pos_label)

        self.size_label = QLabel(f"{self.project.width} × {self.project.height}")
        self.size_label.setStyleSheet("color: #888;")
        self.status_bar.addPermanentWidget(self.size_label)

        self.layer_count_label = QLabel(f"Layers: {len(self.project.layers)}")
        self.layer_count_label.setStyleSheet("color: #888;")
        self.status_bar.addPermanentWidget(self.layer_count_label)

    def _connect_signals(self):
        """Connect widget signals."""
        self.canvas.canvas_modified.connect(self._on_canvas_modified)
        self.canvas.cursor_position_changed.connect(self._on_cursor_moved)
        self.layer_panel.layer_changed.connect(self._on_layer_changed)
        self.layer_panel.active_layer_changed.connect(self._on_active_layer_changed)

    # ================================================================
    #  STYLESHEET
    # ================================================================

    def _apply_stylesheet(self):
        """Apply the dark theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background: #1e1e1e;
            }
            QMenuBar {
                background: #2a2a2a;
                color: #ddd;
                border-bottom: 1px solid #444;
                padding: 2px;
            }
            QMenuBar::item:selected {
                background: #4682B4;
                border-radius: 3px;
            }
            QMenu {
                background: #333;
                color: #ddd;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background: #4682B4;
            }
            QMenu::separator {
                height: 1px;
                background: #555;
                margin: 4px 8px;
            }
            QDockWidget {
                color: #ddd;
                titlebar-close-icon: none;
            }
            QDockWidget::title {
                background: #2a2a2a;
                padding: 6px;
                border-bottom: 1px solid #444;
                font-weight: bold;
            }
            QStatusBar {
                background: #2a2a2a;
                border-top: 1px solid #444;
                color: #aaa;
            }
            QSplitter::handle {
                background: #444;
                width: 2px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #444;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4682B4;
                border: 1px solid #5a9bd5;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #5a9bd5;
            }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 10px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #777;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                height: 0;
            }
            QLabel {
                color: #ccc;
            }
            QGroupBox {
                color: #ccc;
            }
        """)

    # ================================================================
    #  SIGNAL HANDLERS
    # ================================================================

    def _on_canvas_modified(self):
        """Called when the canvas content changes."""
        self.layer_panel.update_thumbnails()
        self.preview_3d.request_render()
        self._update_status()

    def _on_cursor_moved(self, x, y):
        self.pos_label.setText(f"X: {x}  Y: {y}")

    def _on_layer_changed(self):
        self.canvas.refresh()
        self._update_status()

    def _on_active_layer_changed(self, index):
        layer = self.project.active_layer
        if layer:
            self.status_label.setText(f"Active: {layer.name}")

    def _update_status(self):
        self.layer_count_label.setText(f"Layers: {len(self.project.layers)}")

    # ================================================================
    #  FILE OPERATIONS
    # ================================================================

    def _new_project(self):
        """Create a new empty project."""
        reply = QMessageBox.question(
            self, "New Project",
            "Create a new project? Unsaved changes will be lost.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            sizes = ["1024 × 512", "2048 × 1024", "4096 × 2048", "8192 × 4096"]
            size_str, ok = QInputDialog.getItem(
                self, "Canvas Size", "Select HDRI resolution:", sizes, 1, False
            )
            if ok:
                parts = size_str.split("×")
                w = int(parts[0].strip())
                h = int(parts[1].strip())
                self.project = HDRIProject(w, h)
                self.canvas.project = self.project
                self.layer_panel.project = self.project
                self.preview_3d.project = self.project
                self.canvas.fit_to_view()
                self.canvas.refresh()
                self.layer_panel.refresh()
                self.preview_3d.request_render()
                self.size_label.setText(f"{w} × {h}")
                self._update_status()
                self.status_label.setText("New project created")

    def _import_image(self):
        """Import an image file as a new layer."""
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
                self.status_label.setText(f"Imported: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import image:\n{e}")

    def _import_hdr(self):
        """Import an HDR/EXR file as a new layer."""
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

    def _export_format(self, fmt: str):
        """Export in a specific format."""
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
                QMessageBox.information(self, "Export Complete",
                                         f"Successfully exported to:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    def _export_all(self):
        """Export in all formats."""
        directory = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if directory:
            composite = self.project.flatten()
            try:
                files = export_project(composite, directory, "hdri_output",
                                        ['hdr', 'png', 'blender'])
                file_list = "\n".join(files)
                self.status_label.setText(f"Exported {len(files)} files")
                QMessageBox.information(
                    self, "Export Complete",
                    f"Exported {len(files)} files:\n\n{file_list}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")

    def _export_blender(self):
        """Generate a Blender import script."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Blender Script",
            "hdri_blender_import.py", "Python Files (*.py)"
        )
        if filepath:
            hdr_path = filepath.rsplit('.', 1)[0] + '.hdr'
            composite = self.project.flatten()
            export_hdr(composite, hdr_path)
            export_blender_script(hdr_path, filepath)
            self.status_label.setText(f"Exported Blender script: {filepath}")

    # ================================================================
    #  EDIT OPERATIONS
    # ================================================================

    def _undo(self):
        if self.project.undo():
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.status_label.setText("Undo")

    def _redo(self):
        if self.project.redo():
            self.canvas.refresh()
            self.layer_panel.refresh()
            self.status_label.setText("Redo")

    def _clear_layer(self):
        layer = self.project.active_layer
        if layer and not layer.locked:
            self.project.save_undo_state("Clear layer")
            layer.clear()
            self.canvas.refresh()
            self.layer_panel.refresh()

    def _flatten_layers(self):
        reply = QMessageBox.question(
            self, "Flatten Layers",
            "Flatten all layers into one? This cannot be undone easily.",
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

    # ================================================================
    #  LAYER OPERATIONS
    # ================================================================

    def _add_layer(self):
        self.project.save_undo_state("Add layer")
        self.project.add_layer()
        self.layer_panel.refresh()
        self.canvas.refresh()

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

    def _merge_down(self):
        if self.project.active_layer_index > 0:
            self.project.save_undo_state("Merge down")
            self.project.merge_down(self.project.active_layer_index)
            self.layer_panel.refresh()
            self.canvas.refresh()

    # ================================================================
    #  FILTERS
    # ================================================================

    def _filter_blur(self):
        layer = self.project.active_layer
        if not layer:
            return
        dialog = GaussianBlurDialog(self)
        if dialog.exec():
            self.project.save_undo_state("Gaussian Blur")
            self.project.processor.gaussian_blur(layer.data, dialog.sigma)
            self.canvas.refresh()
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
            self.status_label.setText("Generated Procedural Sky")

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
            self.status_label.setText("Applied Gradient Fill")

    # ================================================================
    #  ABOUT
    # ================================================================

    def _show_about(self):
        QMessageBox.about(
            self, "About HDRI Maker",
            "<h2>HDRI Maker v1.0</h2>"
            "<p>A surface painter for creating HDR environment images.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Paint HDR colors with intensity values > 1.0</li>"
            "<li>Layer system with blend modes</li>"
            "<li>Procedural sky generation</li>"
            "<li>Filters: blur, bloom, color grading, noise</li>"
            "<li>Real-time 3D preview</li>"
            "<li>Export to .hdr, .exr, .png</li>"
            "<li>Blender & Unity import support</li>"
            "</ul>"
            "<p><b>Components:</b> Python + C++ + C#</p>"
            "<p>Built with PySide6, NumPy, and custom C++ processing</p>"
        )


def run():
    """Entry point for the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("HDRI Maker")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")  # Use Fusion style as base for dark theme

    window = HDRIMakerApp()
    window.show()
    sys.exit(app.exec())
