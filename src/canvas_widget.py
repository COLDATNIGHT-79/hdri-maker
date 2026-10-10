"""
Canvas Widget for HDRI Maker.
Displays the equirectangular HDRI canvas and handles painting operations.
"""

import numpy as np
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPixmap, QCursor,
    QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent
)

from src.hdri_engine import HDRIProject, BrushEngine


class CanvasWidget(QWidget):
    """
    HDRI painting canvas widget.
    Displays the composited layers in equirectangular projection
    and handles brush/eraser/fill painting operations.
    """

    canvas_modified = Signal()
    cursor_position_changed = Signal(int, int)  # x, y on canvas

    # Tool modes
    TOOL_BRUSH = 0
    TOOL_ERASER = 1
    TOOL_FILL = 2
    TOOL_EYEDROPPER = 3

    def __init__(self, project: HDRIProject, brush: BrushEngine, parent=None):
        super().__init__(parent)
        self.project = project
        self.brush = brush
        self.tool = self.TOOL_BRUSH

        # View state
        self._zoom = 1.0
        self._pan_offset = QPoint(0, 0)
        self._panning = False
        self._pan_start = QPoint(0, 0)
        self._painting = False
        self._last_paint_pos = None

        # Display settings
        self._exposure = 0.0
        self._show_grid = False
        self._display_buffer = None
        self._display_dirty = True

        # Performance: throttle composite updates
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._deferred_update)

        self.setMinimumSize(400, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Checkerboard pattern for alpha visualization
        self._checker_pixmap = self._create_checker_pattern()

    def _create_checker_pattern(self, tile_size=16) -> QPixmap:
        """Create a checkerboard pattern for transparent areas."""
        size = tile_size * 2
        pixmap = QPixmap(size, size)
        painter = QPainter(pixmap)
        c1 = QColor(60, 60, 60)
        c2 = QColor(80, 80, 80)
        painter.fillRect(0, 0, tile_size, tile_size, c1)
        painter.fillRect(tile_size, 0, tile_size, tile_size, c2)
        painter.fillRect(0, tile_size, tile_size, tile_size, c2)
        painter.fillRect(tile_size, tile_size, tile_size, tile_size, c1)
        painter.end()
        return pixmap

    # ================================================================
    #  VIEW CONTROLS
    # ================================================================

    def set_zoom(self, zoom: float):
        """Set zoom level."""
        self._zoom = max(0.1, min(10.0, zoom))
        self.update()

    def zoom_in(self):
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self._zoom / 1.25)

    def fit_to_view(self):
        """Fit the canvas to the widget size."""
        w_ratio = self.width() / self.project.width
        h_ratio = self.height() / self.project.height
        self._zoom = min(w_ratio, h_ratio) * 0.95
        self._pan_offset = QPoint(0, 0)
        self.update()

    def set_exposure(self, exposure: float):
        """Set display exposure for preview."""
        self._exposure = exposure
        self._display_dirty = True
        self.update()

    def set_show_grid(self, show: bool):
        self._show_grid = show
        self.update()

    # ================================================================
    #  COORDINATE TRANSFORMS
    # ================================================================

    def _widget_to_canvas(self, widget_pos: QPoint) -> tuple:
        """Convert widget coordinates to canvas pixel coordinates."""
        cx = self.width() / 2 + self._pan_offset.x()
        cy = self.height() / 2 + self._pan_offset.y()

        canvas_x = (widget_pos.x() - cx) / self._zoom + self.project.width / 2
        canvas_y = (widget_pos.y() - cy) / self._zoom + self.project.height / 2

        return int(canvas_x), int(canvas_y)

    def _canvas_to_widget(self, canvas_x: int, canvas_y: int) -> QPoint:
        """Convert canvas pixel coordinates to widget coordinates."""
        cx = self.width() / 2 + self._pan_offset.x()
        cy = self.height() / 2 + self._pan_offset.y()

        wx = (canvas_x - self.project.width / 2) * self._zoom + cx
        wy = (canvas_y - self.project.height / 2) * self._zoom + cy

        return QPoint(int(wx), int(wy))

    # ================================================================
    #  DISPLAY BUFFER
    # ================================================================

    def _update_display_buffer(self):
        """Update the tone-mapped display buffer from the composited HDR data."""
        composite = self.project.get_composite()

        # Simple tone mapping for display
        exp_scale = 2.0 ** self._exposure
        rgb = composite[:, :, :3] * exp_scale

        # ACES tone map
        a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
        mapped = np.clip((rgb * (a * rgb + b)) / (rgb * (c * rgb + d) + e), 0, 1)

        # Gamma correction
        mapped = np.power(mapped, 1.0 / 2.2)

        # Alpha channel
        alpha = np.clip(composite[:, :, 3], 0, 1)

        # Compose with checkerboard for transparency visualization
        rgba = np.zeros((*mapped.shape[:2], 4), dtype=np.uint8)
        rgba[:, :, 0] = (mapped[:, :, 0] * alpha * 255).astype(np.uint8)
        rgba[:, :, 1] = (mapped[:, :, 1] * alpha * 255).astype(np.uint8)
        rgba[:, :, 2] = (mapped[:, :, 2] * alpha * 255).astype(np.uint8)
        rgba[:, :, 3] = (alpha * 255).astype(np.uint8)

        h, w = rgba.shape[:2]
        self._display_buffer = QImage(
            rgba.tobytes(), w, h, w * 4, QImage.Format_RGBA8888
        ).copy()
        self._display_dirty = False

    # ================================================================
    #  PAINTING
    # ================================================================

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Dark background
        painter.fillRect(self.rect(), QColor(30, 30, 35))

        if self._display_dirty or self._display_buffer is None:
            self._update_display_buffer()

        if self._display_buffer is not None:
            # Calculate display rect
            canvas_w = int(self.project.width * self._zoom)
            canvas_h = int(self.project.height * self._zoom)
            cx = self.width() // 2 + self._pan_offset.x() - canvas_w // 2
            cy = self.height() // 2 + self._pan_offset.y() - canvas_h // 2
            dest_rect = QRect(cx, cy, canvas_w, canvas_h)

            # Draw checkerboard background
            painter.setBrush(self._checker_pixmap)
            painter.setPen(Qt.NoPen)
            painter.drawRect(dest_rect)

            # Draw the HDRI image
            pixmap = QPixmap.fromImage(self._display_buffer)
            painter.drawPixmap(dest_rect, pixmap)

            # Draw grid overlay
            if self._show_grid:
                self._draw_grid(painter, dest_rect)

            # Draw canvas border
            painter.setPen(QColor(100, 100, 100))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(dest_rect)

        # Draw brush cursor
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            self._draw_brush_cursor(painter)

        painter.end()

    def _draw_grid(self, painter: QPainter, rect: QRect):
        """Draw equirectangular grid overlay."""
        painter.setPen(QColor(255, 255, 255, 40))

        # Vertical lines (longitude)
        for i in range(1, 8):
            x = rect.x() + int(rect.width() * i / 8)
            painter.drawLine(x, rect.y(), x, rect.y() + rect.height())

        # Horizontal lines (latitude)
        for i in range(1, 4):
            y = rect.y() + int(rect.height() * i / 4)
            painter.drawLine(rect.x(), y, rect.x() + rect.width(), y)

        # Horizon line (stronger)
        painter.setPen(QColor(255, 200, 50, 80))
        mid_y = rect.y() + rect.height() // 2
        painter.drawLine(rect.x(), mid_y, rect.x() + rect.width(), mid_y)

    def _draw_brush_cursor(self, painter: QPainter):
        """Draw the brush cursor at current mouse position."""
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            return

        radius = int(self.brush.size * self._zoom)
        if self.tool == self.TOOL_ERASER:
            painter.setPen(QColor(255, 100, 100, 180))
        else:
            painter.setPen(QColor(255, 255, 255, 180))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(pos, radius, radius)

    # ================================================================
    #  MOUSE EVENTS
    # ================================================================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.LeftButton:
            if self.tool == self.TOOL_EYEDROPPER:
                self._eyedrop(event.pos())
            elif self.tool == self.TOOL_FILL:
                self._fill_layer(event.pos())
            elif self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
                self._painting = True
                self._last_paint_pos = event.pos()
                self.project.save_undo_state("Paint stroke")
                self._do_paint(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        # Update cursor position display
        cx, cy = self._widget_to_canvas(event.pos())
        if 0 <= cx < self.project.width and 0 <= cy < self.project.height:
            self.cursor_position_changed.emit(cx, cy)

        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_offset += delta
            self._pan_start = event.pos()
            self.update()
        elif self._painting:
            self._do_paint(event.pos())
        else:
            self.update()  # Update brush cursor

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
        elif event.button() == Qt.LeftButton:
            self._painting = False
            self._last_paint_pos = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self._display_buffer is None:
            self.fit_to_view()

    # ================================================================
    #  PAINT OPERATIONS
    # ================================================================

    def _do_paint(self, widget_pos: QPoint):
        """Execute paint/erase at a widget position."""
        layer = self.project.active_layer
        if not layer or layer.locked:
            return

        cx, cy = self._widget_to_canvas(widget_pos)

        if self._last_paint_pos:
            lx, ly = self._widget_to_canvas(self._last_paint_pos)
            self.brush.paint_line(layer, lx, ly, cx, cy,
                                  erase=(self.tool == self.TOOL_ERASER))
        else:
            self.brush.paint_stroke(layer, cx, cy,
                                     erase=(self.tool == self.TOOL_ERASER))

        self._last_paint_pos = widget_pos
        self.project.invalidate_cache()
        self._display_dirty = True

        # Throttled update for performance
        if not self._update_timer.isActive():
            self._update_timer.start(16)  # ~60fps

    def _deferred_update(self):
        """Deferred update for performance."""
        self.update()
        self.canvas_modified.emit()

    def _eyedrop(self, widget_pos: QPoint):
        """Pick color from the composite at the given position."""
        cx, cy = self._widget_to_canvas(widget_pos)
        composite = self.project.get_composite()

        if 0 <= cx < self.project.width and 0 <= cy < self.project.height:
            r = float(composite[cy, cx, 0])
            g = float(composite[cy, cx, 1])
            b = float(composite[cy, cx, 2])

            # Determine intensity (max component)
            max_val = max(r, g, b, 0.001)
            self.brush.intensity = max_val
            if max_val > 0:
                self.brush.color = (r / max_val, g / max_val, b / max_val, 1.0)
            else:
                self.brush.color = (0, 0, 0, 1.0)

    def _fill_layer(self, widget_pos: QPoint):
        """Fill the current layer with the current color."""
        layer = self.project.active_layer
        if not layer or layer.locked:
            return

        self.project.save_undo_state("Fill layer")
        r = self.brush.color[0] * self.brush.intensity
        g = self.brush.color[1] * self.brush.intensity
        b = self.brush.color[2] * self.brush.intensity
        layer.data[:, :, 0] = r
        layer.data[:, :, 1] = g
        layer.data[:, :, 2] = b
        layer.data[:, :, 3] = self.brush.opacity

        self.project.invalidate_cache()
        self._display_dirty = True
        self.update()
        self.canvas_modified.emit()

    def refresh(self):
        """Force a full refresh of the display."""
        self.project.invalidate_cache()
        self._display_dirty = True
        self.update()
        self.canvas_modified.emit()
