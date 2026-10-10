"""
Exporter module for HDRI Maker.
Handles exporting HDRI projects to various formats:
- .hdr (Radiance RGBE format)
- .exr (OpenEXR format, if available)
- .png (Tone-mapped LDR for preview)
- .blend (Blender Python script for import)
"""

import os
import struct
import numpy as np
from pathlib import Path
from typing import Optional


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


def export_exr(image_data: np.ndarray, filepath: str):
    """
    Export an HDR image in OpenEXR format using imageio.
    Falls back to .hdr format if OpenEXR support is not available.
    
    Args:
        image_data: Float32 numpy array, shape (H, W, 3) or (H, W, 4)
        filepath: Output .exr file path
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


def export_png(image_data: np.ndarray, filepath: str,
               exposure: float = 0.0, tone_map: str = 'aces'):
    """
    Export a tone-mapped PNG for preview purposes.
    
    Args:
        image_data: Float32 numpy array (HDR)
        filepath: Output .png file path
        exposure: Exposure adjustment in stops
        tone_map: Tone mapping operator ('reinhard' or 'aces')
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


def export_blender_script(hdri_filepath: str, script_filepath: str):
    """
    Generate a Blender Python script that imports the HDRI as world environment.
    
    Usage in Blender: File > Run Script, or paste into scripting tab.
    
    Args:
        hdri_filepath: Path to the .hdr/.exr file (will be used in the script)
        script_filepath: Output .py file path
    """
    # Convert to forward slashes for Blender compatibility
    hdri_path_escaped = hdri_filepath.replace('\\', '/')

    script = f'''"""
HDRI Maker - Blender Import Script
Auto-generated script to set up HDRI environment lighting.
Run this in Blender's scripting tab or via File > Run Script.
"""

import bpy
import os

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
    
    # Set viewport shading to rendered
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'
    
    print(f"HDRI environment set up successfully: {{hdri_path}}")
    return True


# Run the setup
hdri_path = r"{hdri_path_escaped}"
setup_hdri_environment(hdri_path)
'''

    os.makedirs(os.path.dirname(script_filepath) or '.', exist_ok=True)
    with open(script_filepath, 'w') as f:
        f.write(script)

    print(f"[Exporter] Saved Blender script: {script_filepath}")


def export_project(image_data: np.ndarray, output_dir: str, name: str = "hdri_output",
                    formats: list = None):
    """
    Export the HDRI in multiple formats at once.
    
    Args:
        image_data: Float32 numpy array (HDR, RGBA)
        output_dir: Output directory
        name: Base filename without extension
        formats: List of formats to export ('hdr', 'exr', 'png', 'blender')
    """
    if formats is None:
        formats = ['hdr', 'png', 'blender']

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

    if 'blender' in formats and hdr_path:
        script_path = os.path.join(output_dir, f"{name}_blender_import.py")
        export_blender_script(hdr_path, script_path)
        exported.append(script_path)

    return exported
