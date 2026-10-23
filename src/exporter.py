"""
Exporter module for HDRI Maker.
Handles exporting HDRI projects to various formats:
- .hdr (Radiance RGBE format)
- .exr (OpenEXR format, if available)
- .png (Tone-mapped LDR for preview)
- .blend (Blender Python script for import)
- Cubemap (6-face layout for game engines)
- Unreal Engine (Python script + data asset)
- Godot Engine (GDScript + .tscn scene)

Export presets for one-click engine-specific export.
"""

import os
import struct
import math
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple


# ============================================================
#  HDR EXPORT
# ============================================================

def export_hdr(image_data: np.ndarray, filepath: str):
    """
    Export an HDR image in Radiance .hdr (RGBE) format.

    The RGBE format stores each pixel as 4 bytes: R, G, B mantissa + shared exponent.
    This is the most widely supported HDR format across tools.

    Args:
        image_data: Float32 numpy array, shape (H, W, 3) or (H, W, 4)
        filepath: Output .hdr file path
    """
    if image_data.shape[2] == 4:
        rgb = image_data[:, :, :3].copy()
    else:
        rgb = image_data.copy()

    h, w = rgb.shape[:2]

    # Convert float RGB to RGBE format
    def float_to_rgbe(r, g, b):
        """Convert float RGB to RGBE (4 bytes)."""
        v = max(r, g, b)
        if v < 1e-32:
            return (0, 0, 0, 0)
        import math
        mantissa, exponent = math.frexp(v)
        v = mantissa * 256.0 / v
        return (
            min(255, max(0, int(r * v))),
            min(255, max(0, int(g * v))),
            min(255, max(0, int(b * v))),
            exponent + 128
        )

    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    with open(filepath, 'wb') as f:
        # Write Radiance HDR header
        f.write(b'#?RADIANCE\n')
        f.write(b'# Created by HDRI Maker\n')
        f.write(b'FORMAT=32-bit_rle_rgbe\n')
        f.write(b'\n')
        f.write(f'-Y {h} +X {w}\n'.encode('ascii'))

        # Write pixel data (uncompressed scanlines)
        for y in range(h):
            scanline = bytearray()
            for x in range(w):
                r, g, b = float(rgb[y, x, 0]), float(rgb[y, x, 1]), float(rgb[y, x, 2])
                re, ge, be, e = float_to_rgbe(r, g, b)
                scanline.extend([re, ge, be, e])
            f.write(bytes(scanline))

    print(f"[Exporter] Saved HDR: {filepath} ({w}x{h})")


# ============================================================
#  EXR EXPORT
# ============================================================

def export_exr(image_data: np.ndarray, filepath: str):
    """
    Export an HDR image in OpenEXR format using imageio.
    Falls back to .hdr format if OpenEXR support is not available.
    """
    try:
        import imageio.v3 as iio
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

        if image_data.shape[2] == 4:
            rgb = image_data[:, :, :3]
        else:
            rgb = image_data

        iio.imwrite(filepath, rgb.astype(np.float32))
        print(f"[Exporter] Saved EXR: {filepath}")
    except Exception as e:
        print(f"[Exporter] EXR export failed ({e}), falling back to HDR format")
        hdr_path = filepath.rsplit('.', 1)[0] + '.hdr'
        export_hdr(image_data, hdr_path)


# ============================================================
#  PNG EXPORT
# ============================================================

def export_png(image_data: np.ndarray, filepath: str,
               exposure: float = 0.0, tone_map: str = 'aces'):
    """
    Export a tone-mapped PNG for preview purposes.
    """
    from PIL import Image

    exp_scale = 2.0 ** exposure
    rgb = image_data[:, :, :3] * exp_scale

    if tone_map == 'reinhard':
        mapped = rgb / (1.0 + rgb)
    else:  # ACES
        a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
        mapped = np.clip((rgb * (a * rgb + b)) / (rgb * (c * rgb + d) + e), 0, 1)

    # Apply simple sRGB gamma
    mapped = np.power(np.clip(mapped, 0, 1), 1.0 / 2.2)

    # Convert to uint8
    ldr = (mapped * 255).astype(np.uint8)

    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    img = Image.fromarray(ldr, 'RGB')
    img.save(filepath, 'PNG')
    print(f"[Exporter] Saved PNG: {filepath}")


# ============================================================
#  CUBEMAP EXPORT
# ============================================================

def _equirect_to_cube_face(equirect: np.ndarray, face: str, face_size: int) -> np.ndarray:
    """
    Convert equirectangular image to a single cubemap face.

    Args:
        equirect: Input equirectangular image (H, W, C), float32
        face: One of '+x', '-x', '+y', '-y', '+z', '-z'
        face_size: Output face size in pixels
    """
    h, w, c = equirect.shape

    # Create pixel grid for the face
    u = np.linspace(-1, 1, face_size, dtype=np.float32)
    v = np.linspace(-1, 1, face_size, dtype=np.float32)
    uu, vv = np.meshgrid(u, v)

    # Convert face UV to 3D direction
    if face == '+x':
        dx, dy, dz = np.ones_like(uu), -vv, -uu
    elif face == '-x':
        dx, dy, dz = -np.ones_like(uu), -vv, uu
    elif face == '+y':
        dx, dy, dz = uu, np.ones_like(uu), vv
    elif face == '-y':
        dx, dy, dz = uu, -np.ones_like(uu), -vv
    elif face == '+z':
        dx, dy, dz = uu, -vv, np.ones_like(uu)
    elif face == '-z':
        dx, dy, dz = -uu, -vv, -np.ones_like(uu)
    else:
        raise ValueError(f"Invalid face: {face}")

    # Normalize direction
    length = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
    dx /= length
    dy /= length
    dz /= length

    # Convert 3D direction to equirectangular UV
    theta = np.arctan2(dz, dx)  # -pi to pi
    phi = np.arccos(np.clip(dy, -1, 1))  # 0 to pi

    eq_u = (theta / (2 * np.pi) + 0.5) * (w - 1)
    eq_v = (phi / np.pi) * (h - 1)

    # Bilinear sampling
    eq_u = np.clip(eq_u, 0, w - 1)
    eq_v = np.clip(eq_v, 0, h - 1)

    u0 = np.floor(eq_u).astype(int)
    v0 = np.floor(eq_v).astype(int)
    u1 = np.minimum(u0 + 1, w - 1)
    v1 = np.minimum(v0 + 1, h - 1)

    fu = eq_u - u0.astype(np.float32)
    fv = eq_v - v0.astype(np.float32)
    fu = fu[..., np.newaxis]
    fv = fv[..., np.newaxis]

    result = (
        equirect[v0, u0] * (1 - fu) * (1 - fv) +
        equirect[v0, u1] * fu * (1 - fv) +
        equirect[v1, u0] * (1 - fu) * fv +
        equirect[v1, u1] * fu * fv
    )

    return result.astype(np.float32)


def export_cubemap(image_data: np.ndarray, output_dir: str, name: str = "hdri",
                    face_size: int = 1024, as_hdr: bool = False):
    """
    Export an equirectangular HDRI as 6 cubemap face images.

    Args:
        image_data: Float32 equirectangular image (H, W, 3 or 4)
        output_dir: Output directory
        name: Base name for output files
        face_size: Size of each cubemap face in pixels
        as_hdr: If True, save as .hdr; otherwise save as .png (tone-mapped)

    Returns:
        List of exported file paths
    """
    from PIL import Image

    os.makedirs(output_dir, exist_ok=True)
    rgb = image_data[:, :, :3] if image_data.shape[2] == 4 else image_data

    faces = ['+x', '-x', '+y', '-y', '+z', '-z']
    face_names = ['px', 'nx', 'py', 'ny', 'pz', 'nz']

    exported = []

    for face, fname in zip(faces, face_names):
        face_data = _equirect_to_cube_face(rgb, face, face_size)

        if as_hdr:
            filepath = os.path.join(output_dir, f"{name}_{fname}.hdr")
            # Add alpha for HDR export
            face_rgba = np.concatenate([
                face_data,
                np.ones((*face_data.shape[:2], 1), dtype=np.float32)
            ], axis=2)
            export_hdr(face_rgba, filepath)
        else:
            filepath = os.path.join(output_dir, f"{name}_{fname}.png")
            # Tone map for PNG
            a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
            mapped = np.clip(
                (face_data * (a * face_data + b)) /
                (face_data * (c * face_data + d) + e), 0, 1
            )
            mapped = np.power(mapped, 1.0 / 2.2)
            ldr = (mapped * 255).astype(np.uint8)
            img = Image.fromarray(ldr, 'RGB')
            img.save(filepath, 'PNG')

        exported.append(filepath)

    # Also create a cross layout cubemap
    cross_path = os.path.join(output_dir, f"{name}_cubemap_cross.png")
    _create_cubemap_cross(rgb, face_size, cross_path)
    exported.append(cross_path)

    print(f"[Exporter] Saved cubemap ({len(exported)} files) to {output_dir}")
    return exported


def _create_cubemap_cross(equirect: np.ndarray, face_size: int, filepath: str):
    """Create a cubemap cross layout image."""
    from PIL import Image

    # Cross layout: 4 wide x 3 tall
    cross_w = face_size * 4
    cross_h = face_size * 3
    cross = np.zeros((cross_h, cross_w, 3), dtype=np.float32)

    # Layout:
    #        [+Y]
    # [-X] [+Z] [+X] [-Z]
    #        [-Y]
    layout = {
        '+y': (1, 0),
        '-x': (0, 1),
        '+z': (1, 1),
        '+x': (2, 1),
        '-z': (3, 1),
        '-y': (1, 2),
    }

    for face, (col, row) in layout.items():
        face_data = _equirect_to_cube_face(equirect, face, face_size)
        y0 = row * face_size
        x0 = col * face_size
        cross[y0:y0 + face_size, x0:x0 + face_size] = face_data[:, :, :3]

    # Tone map
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    mapped = np.clip(
        (cross * (a * cross + b)) / (cross * (c * cross + d) + e), 0, 1
    )
    mapped = np.power(mapped, 1.0 / 2.2)
    ldr = (mapped * 255).astype(np.uint8)

    img = Image.fromarray(ldr, 'RGB')
    img.save(filepath, 'PNG')


# ============================================================
#  BLENDER EXPORT
# ============================================================

def export_blender_script(hdri_filepath: str, script_filepath: str,
                           sun_azimuth: float = 0.25, sun_elevation: float = 0.25,
                           sun_intensity: float = 10.0,
                           sun_color: tuple = (1.0, 0.95, 0.85)):
    """
    Generate a Blender Python script that imports the HDRI as world environment.
    Enhanced: also creates a Sun lamp matching the HDRI sun position.
    """
    hdri_path_escaped = hdri_filepath.replace('\\', '/')

    # Convert sun position to Blender's coordinate system
    sun_yaw = sun_azimuth * 360.0
    sun_pitch = 90.0 - sun_elevation * 180.0

    script = f'''"""
HDRI Maker - Blender Import Script
Auto-generated script to set up HDRI environment lighting.
Run this in Blender's scripting tab or via File > Run Script.

Includes:
  - HDRI world environment with mapping controls
  - Sun lamp matching the HDRI sun position
  - EEVEE/Cycles settings
"""

import bpy
import os
import math


def setup_hdri_environment(hdri_path):
    """Set up the HDRI as world environment in Blender."""

    # Ensure the file exists
    if not os.path.isfile(hdri_path):
        print(f"Error: HDRI file not found: {{hdri_path}}")
        return False

    # Get or create world
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("HDRI World")
        bpy.context.scene.world = world

    # Enable nodes
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    # Clear existing nodes
    nodes.clear()

    # Create nodes
    # Background node
    bg_node = nodes.new(type='ShaderNodeBackground')
    bg_node.location = (0, 0)
    bg_node.inputs['Strength'].default_value = 1.0

    # Environment Texture node
    env_node = nodes.new(type='ShaderNodeTexEnvironment')
    env_node.location = (-300, 0)
    env_node.image = bpy.data.images.load(hdri_path, check_existing=True)

    # Texture Coordinate node
    coord_node = nodes.new(type='ShaderNodeTexCoord')
    coord_node.location = (-700, 0)

    # Mapping node (for rotation control)
    mapping_node = nodes.new(type='ShaderNodeMapping')
    mapping_node.location = (-500, 0)

    # World Output node
    output_node = nodes.new(type='ShaderNodeOutputWorld')
    output_node.location = (200, 0)

    # Connect nodes
    links.new(coord_node.outputs['Generated'], mapping_node.inputs['Vector'])
    links.new(mapping_node.outputs['Vector'], env_node.inputs['Vector'])
    links.new(env_node.outputs['Color'], bg_node.inputs['Color'])
    links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])

    print(f"HDRI environment set up: {{hdri_path}}")
    return True


def setup_sun_lamp():
    """Create a Sun lamp matching the HDRI sun position."""

    # Check for existing sun lamp
    sun_obj = None
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT' and obj.data.type == 'SUN':
            sun_obj = obj
            break

    if sun_obj is None:
        # Create new sun lamp
        sun_data = bpy.data.lights.new(name="HDRI Sun", type='SUN')
        sun_obj = bpy.data.objects.new("HDRI Sun", sun_data)
        bpy.context.collection.objects.link(sun_obj)

    # Set sun properties
    sun_obj.data.energy = {sun_intensity:.2f}
    sun_obj.data.color = ({sun_color[0]:.3f}, {sun_color[1]:.3f}, {sun_color[2]:.3f})

    # Set rotation (convert azimuth/elevation to Euler)
    sun_yaw_rad = math.radians({sun_yaw:.2f})
    sun_pitch_rad = math.radians({sun_pitch:.2f})
    sun_obj.rotation_euler = (sun_pitch_rad, 0, sun_yaw_rad)

    print(f"Sun lamp configured: intensity={sun_intensity:.1f}, yaw={sun_yaw:.1f}°, pitch={sun_pitch:.1f}°")


def configure_render_settings():
    """Configure render settings for best HDRI results."""
    scene = bpy.context.scene

    # Try Cycles first
    if hasattr(scene, 'cycles'):
        scene.render.engine = 'CYCLES'
        scene.cycles.samples = 128
        scene.cycles.use_denoising = True
    else:
        scene.render.engine = 'BLENDER_EEVEE'

    # Set viewport shading to rendered/material
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'

    print("Render settings configured")


# Run the setup
hdri_path = r"{hdri_path_escaped}"
if setup_hdri_environment(hdri_path):
    setup_sun_lamp()
    configure_render_settings()
    print("\\n=== HDRI Maker: Blender setup complete! ===")
'''

    os.makedirs(os.path.dirname(script_filepath) or '.', exist_ok=True)
    with open(script_filepath, 'w') as f:
        f.write(script)

    print(f"[Exporter] Saved Blender script: {script_filepath}")


# ============================================================
#  UNREAL ENGINE EXPORT
# ============================================================

def export_unreal(image_data: np.ndarray, output_dir: str, name: str = "hdri_output",
                   sun_azimuth: float = 0.25, sun_elevation: float = 0.25,
                   sun_intensity: float = 10.0, sun_color: tuple = (1.0, 0.95, 0.85),
                   exposure: float = 1.0):
    """Export HDRI with Unreal Engine import script."""
    os.makedirs(output_dir, exist_ok=True)

    # Export HDR file
    hdr_path = os.path.join(output_dir, f"{name}.hdr")
    export_hdr(image_data, hdr_path)

    # Generate Unreal import script
    try:
        from unreal.unreal_hdri_setup import generate_unreal_import_script, generate_unreal_data_asset

        script_path = os.path.join(output_dir, f"{name}_unreal_import.py")
        generate_unreal_import_script(
            hdr_path, script_path,
            sun_azimuth, sun_elevation, sun_intensity, sun_color, exposure
        )

        data_path = os.path.join(output_dir, f"{name}_unreal_data.json")
        generate_unreal_data_asset(
            hdr_path, data_path,
            sun_azimuth, sun_elevation, sun_intensity
        )

        return [hdr_path, script_path, data_path]
    except Exception as e:
        print(f"[Exporter] Unreal script generation failed: {e}")
        return [hdr_path]


# ============================================================
#  GODOT ENGINE EXPORT
# ============================================================

def export_godot(image_data: np.ndarray, output_dir: str, name: str = "hdri_output",
                  sun_azimuth: float = 0.25, sun_elevation: float = 0.25,
                  sun_intensity: float = 10.0, sun_color: tuple = (1.0, 0.95, 0.85),
                  exposure: float = 1.0):
    """Export HDRI with Godot Engine import script."""
    os.makedirs(output_dir, exist_ok=True)

    # Export HDR file
    hdr_path = os.path.join(output_dir, f"{name}.hdr")
    export_hdr(image_data, hdr_path)

    try:
        from godot.godot_hdri_setup import generate_godot_import_script, generate_godot_scene

        script_path = os.path.join(output_dir, f"{name}_godot_setup.gd")
        generate_godot_import_script(
            hdr_path, script_path,
            sun_azimuth, sun_elevation, sun_intensity, sun_color, exposure
        )

        scene_path = os.path.join(output_dir, f"{name}_environment.tscn")
        generate_godot_scene(
            hdr_path, scene_path,
            sun_azimuth, sun_elevation, sun_intensity, sun_color, exposure
        )

        return [hdr_path, script_path, scene_path]
    except Exception as e:
        print(f"[Exporter] Godot script generation failed: {e}")
        return [hdr_path]


# ============================================================
#  PROJECT EXPORT (MULTI-FORMAT)
# ============================================================

def export_project(image_data: np.ndarray, output_dir: str, name: str = "hdri_output",
                    formats: list = None, sun_data: dict = None):
    """
    Export the HDRI in multiple formats at once.

    Args:
        image_data: Float32 numpy array (HDR, RGBA)
        output_dir: Output directory
        name: Base filename without extension
        formats: List of formats to export
        sun_data: Dict with sun position/color data for engine scripts
    """
    if formats is None:
        formats = ['hdr', 'png', 'blender']

    if sun_data is None:
        sun_data = {
            'azimuth': 0.25,
            'elevation': 0.25,
            'intensity': 10.0,
            'color': (1.0, 0.95, 0.85),
            'exposure': 1.0,
        }

    os.makedirs(output_dir, exist_ok=True)

    exported = []
    hdr_path = None

    if 'hdr' in formats:
        hdr_path = os.path.join(output_dir, f"{name}.hdr")
        export_hdr(image_data, hdr_path)
        exported.append(hdr_path)

    if 'exr' in formats:
        exr_path = os.path.join(output_dir, f"{name}.exr")
        export_exr(image_data, exr_path)
        exported.append(exr_path)

    if 'png' in formats:
        png_path = os.path.join(output_dir, f"{name}.png")
        export_png(image_data, png_path)
        exported.append(png_path)

    if 'cubemap' in formats:
        cube_dir = os.path.join(output_dir, f"{name}_cubemap")
        cube_files = export_cubemap(image_data, cube_dir, name)
        exported.extend(cube_files)

    if 'blender' in formats and hdr_path:
        script_path = os.path.join(output_dir, f"{name}_blender_import.py")
        export_blender_script(
            hdr_path, script_path,
            sun_data['azimuth'], sun_data['elevation'],
            sun_data['intensity'], sun_data['color']
        )
        exported.append(script_path)

    if 'unreal' in formats:
        unreal_files = export_unreal(
            image_data, output_dir, name,
            sun_data['azimuth'], sun_data['elevation'],
            sun_data['intensity'], sun_data['color'],
            sun_data.get('exposure', 1.0)
        )
        exported.extend(unreal_files)

    if 'godot' in formats:
        godot_files = export_godot(
            image_data, output_dir, name,
            sun_data['azimuth'], sun_data['elevation'],
            sun_data['intensity'], sun_data['color'],
            sun_data.get('exposure', 1.0)
        )
        exported.extend(godot_files)

    if 'unity' in formats:
        cs_source = Path(__file__).parent.parent / "csharp" / "HDRIImporter.cs"
        if cs_source.exists():
            import shutil
            cs_dest = os.path.join(output_dir, "HDRIImporter.cs")
            shutil.copy2(str(cs_source), cs_dest)
            exported.append(cs_dest)

    return exported


# ============================================================
#  EXPORT PRESETS
# ============================================================

EXPORT_PRESETS = {
    "blender": {
        "name": "Export for Blender",
        "formats": ["hdr", "blender"],
        "description": "HDR file + Blender Python import script with sun lamp",
    },
    "unity": {
        "name": "Export for Unity",
        "formats": ["hdr", "cubemap", "unity"],
        "description": "HDR file + cubemap faces + Unity C# Importer script",
    },
    "unreal": {
        "name": "Export for Unreal Engine",
        "formats": ["hdr", "unreal"],
        "description": "HDR file + Unreal Python setup script + data asset",
    },
    "godot": {
        "name": "Export for Godot",
        "formats": ["hdr", "godot"],
        "description": "HDR file + GDScript + .tscn scene file",
    },
    "all_engines": {
        "name": "Export for All Engines",
        "formats": ["hdr", "exr", "png", "cubemap", "blender", "unity", "unreal", "godot"],
        "description": "Complete export for Blender, Unity, Unreal, and Godot",
    },
    "web": {
        "name": "Export for Web / Preview",
        "formats": ["png", "cubemap"],
        "description": "Tone-mapped PNG + cubemap faces for web/preview",
    },
}


def export_with_preset(image_data: np.ndarray, output_dir: str,
                        preset_name: str, name: str = "hdri_output",
                        sun_data: dict = None) -> List[str]:
    """Export using a named preset."""
    preset = EXPORT_PRESETS.get(preset_name)
    if not preset:
        raise ValueError(f"Unknown export preset: {preset_name}")

    return export_project(image_data, output_dir, name,
                           preset['formats'], sun_data)
