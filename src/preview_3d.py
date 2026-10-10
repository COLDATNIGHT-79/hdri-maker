"""
3D Preview Widget for HDRI Maker.
Renders a sample 3D object (sphere) with the current HDRI as environment lighting.
Uses OpenGL for real-time rendering with environment mapping.
"""

import numpy as np
import math
import os
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPixmap, QMouseEvent, QWheelEvent

from src.hdri_engine import HDRIProject


class Preview3DWidget(QWidget):
    """
    3D preview widget that shows a sphere rendered with the current HDRI
    environment. Uses software rendering for maximum compatibility
    (no OpenGL dependency issues).
    """

    def __init__(self, project: HDRIProject, parent=None):
        super().__init__(parent)
        self.project = project

        # Camera/view state
        self._rot_x = 0.0    # Rotation around X axis
        self._rot_y = 0.0    # Rotation around Y axis
        self._zoom = 2.5     # Camera distance
        self._dragging = False
        self._last_mouse_pos = None

        # Render settings
        self._sphere_segments = 64
        self._render_size = 256  # Internal render resolution
        self._render_buffer = None
        self._needs_render = True

        # Material mode
        self._material_mode = 0  # 0=Mirror, 1=Diffuse, 2=Glossy

        # Timer for deferred rendering
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render)

        self.setMinimumSize(200, 200)
        self.setMouseTracking(True)

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls bar
        controls = QHBoxLayout()
        controls.setSpacing(4)

        material_label = QLabel("Material:")
        material_label.setStyleSheet("color: #aaa; font-size: 10px;")
        controls.addWidget(material_label)

        self.material_combo = QComboBox()
        self.material_combo.addItems(["Mirror", "Diffuse", "Glossy"])
        self.material_combo.setFixedHeight(22)
        self.material_combo.setStyleSheet("""
            QComboBox {
                background: #3a3a3a; color: #ddd; border: 1px solid #555;
                border-radius: 3px; padding: 1px 4px; font-size: 10px;
            }
        """)
        self.material_combo.currentIndexChanged.connect(self._on_material_changed)
        controls.addWidget(self.material_combo)

        controls.addStretch()

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedSize(50, 22)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; border: 1px solid #555;
                border-radius: 3px; color: #ddd; font-size: 10px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        reset_btn.clicked.connect(self._reset_view)
        controls.addWidget(reset_btn)

        layout.addLayout(controls)

        # Render area
        self._render_label = QLabel()
        self._render_label.setAlignment(Qt.AlignCenter)
        self._render_label.setStyleSheet("background: #1a1a1a; border: 1px solid #333; border-radius: 4px;")
        self._render_label.setMinimumSize(200, 200)
        layout.addWidget(self._render_label, 1)

    # ================================================================
    #  VIEW CONTROLS
    # ================================================================

    def _reset_view(self):
        self._rot_x = 0.0
        self._rot_y = 0.0
        self._zoom = 2.5
        self.request_render()

    def _on_material_changed(self, index):
        self._material_mode = index
        self.request_render()

    def request_render(self):
        """Request a deferred render update."""
        self._needs_render = True
        if not self._render_timer.isActive():
            self._render_timer.start(50)

    # ================================================================
    #  MOUSE INTERACTION
    # ================================================================

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and self._last_mouse_pos:
            dx = event.pos().x() - self._last_mouse_pos.x()
            dy = event.pos().y() - self._last_mouse_pos.y()
            self._rot_y += dx * 0.5
            self._rot_x += dy * 0.5
            self._rot_x = max(-90, min(90, self._rot_x))
            self._last_mouse_pos = event.pos()
            self.request_render()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom = max(1.0, self._zoom - 0.2)
        else:
            self._zoom = min(10.0, self._zoom + 0.2)
        self.request_render()

    # ================================================================
    #  SOFTWARE RENDERER
    # ================================================================

    def _render(self):
        """Software-render the sphere with environment mapping."""
        size = self._render_size
        buffer = np.zeros((size, size, 3), dtype=np.uint8)

        # Get HDRI environment map
        composite = self.project.get_composite()

        # Camera setup
        aspect = 1.0
        fov = 45.0
        cam_dist = self._zoom
        rot_x_rad = math.radians(self._rot_x)
        rot_y_rad = math.radians(self._rot_y)

        # Sphere properties
        sphere_radius = 0.8
        sphere_center = np.array([0.0, 0.0, 0.0])

        # Camera position (orbiting)
        cam_pos = np.array([
            cam_dist * math.sin(rot_y_rad) * math.cos(rot_x_rad),
            cam_dist * math.sin(rot_x_rad),
            cam_dist * math.cos(rot_y_rad) * math.cos(rot_x_rad)
        ])

        # Camera basis vectors
        forward = sphere_center - cam_pos
        forward = forward / np.linalg.norm(forward)
        world_up = np.array([0.0, 1.0, 0.0])
        right = np.cross(forward, world_up)
        if np.linalg.norm(right) < 0.001:
            right = np.array([1.0, 0.0, 0.0])
        right = right / np.linalg.norm(right)
        up = np.cross(right, forward)
        up = up / np.linalg.norm(up)

        half_fov = math.tan(math.radians(fov / 2))
        env_h, env_w = composite.shape[:2]

        for py in range(size):
            for px in range(size):
                # Generate ray
                ndc_x = (2.0 * px / size - 1.0) * half_fov * aspect
                ndc_y = (1.0 - 2.0 * py / size) * half_fov

                ray_dir = forward + right * ndc_x + up * ndc_y
                ray_dir = ray_dir / np.linalg.norm(ray_dir)

                # Ray-sphere intersection
                oc = cam_pos - sphere_center
                a = np.dot(ray_dir, ray_dir)
                b = 2.0 * np.dot(oc, ray_dir)
                c = np.dot(oc, oc) - sphere_radius * sphere_radius
                discriminant = b * b - 4 * a * c

                if discriminant >= 0:
                    t = (-b - math.sqrt(discriminant)) / (2 * a)
                    if t > 0:
                        hit_point = cam_pos + ray_dir * t
                        normal = (hit_point - sphere_center) / sphere_radius

                        if self._material_mode == 0:  # Mirror
                            reflect_dir = ray_dir - 2.0 * np.dot(ray_dir, normal) * normal
                            color = self._sample_env(composite, reflect_dir, env_w, env_h)
                        elif self._material_mode == 1:  # Diffuse
                            color = self._sample_diffuse(composite, normal, env_w, env_h)
                        else:  # Glossy
                            reflect_dir = ray_dir - 2.0 * np.dot(ray_dir, normal) * normal
                            mirror_color = self._sample_env(composite, reflect_dir, env_w, env_h)
                            diffuse_color = self._sample_diffuse(composite, normal, env_w, env_h)
                            color = mirror_color * 0.6 + diffuse_color * 0.4

                        # Tone map (ACES)
                        a_val, b_val, c_val, d_val, e_val = 2.51, 0.03, 2.43, 0.59, 0.14
                        mapped = np.clip(
                            (color * (a_val * color + b_val)) /
                            (color * (c_val * color + d_val) + e_val),
                            0, 1
                        )
                        # Gamma
                        mapped = np.power(mapped, 1.0 / 2.2)

                        buffer[py, px] = (mapped * 255).astype(np.uint8)
                    else:
                        # Background: sample environment directly
                        bg_color = self._sample_env(composite, ray_dir, env_w, env_h)
                        bg_mapped = np.clip(bg_color / (1.0 + bg_color), 0, 1)
                        bg_mapped = np.power(bg_mapped, 1.0 / 2.2)
                        buffer[py, px] = (bg_mapped * 255).astype(np.uint8)
                else:
                    # Background: sample environment
                    bg_color = self._sample_env(composite, ray_dir, env_w, env_h)
                    bg_mapped = np.clip(bg_color / (1.0 + bg_color), 0, 1)
                    bg_mapped = np.power(bg_mapped, 1.0 / 2.2)
                    buffer[py, px] = (bg_mapped * 255).astype(np.uint8)

        # Display the rendered image
        h, w = buffer.shape[:2]
        img = QImage(buffer.tobytes(), w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)

        # Scale to widget size
        label_size = self._render_label.size()
        scaled = pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._render_label.setPixmap(scaled)

        self._needs_render = False

    def _sample_env(self, env_map: np.ndarray, direction: np.ndarray,
                     env_w: int, env_h: int) -> np.ndarray:
        """Sample the environment map at a given direction."""
        # Convert direction to equirectangular UV
        theta = math.atan2(direction[2], direction[0])  # -pi to pi
        phi = math.acos(np.clip(direction[1], -1, 1))   # 0 to pi

        u = (theta / (2 * math.pi)) + 0.5  # 0 to 1
        v = phi / math.pi                    # 0 to 1

        # Sample the environment map
        ex = int(u * (env_w - 1)) % env_w
        ey = int(v * (env_h - 1)) % env_h

        return env_map[ey, ex, :3].copy()

    def _sample_diffuse(self, env_map: np.ndarray, normal: np.ndarray,
                         env_w: int, env_h: int) -> np.ndarray:
        """Simple diffuse lighting by sampling a few directions around the normal."""
        # Quick hemisphere sampling (low quality but fast)
        color = np.zeros(3, dtype=np.float32)
        samples = 12

        # Create basis from normal
        if abs(normal[1]) < 0.999:
            tangent = np.cross(np.array([0, 1, 0]), normal)
        else:
            tangent = np.cross(np.array([1, 0, 0]), normal)
        tangent = tangent / max(np.linalg.norm(tangent), 0.001)
        bitangent = np.cross(normal, tangent)

        for i in range(samples):
            angle = 2.0 * math.pi * i / samples
            elevation = 0.3

            sample_dir = (normal * math.cos(elevation) +
                          tangent * math.sin(elevation) * math.cos(angle) +
                          bitangent * math.sin(elevation) * math.sin(angle))
            sample_dir = sample_dir / max(np.linalg.norm(sample_dir), 0.001)

            ndotl = max(np.dot(normal, sample_dir), 0)
            color += self._sample_env(env_map, sample_dir, env_w, env_h) * ndotl

        # Add direct normal sample
        color += self._sample_env(env_map, normal, env_w, env_h) * 0.5

        return color / (samples * 0.3 + 0.5)
