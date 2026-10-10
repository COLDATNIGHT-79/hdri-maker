"""
Layer Panel for HDRI Maker.
Provides a dock widget for managing HDRI layers with thumbnails,
visibility toggles, opacity, blend modes, and reordering.
"""

import numpy as np
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QMenu, QToolButton, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QImage, QPixmap, QIcon, QColor, QAction, QDrag

from src.hdri_engine import HDRIProject, BlendMode, BLEND_MODE_NAMES


class LayerItemWidget(QWidget):
    """Custom widget for each layer item in the list."""

    visibility_toggled = Signal(int, bool)  # layer_index, visible
    selected = Signal(int)  # layer_index

    def __init__(self, layer_index: int, name: str, visible: bool = True,
                 thumbnail: np.ndarray = None, parent=None):
        super().__init__(parent)
        self.layer_index = layer_index

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Visibility toggle
        self.vis_btn = QPushButton("👁")
        self.vis_btn.setFixedSize(28, 28)
        self.vis_btn.setCheckable(True)
        self.vis_btn.setChecked(visible)
        self.vis_btn.setToolTip("Toggle visibility")
        self.vis_btn.setStyleSheet("""
            QPushButton { 
                border: none; background: transparent; font-size: 14px; 
                border-radius: 4px;
            }
            QPushButton:checked { background: rgba(255,255,255,0.1); }
            QPushButton:hover { background: rgba(255,255,255,0.15); }
        """)
        self.vis_btn.toggled.connect(
            lambda checked: self.visibility_toggled.emit(self.layer_index, checked)
        )
        layout.addWidget(self.vis_btn)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(40, 40)
        self.thumb_label.setStyleSheet(
            "border: 1px solid #555; border-radius: 3px; background: #2a2a2a;"
        )
        if thumbnail is not None:
            self._set_thumbnail(thumbnail)
        layout.addWidget(self.thumb_label)

        # Layer name
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("color: #ddd; font-size: 12px;")
        layout.addWidget(self.name_label, 1)

    def _set_thumbnail(self, thumb_data: np.ndarray):
        """Set the thumbnail from a numpy RGBA array."""
        h, w = thumb_data.shape[:2]
        img = QImage(thumb_data.tobytes(), w, h, w * 4, QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(img).scaled(
            38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.thumb_label.setPixmap(pixmap)

    def update_thumbnail(self, thumb_data: np.ndarray):
        self._set_thumbnail(thumb_data)

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("background: rgba(70, 130, 220, 0.25); border-radius: 4px;")
        else:
            self.setStyleSheet("")


class LayerPanel(QDockWidget):
    """
    Layer management dock panel.
    Shows the layer stack and provides controls for manipulation.
    """

    layer_changed = Signal()
    active_layer_changed = Signal(int)

    def __init__(self, project: HDRIProject, parent=None):
        super().__init__("Layers", parent)
        self.project = project
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(220)

        # Main widget
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # === Blend mode and opacity controls ===
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
            }
        """)
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(6)

        # Blend mode
        blend_row = QHBoxLayout()
        blend_label = QLabel("Blend:")
        blend_label.setStyleSheet("color: #aaa; font-size: 11px;")
        blend_label.setFixedWidth(45)
        self.blend_combo = QComboBox()
        for mode in BlendMode:
            self.blend_combo.addItem(BLEND_MODE_NAMES[mode], mode)
        self.blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        self.blend_combo.setStyleSheet("""
            QComboBox {
                background: #3a3a3a; color: #ddd; border: 1px solid #555;
                border-radius: 3px; padding: 3px 8px;
            }
        """)
        blend_row.addWidget(blend_label)
        blend_row.addWidget(self.blend_combo)
        controls_layout.addLayout(blend_row)

        # Opacity
        opacity_row = QHBoxLayout()
        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("color: #aaa; font-size: 11px;")
        opacity_label.setFixedWidth(45)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_value = QLabel("100%")
        self.opacity_value.setStyleSheet("color: #ddd; font-size: 11px;")
        self.opacity_value.setFixedWidth(35)
        opacity_row.addWidget(opacity_label)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value)
        controls_layout.addLayout(opacity_row)

        main_layout.addWidget(controls_frame)

        # === Layer list ===
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.layer_list.setDefaultDropAction(Qt.MoveAction)
        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        self.layer_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layer_list.customContextMenuRequested.connect(self._show_context_menu)
        self.layer_list.setStyleSheet("""
            QListWidget {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #333;
                padding: 2px;
            }
            QListWidget::item:selected {
                background: rgba(70, 130, 220, 0.3);
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.05);
            }
        """)
        main_layout.addWidget(self.layer_list, 1)

        # === Action buttons ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_add = self._make_button("➕", "Add new layer")
        self.btn_delete = self._make_button("🗑", "Delete layer")
        self.btn_duplicate = self._make_button("📋", "Duplicate layer")
        self.btn_merge = self._make_button("⬇", "Merge down")
        self.btn_up = self._make_button("⬆", "Move up")
        self.btn_down = self._make_button("⬇", "Move down")

        self.btn_add.clicked.connect(self._add_layer)
        self.btn_delete.clicked.connect(self._delete_layer)
        self.btn_duplicate.clicked.connect(self._duplicate_layer)
        self.btn_merge.clicked.connect(self._merge_down)
        self.btn_up.clicked.connect(self._move_up)
        self.btn_down.clicked.connect(self._move_down)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_duplicate)
        btn_layout.addWidget(self.btn_merge)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)

        main_layout.addLayout(btn_layout)

        self.setWidget(main_widget)
        self._refresh_list()

    def _make_button(self, text: str, tooltip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(32, 32)
        btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 14px;
                color: #ddd;
            }
            QPushButton:hover {
                background: #4a4a4a;
                border-color: #777;
            }
            QPushButton:pressed {
                background: #555;
            }
        """)
        return btn

    # ================================================================
    #  LIST MANAGEMENT
    # ================================================================

    def _refresh_list(self):
        """Rebuild the layer list from the project."""
        self.layer_list.blockSignals(True)
        self.layer_list.clear()

        # Layers displayed top-to-bottom (top layer first)
        for i in range(len(self.project.layers) - 1, -1, -1):
            layer = self.project.layers[i]
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 50))
            item.setData(Qt.UserRole, i)

            widget = LayerItemWidget(
                i, layer.name, layer.visible,
                thumbnail=layer.get_thumbnail()
            )
            widget.visibility_toggled.connect(self._on_visibility_toggled)

            self.layer_list.addItem(item)
            self.layer_list.setItemWidget(item, widget)

        # Select active layer
        active_row = len(self.project.layers) - 1 - self.project.active_layer_index
        if 0 <= active_row < self.layer_list.count():
            self.layer_list.setCurrentRow(active_row)
            widget = self.layer_list.itemWidget(self.layer_list.item(active_row))
            if widget:
                widget.set_active(True)

        # Update blend/opacity controls
        layer = self.project.active_layer
        if layer:
            self.blend_combo.blockSignals(True)
            self.blend_combo.setCurrentIndex(int(layer.blend_mode))
            self.blend_combo.blockSignals(False)

            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(int(layer.opacity * 100))
            self.opacity_slider.blockSignals(False)
            self.opacity_value.setText(f"{int(layer.opacity * 100)}%")

        self.layer_list.blockSignals(False)

    def refresh(self):
        """Public method to refresh the layer list."""
        self._refresh_list()

    def update_thumbnails(self):
        """Update all layer thumbnails."""
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            widget = self.layer_list.itemWidget(item)
            if widget:
                layer_idx = widget.layer_index
                if 0 <= layer_idx < len(self.project.layers):
                    thumb = self.project.layers[layer_idx].get_thumbnail()
                    widget.update_thumbnail(thumb)

    # ================================================================
    #  SLOTS
    # ================================================================

    def _on_layer_selected(self, row):
        if row < 0:
            return
        item = self.layer_list.item(row)
        if item:
            layer_index = item.data(Qt.UserRole)
            if layer_index is not None:
                self.project.active_layer_index = layer_index
                self.active_layer_changed.emit(layer_index)
                self._refresh_list()

    def _on_visibility_toggled(self, layer_index, visible):
        if 0 <= layer_index < len(self.project.layers):
            self.project.layers[layer_index].visible = visible
            self.project.invalidate_cache()
            self.layer_changed.emit()

    def _on_blend_changed(self, index):
        layer = self.project.active_layer
        if layer:
            layer.blend_mode = BlendMode(index)
            self.project.invalidate_cache()
            self.layer_changed.emit()

    def _on_opacity_changed(self, value):
        layer = self.project.active_layer
        if layer:
            layer.opacity = value / 100.0
            self.opacity_value.setText(f"{value}%")
            self.project.invalidate_cache()
            self.layer_changed.emit()

    def _add_layer(self):
        self.project.save_undo_state("Add layer")
        self.project.add_layer()
        self._refresh_list()
        self.layer_changed.emit()

    def _delete_layer(self):
        if len(self.project.layers) <= 1:
            return
        self.project.save_undo_state("Delete layer")
        self.project.remove_layer(self.project.active_layer_index)
        self._refresh_list()
        self.layer_changed.emit()

    def _duplicate_layer(self):
        self.project.save_undo_state("Duplicate layer")
        self.project.duplicate_layer(self.project.active_layer_index)
        self._refresh_list()
        self.layer_changed.emit()

    def _merge_down(self):
        if self.project.active_layer_index > 0:
            self.project.save_undo_state("Merge down")
            self.project.merge_down(self.project.active_layer_index)
            self._refresh_list()
            self.layer_changed.emit()

    def _move_up(self):
        idx = self.project.active_layer_index
        if idx < len(self.project.layers) - 1:
            self.project.move_layer(idx, idx + 1)
            self._refresh_list()
            self.layer_changed.emit()

    def _move_down(self):
        idx = self.project.active_layer_index
        if idx > 0:
            self.project.move_layer(idx, idx - 1)
            self._refresh_list()
            self.layer_changed.emit()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #333;
                color: #ddd;
                border: 1px solid #555;
            }
            QMenu::item:selected {
                background: #4682B4;
            }
        """)

        menu.addAction("Add Layer", self._add_layer)
        menu.addAction("Duplicate Layer", self._duplicate_layer)
        menu.addSeparator()
        menu.addAction("Merge Down", self._merge_down)
        menu.addSeparator()
        menu.addAction("Delete Layer", self._delete_layer)

        menu.exec(self.layer_list.mapToGlobal(pos))
