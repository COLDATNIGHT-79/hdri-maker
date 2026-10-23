# HDRI Maker — Substance Painter for Lighting & HDR Environments

A powerful multi-language desktop suite (Python + C++ + C#) for creating, painting, sculpting, and composing High Dynamic Range Images (HDRIs) and skyboxes for **Blender**, **Unreal Engine**, **Unity**, and **Godot**.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![PySide6](https://img.shields.io/badge/PySide6-Qt_Dark_Theme-brightgreen)
![C++](https://img.shields.io/badge/C++-17-orange)
![C#](https://img.shields.io/badge/C%23-.NET_Standard_2.1-green)

---

## 🌟 Key Features

### ☀ Interactive Sun & Light Source System
- **Interactive canvas placement**: Click and drag directly on the 360° equirectangular canvas to position suns and light sources.
- **Physical Color Temperature**: Kelvin temperature slider (1800K to 12000K) with realistic blackbody radiation colors.
- **Solar disc & halo controls**: Configurable disc size, limb darkening, halo radius, halo intensity, and exponential falloff.
- **Starburst / Flare rays**: Procedural multi-blade starburst flare effect.
- **Directional light metadata**: Sun azimuth, elevation, intensity, and color automatically synchronize to exported 3D engine scripts.

### ☁ Procedural Cloud Painter
- **Procedural cloud brush**: Paint volumetric-looking clouds directly onto any layer or dedicated cloud layer.
- **Cloud presets**:
  - `Cumulus`: Fluffy, bright, sunny-day clouds
  - `Cirrus`: High-altitude wispy streaks
  - `Stratus`: Low, overcast blanket clouds
  - `Wispy`: Ethereal, delicate cloud tendrils
  - `Storm`: Dense, dramatic, ominous clouds
  - `Sunset`: Warm, golden rim-lit clouds
- **Sun-aware illumination**: Clouds automatically illuminate from the project's sun direction with front-lit, back-lit, and rim-lit scattering.
- **Full sky generation**: One-click generation of procedural multi-octave cloud fields.

### 🌲 Element Stamps & Silhouette Library
- **Built-in stamp categories**:
  - `Trees`: Oak, Pine, Palm, Dead Tree silhouettes
  - `Mountains`: Mountain ranges and peak horizons
  - `Buildings`: City skyline silhouettes
  - `Foliage`, `Power Lines`, `Birds`, `Nature`
- **Interactive placement**: Click to place stamps at horizon line or custom coordinates.
- **Transform & styling**: Scale (0.2x–4.0x), rotation (-180° to 180°), horizontal flip, opacity, and silhouette color tint.
- **Custom stamps**: Import any custom PNG/JPG silhouette or graphic directly into the stamp library.

### 🌅 Physical Atmosphere & Sky Simulation
- **Rayleigh & Mie scattering**: Physically-based sky gradients calculated from atmospheric particle scattering.
- **Time-of-day slider**: Automatic sun positioning and sky gradient transitions from dawn to noon to sunset to night.
- **Atmospheric haze & ground fog**: Depth and atmospheric attenuation controls.
- **Crepuscular rays (God Rays)**: Volumetric sunbeams shining through clouds and atmosphere.
- **Starfield**: Realistic night sky stars generator.

### 📚 Substance Painter–Style Layer System
- **Specialized layer types**:
  - 🎨 **Paint Layer**: Freeform brush, eraser, and color fills
  - ☀ **Sun Layer**: Dedicated procedural sun disc & halo
  - ☁ **Cloud Layer**: Procedural cloud field with noise controls
  - 🌅 **Atmosphere Layer**: Rayleigh/Mie physical sky simulation
  - 🌲 **Stamp Layer**: Non-destructive placed stamp collection
  - ⚙ **Adjustment Layer**: Non-destructive color grading (lift/gamma/gain)
- **Layer Masks**: Per-layer alpha masks (paint mask, invert mask, toggle mask).
- **Blend Modes**: Normal, Add, Multiply, Screen, Overlay, Soft Light.
- **Full Undo/Redo**: 30-state historical undo stack.
- **Project Save/Load**: Native `.hdriproject` format saving all layer stacks, masks, and metadata.

### 🚀 Cross-Engine One-Click Export
- **File formats**:
  - `.hdr` (Radiance RGBE 32-bit floating point)
  - `.exr` (OpenEXR high dynamic range)
  - `.png` (ACES tone-mapped LDR preview)
- **Cubemap export**:
  - 6 individual face textures: `+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z`
  - Horizontal / Vertical cross cubemap layout
- **Engine-specific packages**:
  - **Blender**: `.hdr` + auto-generated Python script configuring World Environment, EEVEE/Cycles settings, and a matching Sun Lamp.
  - **Unreal Engine**: `.hdr` + Python utility script + directional light setup data asset.
  - **Godot**: `.hdr` + GDScript + `WorldEnvironment` scene with `PanoramaSkyMaterial`.
  - **Unity**: `.hdr` + 6-face cubemap textures + `HDRIImporter.cs` C# editor plugin.
  - **All Engines**: One-click export bundling every engine preset into a single package.

### 🔮 Real-Time 3D Environment Preview
- Software-rendered sphere with real-time equirectangular environment mapping.
- Material modes: **Mirror**, **Diffuse**, and **Glossy**.
- Orbit camera with mouse drag and zoom controls.

---

## ⚡ Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/COLDATNIGHT-79/hdri-maker.git
cd hdri-maker

# Install requirements
pip install -r requirements.txt

# Run HDRI Maker
python main.py
```

### Optional: Build C++ Processing DLL

For accelerated blur, bloom, tone mapping, and composite math:

```bash
cd cpp
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

---

## 🛠 Usage Workflow ("Substance Painter for Lighting")

1. **Create Base Sky**:
   - Go to `Filter & Skies > Atmosphere & Rayleigh/Mie Scattering...`
   - Adjust the **Time of Day** slider (e.g. 17.5h for golden hour sunset).
2. **Place Sun**:
   - Select the **Sun Tool (S)** from the tools panel.
   - Click and drag on the canvas to place your primary sun.
   - Adjust temperature (e.g., 3200K for golden sunset, 5500K for midday sun) and intensity.
3. **Sculpt Clouds**:
   - Select the **Cloud Tool (C)**.
   - Choose a preset (`Cumulus`, `Cirrus`, or `Sunset`) and paint natural cloud formations.
4. **Place Horizon Elements**:
   - Select the **Stamp Tool (T)**.
   - Pick trees, mountains, or skylines and click along the horizon.
5. **Add God Rays & Effects**:
   - Use `Filter & Skies > God Rays...` and `Filter & Skies > Bloom / HDR Glow...`.
6. **Check 3D Preview**:
   - Rotate the 3D preview sphere to inspect how light and reflections wrap around objects.
7. **Export to Your Engine**:
   - Click **Export Presets (Ctrl+E)** and select **Blender**, **Unreal**, **Unity**, or **Godot**.
   - Run the generated script in your 3D engine for instant lighting setup.

---

## ⌨ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `B` | Brush tool |
| `E` | Eraser tool |
| `G` | Fill tool |
| `I` | Eyedropper tool |
| `S` | Sun creation tool |
| `C` | Cloud painting tool |
| `T` | Stamp placement tool |
| `Ctrl+S` | Save project (`.hdriproject`) |
| `Ctrl+O` | Open project (`.hdriproject`) |
| `Ctrl+E` | Cross-engine export presets |
| `Ctrl+Shift+E` | Export all formats |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Undo / Redo |
| `Ctrl+Shift+N` | Add Paint layer |
| `Ctrl+Alt+S` | Add Sun layer |
| `Ctrl+Alt+C` | Add Cloud layer |
| `Ctrl+Alt+A` | Add Atmosphere layer |
| `Ctrl+Alt+T` | Add Stamp layer |
| `Ctrl+M` | Toggle layer mask |
| `Ctrl+J` | Duplicate layer |
| `Ctrl+=` / `Ctrl+-` | Zoom in / Zoom out |
| `Ctrl+0` | Fit canvas to view |
| `Middle Mouse Drag` | Pan canvas |

---

## 📁 Repository Structure

```
hdri-maker/
├── main.py                     # Entry point
├── requirements.txt            # Python dependencies
├── README.md                   # Full documentation
├── src/
│   ├── app.py                  # Main GUI window, menus & toolbar
│   ├── canvas_widget.py        # Equirectangular canvas & tool drawing
│   ├── tools_panel.py          # Tools selector, sun, cloud & stamp UI
│   ├── layer_panel.py          # Layer stack, types, masks & blend modes
│   ├── hdri_engine.py          # Engine core, SunObject, layer data & save/load
│   ├── cloud_engine.py         # Multi-octave procedural cloud generator
│   ├── atmosphere.py           # Rayleigh & Mie scattering, god rays & stars
│   ├── stamp_library.py        # Element stamps, silhouettes & PNG importer
│   ├── exporter.py             # Multi-engine exporter & presets
│   ├── preview_3d.py           # 3D sphere preview with mirror/glossy shaders
│   └── filters.py              # Blur, Bloom, Color Grade, Noise, Sky dialogs
├── cpp/                        # C++ accelerated processing
│   ├── CMakeLists.txt
│   ├── hdri_processing.h
│   └── hdri_processing.cpp
├── csharp/                     # Unity engine integration
│   ├── HDRIImporter.cs
│   └── HDRIImporter.csproj
├── unreal/                     # Unreal Engine automation scripts
│   └── unreal_hdri_setup.py
├── godot/                      # Godot Engine automation scripts
│   └── godot_hdri_setup.py
└── assets/
    ├── sample_sphere.obj       # 3D preview sphere mesh
    └── stamps/                 # Built-in procedural stamp silhouettes
```

---

## 📄 License

MIT License — Free for personal and commercial use.
