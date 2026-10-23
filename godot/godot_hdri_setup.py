"""
HDRI Maker — Godot Engine Setup Script Generator.
Generates GDScript for importing HDRIs into Godot Engine 4.x projects.
"""


def generate_godot_import_script(hdri_path: str, output_path: str,
                                  sun_azimuth: float = 0.25,
                                  sun_elevation: float = 0.25,
                                  sun_intensity: float = 10.0,
                                  sun_color: tuple = (1.0, 0.95, 0.85),
                                  exposure: float = 1.0):
    """
    Generate a Godot 4.x GDScript that sets up HDRI environment.

    The generated script creates:
      - WorldEnvironment node with PanoramaSky
      - DirectionalLight3D matching the HDRI sun position
      - Configures environment settings

    Args:
        hdri_path: Path to the .hdr/.exr file
        output_path: Where to save the generated .gd script
        sun_azimuth: Sun horizontal position (0-1)
        sun_elevation: Sun vertical position (0-1, 0=zenith)
        sun_intensity: Sun brightness
        sun_color: Sun RGB color tuple
        exposure: Exposure compensation
    """
    import os
    import math

    # Convert to Godot rotation (degrees)
    sun_yaw = sun_azimuth * 360.0
    sun_pitch = -(90.0 - sun_elevation * 180.0)

    hdri_escaped = hdri_path.replace('\\', '/')

    script = f'''@tool
extends EditorScript
## HDRI Maker — Godot 4.x Environment Setup
##
## Auto-generated script to configure HDRI environment lighting.
##
## Usage:
##   1. Copy this script and your .hdr file into your Godot project
##   2. Open Script Editor, load this script
##   3. Run via Script > Run (Ctrl+Shift+X)
##
## Compatible with: Godot 4.0+

const HDRI_PATH = "{hdri_escaped}"

func _run() -> void:
    var scene_root = get_editor_interface().get_edited_scene_root()
    if scene_root == null:
        printerr("No scene open. Please open a scene first.")
        return

    print("[HDRI Maker] Setting up environment...")

    # Load HDRI texture
    var hdri_texture: Texture2D
    if ResourceLoader.exists(HDRI_PATH):
        hdri_texture = load(HDRI_PATH)
    else:
        # Try loading from filesystem
        var image = Image.new()
        var err = image.load(HDRI_PATH)
        if err != OK:
            printerr("Failed to load HDRI: " + HDRI_PATH)
            return
        hdri_texture = ImageTexture.create_from_image(image)

    # =============================================
    #  Create WorldEnvironment
    # =============================================
    var world_env: WorldEnvironment
    for child in scene_root.get_children():
        if child is WorldEnvironment:
            world_env = child
            break

    if world_env == null:
        world_env = WorldEnvironment.new()
        world_env.name = "HDRIEnvironment"
        scene_root.add_child(world_env, true)
        world_env.owner = scene_root

    # Create Environment resource
    var env = Environment.new()

    # Background: Sky
    env.background_mode = Environment.BG_SKY
    env.background_energy_multiplier = {exposure:.2f}

    # Create Sky with PanoramaSkyMaterial
    var sky = Sky.new()
    var sky_material = PanoramaSkyMaterial.new()
    sky_material.panorama = hdri_texture
    sky.sky_material = sky_material
    sky.process_mode = Sky.PROCESS_MODE_QUALITY

    env.sky = sky

    # Ambient light from sky
    env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
    env.ambient_light_energy = 1.0

    # Tonemap
    env.tonemap_mode = Environment.TONE_MAP_ACES
    env.tonemap_exposure = {exposure:.2f}

    # SSAO
    env.ssao_enabled = true

    # SSR
    env.ssr_enabled = true

    world_env.environment = env
    print("[HDRI Maker] WorldEnvironment configured")

    # =============================================
    #  Create DirectionalLight3D (Sun)
    # =============================================
    var sun_light: DirectionalLight3D
    for child in scene_root.get_children():
        if child is DirectionalLight3D:
            sun_light = child
            break

    if sun_light == null:
        sun_light = DirectionalLight3D.new()
        sun_light.name = "HDRISunLight"
        scene_root.add_child(sun_light, true)
        sun_light.owner = scene_root

    # Set rotation to match HDRI sun position
    sun_light.rotation_degrees = Vector3({sun_pitch:.2f}, {sun_yaw:.2f}, 0.0)

    # Light properties
    sun_light.light_energy = {sun_intensity:.2f}
    sun_light.light_color = Color({sun_color[0]:.3f}, {sun_color[1]:.3f}, {sun_color[2]:.3f})
    sun_light.light_temperature_enabled = true
    sun_light.shadow_enabled = true
    sun_light.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS

    print("[HDRI Maker] DirectionalLight3D configured")
    print("[HDRI Maker] === Environment setup complete! ===")
'''

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(script)

    print(f"[Exporter] Saved Godot script: {output_path}")


def generate_godot_scene(hdri_path: str, output_path: str,
                          sun_azimuth: float = 0.25,
                          sun_elevation: float = 0.25,
                          sun_intensity: float = 10.0,
                          sun_color: tuple = (1.0, 0.95, 0.85),
                          exposure: float = 1.0):
    """
    Generate a Godot 4.x .tscn scene file with HDRI environment setup.
    Can be directly inherited or instanced in a Godot project.
    """
    import os
    import math

    sun_yaw = sun_azimuth * 360.0
    sun_pitch = -(90.0 - sun_elevation * 180.0)

    hdri_escaped = hdri_path.replace('\\', '/')

    tscn = f'''[gd_scene load_steps=4 format=3]

[sub_resource type="PanoramaSkyMaterial" id="PanoramaSkyMaterial_hdri"]
; NOTE: Replace this with your actual HDRI texture resource path
; panorama = ExtResource("hdri_texture")

[sub_resource type="Sky" id="Sky_hdri"]
sky_material = SubResource("PanoramaSkyMaterial_hdri")

[sub_resource type="Environment" id="Environment_hdri"]
background_mode = 2
sky = SubResource("Sky_hdri")
ambient_light_source = 3
tonemap_mode = 3
tonemap_exposure = {exposure:.2f}
ssao_enabled = true

[node name="HDRIEnvironmentScene" type="Node3D"]

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_hdri")

[node name="HDRISunLight" type="DirectionalLight3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 10, 0)
rotation_degrees = Vector3({sun_pitch:.2f}, {sun_yaw:.2f}, 0)
light_color = Color({sun_color[0]:.3f}, {sun_color[1]:.3f}, {sun_color[2]:.3f}, 1)
light_energy = {sun_intensity:.2f}
shadow_enabled = true
'''

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(tscn)

    print(f"[Exporter] Saved Godot scene: {output_path}")
