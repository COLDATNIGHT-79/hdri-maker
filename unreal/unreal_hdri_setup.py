"""
HDRI Maker — Unreal Engine Setup Script Generator.
Generates an Unreal Editor Utility script (Python) for importing HDRIs
into Unreal Engine projects.

This module creates a .py script that can be run inside Unreal's Python console
or as an Editor Utility script to:
  - Import the HDRI texture
  - Create a Sky Sphere / SkyAtmosphere setup
  - Configure DirectionalLight to match the HDRI sun position
  - Set up environment lighting
"""


def generate_unreal_import_script(hdri_path: str, output_path: str,
                                   sun_azimuth: float = 0.25,
                                   sun_elevation: float = 0.25,
                                   sun_intensity: float = 10.0,
                                   sun_color: tuple = (1.0, 0.95, 0.85),
                                   exposure: float = 1.0):
    """
    Generate an Unreal Engine Python import script.

    Args:
        hdri_path: Path to the .hdr/.exr file
        output_path: Where to save the generated .py script
        sun_azimuth: Sun horizontal position (0-1, normalized)
        sun_elevation: Sun vertical position (0-1, 0=zenith)
        sun_intensity: Sun brightness
        sun_color: Sun RGB color
        exposure: Exposure compensation
    """
    import os
    import math

    # Convert sun position to Unreal's coordinate system
    # Unreal uses a left-handed coordinate system with Z up
    sun_yaw = sun_azimuth * 360.0  # degrees
    # Convert elevation (0=top, 0.5=horizon) to pitch angle
    sun_pitch = -(90.0 - sun_elevation * 180.0)

    hdri_escaped = hdri_path.replace('\\', '/')

    script = f'''"""
HDRI Maker — Unreal Engine Import Script
Auto-generated script to set up HDRI environment lighting in Unreal Engine.

Prerequisites:
  - Enable the "Editor Scripting Utilities" and "Python Editor Script Plugin" in your project
  - Run this script via: Edit > Run Python Script, or the Python console

Compatible with: Unreal Engine 4.27+, Unreal Engine 5.x
"""

import unreal
import os
import math


def setup_hdri_environment():
    """Import HDRI and configure environment lighting."""

    hdri_path = r"{hdri_escaped}"

    if not os.path.isfile(hdri_path):
        unreal.log_error(f"HDRI file not found: {{hdri_path}}")
        return False

    # ============================================
    #  Step 1: Import HDRI texture
    # ============================================
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    import_data = unreal.AutomatedAssetImportData()

    # Determine destination path in Content Browser
    dest_path = "/Game/HDRIMaker/Environments"
    filename = os.path.splitext(os.path.basename(hdri_path))[0]
    texture_path = f"{{dest_path}}/{{filename}}"

    import_data.set_editor_property("destination_path", dest_path)
    import_data.set_editor_property("filenames", [hdri_path])
    import_data.set_editor_property("replace_existing", True)

    imported = asset_tools.import_assets_automated(import_data)

    if not imported:
        unreal.log_error("Failed to import HDRI texture")
        return False

    texture_asset = imported[0]
    unreal.log(f"Imported HDRI: {{texture_path}}")

    # Configure texture settings for HDR
    if isinstance(texture_asset, unreal.Texture2D):
        texture_asset.set_editor_property("compression_settings",
                                           unreal.TextureCompressionSettings.TC_HDR)
        texture_asset.set_editor_property("srgb", False)

    # ============================================
    #  Step 2: Find or create Directional Light
    # ============================================
    editor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.EditorLevelLibrary.get_editor_world()

    # Find existing directional light or spawn one
    directional_light = None
    all_actors = unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.DirectionalLight
    )

    if all_actors:
        directional_light = all_actors[0]
        unreal.log("Found existing DirectionalLight, updating...")
    else:
        directional_light = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.DirectionalLight,
            unreal.Vector(0, 0, 500)
        )
        unreal.log("Spawned new DirectionalLight")

    if directional_light:
        # Set rotation to match HDRI sun position
        rotation = unreal.Rotator({sun_pitch:.2f}, {sun_yaw:.2f}, 0.0)
        directional_light.set_actor_rotation(rotation, False)

        # Set light properties
        light_comp = directional_light.get_component_by_class(unreal.DirectionalLightComponent)
        if light_comp:
            light_comp.set_editor_property("intensity", {sun_intensity * 10:.1f})
            light_comp.set_editor_property("light_color",
                unreal.Color(
                    r=int({sun_color[0]:.3f} * 255),
                    g=int({sun_color[1]:.3f} * 255),
                    b=int({sun_color[2]:.3f} * 255),
                    a=255
                )
            )
            light_comp.set_editor_property("use_temperature", True)

    # ============================================
    #  Step 3: Find or create SkyLight
    # ============================================
    sky_lights = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SkyLight)

    if sky_lights:
        sky_light = sky_lights[0]
    else:
        sky_light = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SkyLight,
            unreal.Vector(0, 0, 300)
        )

    if sky_light:
        sl_comp = sky_light.get_component_by_class(unreal.SkyLightComponent)
        if sl_comp:
            sl_comp.set_editor_property("source_type",
                                         unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
            # Set cubemap texture (engine will convert equirect to cubemap)
            sl_comp.set_editor_property("cubemap", texture_asset)
            sl_comp.set_editor_property("intensity", {exposure:.2f})
            sl_comp.recapture_sky()

    # ============================================
    #  Step 4: Configure Post-Process Volume (optional)
    # ============================================
    pp_volumes = unreal.GameplayStatics.get_all_actors_of_class(
        world, unreal.PostProcessVolume
    )
    if pp_volumes:
        pp = pp_volumes[0]
        settings = pp.get_editor_property("settings")
        settings.set_editor_property("auto_exposure_bias", {exposure:.2f})

    unreal.log("=== HDRI Maker: Environment setup complete! ===")
    return True


# Run the setup
setup_hdri_environment()
'''

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(script)

    print(f"[Exporter] Saved Unreal Engine script: {output_path}")


def generate_unreal_data_asset(hdri_path: str, output_path: str,
                                sun_azimuth: float = 0.25,
                                sun_elevation: float = 0.25,
                                sun_intensity: float = 10.0):
    """
    Generate a JSON data file with HDRI metadata for Unreal Engine.
    Can be imported as a DataTable or read by Blueprints.
    """
    import json
    import os

    data = {
        "HDRIPath": hdri_path.replace('\\', '/'),
        "SunAzimuth": sun_azimuth * 360.0,
        "SunElevation": 90.0 - sun_elevation * 180.0,
        "SunIntensity": sun_intensity,
        "Metadata": {
            "Generator": "HDRI Maker",
            "Version": "2.0"
        }
    }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"[Exporter] Saved Unreal data asset: {output_path}")
