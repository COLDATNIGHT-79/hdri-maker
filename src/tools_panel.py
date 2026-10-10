"""
Tools Panel for HDRI Maker.
Provides tool selection, brush settings, HDR color picker with intensity slider,
and fill effect controls.
"""

import numpy as np
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QGroupBox, QFormLayout, QColorDialog,
    QFrame, QSizePolicy, QDoubleSpinBox, QSpinBox, QToolButton
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon, QLinearGradient

from src.hdri_engine import BrushEngine
from src.canvas_widget import CanvasWidget


class ColorPreviewWidget(QWidget):
    """Widget showing the current HDR color with intensity."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = (1.0, 1.0, 1.0)
        self.intensity = 1.0
        self.setFixedSize(60, 60)
        self.setCursor(Qt.PointingHandCursor)

    def set_color(self, r, g, b, intensity=1.0):
        self.color = (r, g, b)
        self.intensity = intensity
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Outer ring showing actual HDR color (clamped)
        r = min(self.color[0] * self.intensity, 1.0)
        g = min(self.color[1] * self.intensity, 1.0)
        b = min(self.color[2] * self.intensity, 1.0)

        painter.setPen(QColor(100, 100, 100))
        painter.setBrush(QColor(int(r * 255), int(g * 255), int(b * 255)))
        painter.drawRoundedRect(2, 2, 56, 56, 8, 8)

        # Inner circle showing base color
        painter.setBrush(QColor(
            int(min(self.color[0], 1.0) * 255),
            int(min(self.color[1], 1.0) * 255),
            int(min(self.color[2], 1.0) * 255)
        ))
        painter.drawRoundedRect(16, 16, 28, 28, 4, 4)

        # Intensity indicator
        if self.intensity > 1.0:
            painter.setPen(QColor(255, 220, 50))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(1, 1, 58, 58, 8, 8)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class ToolsPanel(QDockWidget):
    """
    Tool selection and brush settings dock panel.
    """

    tool_changed = Signal(int)
    color_changed = Signal(float, float, float, float)  # r, g, b, intensity

    def __init__(self, brush: BrushEngine, canvas: CanvasWidget, parent=None):
        super().__init__("Tools", parent)
        self.brush = brush
        self.canvas = canvas
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(200)
        self.setMaximumWidth(260)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # === Tool Selection ===
        tools_group = QGroupBox("Tools")
        tools_group.setStyleSheet(self._group_style())
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(4)

        self._tool_buttons = {}
        tools = [
            (CanvasWidget.TOOL_BRUSH, "🖌", "Brush (B)"),
            (CanvasWidget.TOOL_ERASER, "🧹", "Eraser (E)"),
            (CanvasWidget.TOOL_FILL, "🪣", "Fill (G)"),
            (CanvasWidget.TOOL_EYEDROPPER, "💧", "Eyedropper (I)"),
        ]

        for tool_id, icon, tooltip in tools:
            btn = QPushButton(icon)
            btn.setToolTip(tooltip)
            btn.setFixedSize(40, 40)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3a3a3a; border: 1px solid #555;
                    border-radius: 6px; font-size: 18px;
                }
                QPushButton:checked {
                    background: #4682B4; border-color: #6ca8d9;
                }
                QPushButton:hover {
                    background: #4a4a4a; border-color: #777;
                }
            """)
            btn.clicked.connect(lambda checked, tid=tool_id: self._select_tool(tid))
            tools_layout.addWidget(btn)
            self._tool_buttons[tool_id] = btn

        tools_group.setLayout(tools_layout)
        main_layout.addWidget(tools_group)

        # Select brush by default
        self._tool_buttons[CanvasWidget.TOOL_BRUSH].setChecked(True)

        # === Brush Settings ===
        brush_group = QGroupBox("Brush Settings")
        brush_group.setStyleSheet(self._group_style())
        brush_layout = QFormLayout()
        brush_layout.setSpacing(8)

        # Brush size
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(1, 200)
        self.size_slider.setValue(self.brush.size)
        self.size_label = QLabel(str(self.brush.size))
        self.size_label.setFixedWidth(30)
        self.size_label.setStyleSheet("color: #ddd;")
        size_row = QHBoxLayout()
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_label)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        brush_layout.addRow("Size:", size_row)

        # Brush hardness
        self.hardness_slider = QSlider(Qt.Horizontal)
        self.hardness_slider.setRange(0, 100)
        self.hardness_slider.setValue(int(self.brush.hardness * 100))
        self.hardness_label = QLabel(f"{int(self.brush.hardness * 100)}%")
        self.hardness_label.setFixedWidth(30)
        self.hardness_label.setStyleSheet("color: #ddd;")
        hardness_row = QHBoxLayout()
        hardness_row.addWidget(self.hardness_slider)
        hardness_row.addWidget(self.hardness_label)
        self.hardness_slider.valueChanged.connect(self._on_hardness_changed)
        brush_layout.addRow("Hardness:", hardness_row)

        # Brush opacity
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(int(self.brush.opacity * 100))
        self.opacity_label = QLabel(f"{int(self.brush.opacity * 100)}%")
        self.opacity_label.setFixedWidth(30)
        self.opacity_label.setStyleSheet("color: #ddd;")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        brush_layout.addRow("Opacity:", opacity_row)

        brush_group.setLayout(brush_layout)
        main_layout.addWidget(brush_group)

        # === HDR Color Picker ===
        color_group = QGroupBox("HDR Color")
        color_group.setStyleSheet(self._group_style())
        color_layout = QVBoxLayout()
        color_layout.setSpacing(8)

        # Color preview
        color_preview_row = QHBoxLayout()
        self.color_preview = ColorPreviewWidget()
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)
        self.color_preview.clicked.connect(self._pick_color)
        color_preview_row.addWidget(self.color_preview)

        # Quick color buttons
        quick_colors_layout = QVBoxLayout()
        quick_colors_layout.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        quick_colors = [
            ((1, 1, 1), "White"),
            ((0, 0, 0), "Black"),
            ((1, 0, 0), "Red"),
            ((0, 1, 0), "Green"),
            ((0, 0, 1), "Blue"),
        ]
        for color, name in quick_colors:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgb({int(color[0]*255)},{int(color[1]*255)},{int(color[2]*255)});
                    border: 1px solid #666; border-radius: 3px;
                }}
                QPushButton:hover {{ border-color: white; }}
            """)
            btn.clicked.connect(lambda _, c=color: self._set_quick_color(c))
            row1.addWidget(btn)

        row2 = QHBoxLayout()
        row2.setSpacing(2)
        warm_colors = [
            ((1.0, 0.9, 0.7), "Warm White"),
            ((1.0, 0.6, 0.2), "Orange"),
            ((0.5, 0.8, 1.0), "Sky Blue"),
            ((0.2, 0.15, 0.3), "Dark Purple"),
            ((0.8, 0.7, 0.5), "Sand"),
        ]
        for color, name in warm_colors:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setToolTip(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgb({int(color[0]*255)},{int(color[1]*255)},{int(color[2]*255)});
                    border: 1px solid #666; border-radius: 3px;
                }}
                QPushButton:hover {{ border-color: white; }}
            """)
            btn.clicked.connect(lambda _, c=color: self._set_quick_color(c))
            row2.addWidget(btn)

        quick_colors_layout.addLayout(row1)
        quick_colors_layout.addLayout(row2)
        color_preview_row.addLayout(quick_colors_layout)
        color_layout.addLayout(color_preview_row)

        # HDR Intensity slider
        intensity_row = QHBoxLayout()
        intensity_label = QLabel("Intensity:")
        intensity_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.intensity_slider = QSlider(Qt.Horizontal)
        self.intensity_slider.setRange(1, 500)
        self.intensity_slider.setValue(int(self.brush.intensity * 10))
        self.intensity_value = QLabel(f"{self.brush.intensity:.1f}")
        self.intensity_value.setFixedWidth(35)
        self.intensity_value.setStyleSheet("color: #ddd; font-size: 11px;")
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)

        intensity_row.addWidget(intensity_label)
        intensity_row.addWidget(self.intensity_slider)
        intensity_row.addWidget(self.intensity_value)
        color_layout.addLayout(intensity_row)

        # Note about HDR
        note = QLabel("💡 Intensity > 1.0 creates light-emitting areas in the HDRI")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        color_layout.addWidget(note)

        color_group.setLayout(color_layout)
        main_layout.addWidget(color_group)

        # === View Controls ===
        view_group = QGroupBox("View")
        view_group.setStyleSheet(self._group_style())
        view_layout = QFormLayout()
        view_layout.setSpacing(6)

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
        view_layout.addRow("Exposure:", exp_row)

        # View buttons
        view_btns = QHBoxLayout()
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setToolTip("Fit canvas to view")
        self.btn_fit.clicked.connect(self.canvas.fit_to_view)
        self.btn_grid = QPushButton("Grid")
        self.btn_grid.setToolTip("Toggle grid overlay")
        self.btn_grid.setCheckable(True)
        self.btn_grid.toggled.connect(self.canvas.set_show_grid)

        for btn in [self.btn_fit, self.btn_grid]:
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton {
                    background: #3a3a3a; border: 1px solid #555;
                    border-radius: 4px; color: #ddd; padding: 2px 8px;
                }
                QPushButton:hover { background: #4a4a4a; }
                QPushButton:checked { background: #4682B4; }
            """)
            view_btns.addWidget(btn)

        view_layout.addRow(view_btns)

        view_group.setLayout(view_layout)
        main_layout.addWidget(view_group)

        main_layout.addStretch()
        self.setWidget(main_widget)

    def _group_style(self):
        return """
            QGroupBox {
                color: #ccc;
                font-size: 11px;
                font-weight: bold;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
        """

    # ================================================================
    #  SLOTS
    # ================================================================

    def _select_tool(self, tool_id: int):
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)
        self.canvas.tool = tool_id
        self.tool_changed.emit(tool_id)

    def _on_size_changed(self, value):
        self.brush.size = value
        self.brush._stamp_cache.clear()
        self.size_label.setText(str(value))

    def _on_hardness_changed(self, value):
        self.brush.hardness = value / 100.0
        self.brush._stamp_cache.clear()
        self.hardness_label.setText(f"{value}%")

    def _on_opacity_changed(self, value):
        self.brush.opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")

    def _on_intensity_changed(self, value):
        self.brush.intensity = value / 10.0
        self.intensity_value.setText(f"{value / 10.0:.1f}")
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)

    def _on_exposure_changed(self, value):
        exposure = value / 10.0
        self.exposure_label.setText(f"{exposure:.1f}")
        self.canvas.set_exposure(exposure)

    def _pick_color(self):
        """Open color picker dialog."""
        current = QColor(
            int(min(self.brush.color[0], 1.0) * 255),
            int(min(self.brush.color[1], 1.0) * 255),
            int(min(self.brush.color[2], 1.0) * 255)
        )
        color = QColorDialog.getColor(current, self, "Pick HDR Base Color")
        if color.isValid():
            r = color.redF()
            g = color.greenF()
            b = color.blueF()
            self.brush.color = (r, g, b, 1.0)
            self.color_preview.set_color(r, g, b, self.brush.intensity)
            self.color_changed.emit(r, g, b, self.brush.intensity)

    def _set_quick_color(self, color_tuple):
        r, g, b = color_tuple
        self.brush.color = (r, g, b, 1.0)
        self.color_preview.set_color(r, g, b, self.brush.intensity)
        self.color_changed.emit(r, g, b, self.brush.intensity)

    def update_from_brush(self):
        """Update UI to reflect current brush state."""
        self.color_preview.set_color(*self.brush.color[:3], self.brush.intensity)
        self.intensity_slider.blockSignals(True)
        self.intensity_slider.setValue(int(self.brush.intensity * 10))
        self.intensity_slider.blockSignals(False)
        self.intensity_value.setText(f"{self.brush.intensity:.1f}")
