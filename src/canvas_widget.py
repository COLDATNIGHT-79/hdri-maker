"""
Canvas Widget for HDRI Maker.
Displays the equirectangular HDRI canvas and handles painting operations.
"""

import math
import numpy as np
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal, QPoint, QRect, QSize, QTimer
from PySide6.QtGui import (
    QImage, QPainter, QColor, QPixmap, QCursor,
    QMouseEvent, QWheelEvent, QPaintEvent, QResizeEvent,
    QRadialGradient, QPen
)

from src.hdri_engine import HDRIProject, BrushEngine, LayerType


class CanvasWidget(QWidget):
    """
    HDRI painting canvas widget.
    Displays the composited layers in equirectangular projection
    and handles brush/eraser/fill/sun/cloud/stamp operations with living corona and glowing viewport.
    """

    canvas_modified = Signal()
    cursor_position_changed = Signal(int, int)  # x, y on canvas
    sun_moved = Signal(float, float)            # azimuth, elevation (0-1)
    stamp_placed = Signal(float, float)         # x, y (0-1)

    # Tool modes
    TOOL_BRUSH = 0
    TOOL_ERASER = 1
    TOOL_FILL = 2
    TOOL_EYEDROPPER = 3
    TOOL_SUN = 4
    TOOL_CLOUD = 5
    TOOL_STAMP = 6

    def __init__(self, project: HDRIProject, brush: BrushEngine, parent=None):
        super().__init__(parent)
        self.project = project
        self.brush = brush
        self.tool = self.TOOL_BRUSH

        # Stamp tool settings
        self.selected_stamp = None
        self.stamp_scale = 1.0
        self.stamp_rotation = 0.0
        self.stamp_flip_h = False
        self.stamp_opacity = 1.0
        self.stamp_silhouette_mode = True
        self.stamp_color = (0.0, 0.0, 0.0)

        # Cloud tool settings
        from src.cloud_engine import CloudSettings
        self.cloud_settings = CloudSettings.preset_cumulus()

        # Sun tool interaction
        self._dragging_sun = False
        self.paint_mask_mode = False

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
        self._cached_pixmap = None
        self._display_dirty = True

        # Performance: throttle composite updates
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._deferred_update)

        # Animated corona pulse timer for sun visualization
        self._corona_tick = 0
        self._corona_timer = QTimer(self)
        self._corona_timer.timeout.connect(self._on_corona_tick)
        self._corona_timer.start(80)

        self.setMinimumSize(400, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Checkerboard pattern for alpha visualization
        self._checker_pixmap = self._create_checker_pattern()

    def _on_corona_tick(self):
        self._corona_tick = (self._corona_tick + 1) % 60
        if self.isVisible() and (self.tool == self.TOOL_SUN or (self.project.primary_sun and self._show_grid)):
            self.update()

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
        """Update the tone-mapped display buffer and cache QPixmap from the composited HDR data."""
        composite = self.project.get_composite()

        # Simple tone mapping for display
        exp_scale = 2.0 ** self._exposure
        rgb = composite[:, :, :3] * exp_scale

        # ACES tone map
        a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
        mapped = np.clip((rgb * (a * rgb + b)) / (rgb * (c * rgb + d) + e), 0.0, 1.0)

        # Gamma correction
        mapped = np.power(mapped, 1.0 / 2.2)

        # Alpha channel
        alpha = np.clip(composite[:, :, 3], 0.0, 1.0)

        # Fast SIMD RGBA conversion
        h, w = mapped.shape[:2]
        rgba = np.empty((h, w, 4), dtype=np.uint8)
        rgba[..., :3] = (mapped * (alpha[..., np.newaxis] * 255.0)).astype(np.uint8)
        rgba[..., 3] = (alpha * 255.0).astype(np.uint8)

        self._display_buffer = QImage(
            rgba.data, w, h, w * 4, QImage.Format_RGBA8888
        ).copy()
        self._cached_pixmap = QPixmap.fromImage(self._display_buffer)
        self._display_dirty = False

    # ================================================================
    #  PAINTING
    # ================================================================

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Dark background
        painter.fillRect(self.rect(), QColor(30, 30, 35))

        if self._display_dirty or self._cached_pixmap is None:
            self._update_display_buffer()

        if self._cached_pixmap is not None:
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

            # Draw the cached HDRI image directly (instant GPU texture blit, 0 CPU alloc)
            painter.drawPixmap(dest_rect, self._cached_pixmap)

            # Draw grid overlay
            if self._show_grid:
                self._draw_grid(painter, dest_rect)

            # Draw luminous canvas frame with subtle glow
            painter.setPen(QPen(QColor(0, 242, 254, 150), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(dest_rect)

        # Draw cursor overlays
        if self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER, self.TOOL_CLOUD):
            self._draw_brush_cursor(painter)
        elif self.tool == self.TOOL_STAMP:
            self._draw_stamp_cursor(painter)

        # Draw sun indicator
        if self.tool == self.TOOL_SUN or (self.project.primary_sun and self._show_grid):
            self._draw_sun_marker(painter)

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

        # Horizon line (stronger glowing gold)
        painter.setPen(QColor(255, 200, 50, 110))
        mid_y = rect.y() + rect.height() // 2
        painter.drawLine(rect.x(), mid_y, rect.x() + rect.width(), mid_y)

    def _draw_brush_cursor(self, painter: QPainter):
        """Draw the brush cursor at current mouse position."""
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            return

        radius = int(self.brush.size * self._zoom)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.tool == self.TOOL_ERASER:
            painter.setPen(QColor(255, 100, 100, 180))
        elif self.tool == self.TOOL_CLOUD:
            painter.setPen(QColor(180, 220, 255, 200))
        else:
            painter.setPen(QColor(0, 242, 254, 200))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(pos, radius, radius)

    def _draw_stamp_cursor(self, painter: QPainter):
        """Draw stamp ghost/box cursor."""
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            return

        size = max(16, int(64 * self.stamp_scale * self._zoom))
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(0, 242, 254, 220))
        painter.setBrush(QColor(0, 242, 254, 35))

        painter.save()
        painter.translate(pos.x(), pos.y())
        painter.rotate(self.stamp_rotation)
        painter.drawRect(-size // 2, -size // 2, size, size)
        painter.drawLine(-size // 2, 0, size // 2, 0)
        painter.drawLine(0, -size // 2, 0, size // 2)
        painter.restore()

    def _draw_sun_marker(self, painter: QPainter):
        """Draw the sun position marker with animated radiant corona and rays."""
        sun = self.project.primary_sun
        if not sun:
            return

        sx = int(sun.azimuth * self.project.width)
        sy = int(sun.elevation * self.project.height)
        wpos = self._canvas_to_widget(sx, sy)
        if not self.rect().contains(wpos):
            return

        painter.setRenderHint(QPainter.Antialiasing)

        pulse = 0.88 + 0.22 * math.sin(self._corona_tick * math.pi / 30)
        corona_r = int(24 * pulse)

        # Ambient radiant gold/cyan corona
        grad = QRadialGradient(wpos.x(), wpos.y(), corona_r * 2)
        grad.setColorAt(0.0, QColor(255, 255, 255, 230))
        grad.setColorAt(0.3, QColor(255, 215, 0, 160))
        grad.setColorAt(0.7, QColor(255, 120, 0, 70))
        grad.setColorAt(1.0, QColor(0, 242, 254, 0))
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(wpos, corona_r * 2, corona_r * 2)

        # Sun disc
        painter.setPen(QColor(255, 255, 255, 220))
        painter.setBrush(QColor(255, 240, 150, 200))
        painter.drawEllipse(wpos, 12, 12)

        # Animated spinning & pulsing rays
        base_angle = self._corona_tick * 1.5
        for i in range(12):
            deg = base_angle + i * 30
            rad = math.radians(deg)
            is_long = (i % 2 == 0)
            ray_len = (32 if is_long else 22) * pulse
            x1 = wpos.x() + int(14 * math.cos(rad))
            y1 = wpos.y() + int(14 * math.sin(rad))
            x2 = wpos.x() + int(ray_len * math.cos(rad))
            y2 = wpos.y() + int(ray_len * math.sin(rad))

            col = QColor(255, 225, 100, 200 if is_long else 130)
            painter.setPen(QPen(col, 1.5 if is_long else 1.0))
            painter.drawLine(x1, y1, x2, y2)

        # Crosshairs with glowing ends
        painter.setPen(QPen(QColor(0, 242, 254, 180), 1, Qt.DashLine))
        painter.drawLine(wpos.x() - 36, wpos.y(), wpos.x() + 36, wpos.y())
        painter.drawLine(wpos.x(), wpos.y() - 36, wpos.x(), wpos.y() + 36)

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
            elif self.tool == self.TOOL_SUN:
                self._dragging_sun = True
                self.project.save_undo_state("Move Sun")
                self._place_or_drag_sun(event.pos())
            elif self.tool == self.TOOL_STAMP:
                self._place_stamp(event.pos())
            elif self.tool == self.TOOL_CLOUD:
                self._painting = True
                self._last_paint_pos = event.pos()
                self.project.save_undo_state("Paint clouds")
                self._do_paint(event.pos())
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
        elif self._dragging_sun:
            self._place_or_drag_sun(event.pos())
        elif self._painting:
            self._do_paint(event.pos())
        else:
            self.update()  # Update brush/stamp cursor

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
        elif event.button() == Qt.LeftButton:
            was_active = self._painting or self._dragging_sun
            self._painting = False
            self._dragging_sun = False
            self._last_paint_pos = None
            if was_active:
                self.canvas_modified.emit()

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
    #  PAINT & TOOL OPERATIONS
    # ================================================================

    def _place_or_drag_sun(self, widget_pos: QPoint):
        """Update or place sun at widget position."""
        cx, cy = self._widget_to_canvas(widget_pos)
        az = float(np.clip(cx / self.project.width, 0.0, 1.0))
        el = float(np.clip(cy / self.project.height, 0.0, 1.0))

        # Find active sun layer or any sun layer
        layer = self.project.active_layer
        if not layer or layer.layer_type != LayerType.SUN:
            sun_layer = None
            for l in self.project.layers:
                if l.layer_type == LayerType.SUN:
                    sun_layer = l
                    break
            if sun_layer is None:
                sun_layer = self.project.add_sun_layer("Sun")
            layer = sun_layer
            self.project.active_layer_index = self.project.layers.index(layer)

        if not layer.suns:
            from src.hdri_engine import SunObject
            layer.suns.append(SunObject())

        layer.suns[0].azimuth = az
        layer.suns[0].elevation = el
        layer.regenerate(self.project)
        self.project.invalidate_cache()
        self._display_dirty = True
        self.update()
        if not self._dragging_sun:
            self.canvas_modified.emit()
        self.sun_moved.emit(az, el)

    def _place_stamp(self, widget_pos: QPoint):
        """Place the selected stamp asset at the clicked location."""
        if not self.selected_stamp:
            return

        cx, cy = self._widget_to_canvas(widget_pos)
        norm_x = float(np.clip(cx / self.project.width, 0.0, 1.0))
        norm_y = float(np.clip(cy / self.project.height, 0.0, 1.0))

        layer = self.project.active_layer
        if not layer or layer.locked:
            return

        self.project.save_undo_state("Place Stamp")

        from src.stamp_library import StampInstance, render_stamp
        inst = StampInstance()
        inst.stamp_id = self.selected_stamp.stamp_id
        inst.category = self.selected_stamp.category
        inst.x = norm_x
        inst.y = norm_y
        inst.scale = self.stamp_scale
        inst.rotation = self.stamp_rotation
        inst.flip_h = self.stamp_flip_h
        inst.opacity = self.stamp_opacity
        inst.color = self.stamp_color
        inst.silhouette_mode = self.stamp_silhouette_mode

        if layer.layer_type == LayerType.STAMP:
            layer.stamps.append(inst)
            layer.regenerate(self.project)
        else:
            render_stamp(layer.data, self.selected_stamp.image_data, inst)

        self.project.invalidate_cache()
        self._display_dirty = True
        self.update()
        self.canvas_modified.emit()
        self.stamp_placed.emit(norm_x, norm_y)

    def _do_paint(self, widget_pos: QPoint):
        """Execute paint/erase/cloud at a widget position."""
        layer = self.project.active_layer
        if not layer or layer.locked:
            return

        cx, cy = self._widget_to_canvas(widget_pos)

        if self.tool == self.TOOL_CLOUD:
            sun = self.project.primary_sun
            sun_az = sun.azimuth if sun else 0.25
            sun_el = sun.elevation if sun else 0.25
            sun_col = sun.color if sun else (1.0, 0.95, 0.85)

            if self._last_paint_pos:
                lx, ly = self._widget_to_canvas(self._last_paint_pos)
                self.brush.paint_cloud_line(layer, lx, ly, cx, cy,
                                            self.cloud_settings, sun_az, sun_el, sun_col)
            else:
                self.brush.paint_cloud_stroke(layer, cx, cy,
                                              self.cloud_settings, sun_az, sun_el, sun_col)
        elif self.tool in (self.TOOL_BRUSH, self.TOOL_ERASER):
            if self._last_paint_pos:
                lx, ly = self._widget_to_canvas(self._last_paint_pos)
                self.brush.paint_line(layer, lx, ly, cx, cy,
                                      erase=(self.tool == self.TOOL_ERASER),
                                      paint_mask=self.paint_mask_mode)
            else:
                self.brush.paint_stroke(layer, cx, cy,
                                        erase=(self.tool == self.TOOL_ERASER),
                                        paint_mask=self.paint_mask_mode)

        self._last_paint_pos = widget_pos
        self.project.invalidate_cache()
        self._display_dirty = True

        # Throttled update for performance
        if not self._update_timer.isActive():
            self._update_timer.start(16)  # ~60fps

    def _deferred_update(self):
        """Deferred update for performance - keeps viewport at silky 60fps during active stroke."""
        self.update()
        if not self._painting and not self._dragging_sun:
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
