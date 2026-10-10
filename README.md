# HDRI Maker — Surface Painter for HDR Environments

A multi-language tool (Python + C++ + C#) for creating, painting, and composing 
High Dynamic Range Images (HDRIs) for use in Blender, Unity, Unreal Engine, and other 3D applications.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![C++](https://img.shields.io/badge/C++-17-orange)
![C#](https://img.shields.io/badge/C%23-.NET_Standard_2.1-green)

## Features

### 🎨 HDRI Painting
- **Equirectangular canvas** for painting HDR environments
- **HDR color picker** with intensity values > 1.0 for creating light sources
- **Brush tool** with configurable size, hardness, and opacity
- **Eraser, fill, and eyedropper** tools

### 📚 Layer System
- Unlimited layers with thumbnails
- **Blend modes**: Normal, Add, Multiply, Screen, Overlay, Soft Light
- Per-layer opacity and visibility
- Drag to reorder, duplicate, merge down

### ✨ Filters & Effects
- **Gaussian Blur** — smooth HDR content
- **Bloom/Glow** — add glow to bright areas
- **Color Grading** — lift/gamma/gain adjustments
- **Noise** — add texture variation
- **Vignette** — darken edges
- **Procedural Sky** — generate realistic skies with presets (Clear Day, Sunset, Night, etc.)
- **Gradient Fill** — smooth color transitions

### 📦 Import/Export
- **Import**: PNG, JPG, HDR, EXR images as layers
- **Export**: .hdr (Radiance), .exr (OpenEXR), .png (tone-mapped)
- **Blender script** auto-generation for one-click environment setup
- **Unity plugin** (C#) for importing HDRIs as skybox

### 🔮 3D Preview
- Real-time software-rendered sphere with environment mapping
- Mirror, Diffuse, and Glossy material modes
- Orbit camera with zoom

### ⚡ Performance
- C++ processing library for fast blur, bloom, tone mapping, and compositing
- Python fallbacks when DLL is unavailable
- OpenMP parallelization support

## Quick Start

### Requirements
- Python 3.9+
- Windows 10/11 (primary platform)

### Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Optional: Build C++ DLL

For accelerated image processing, build the C++ library:

```bash
cd cpp
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

The DLL will be placed in the project root directory automatically.

## Project Structure

```
hdri-maker/
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
├── src/
│   ├── __init__.py
│   ├── app.py                  # Main window & menus
│   ├── canvas_widget.py        # Painting canvas
│   ├── layer_panel.py          # Layer management UI
│   ├── tools_panel.py          # Tool selection & settings
│   ├── preview_3d.py           # 3D environment preview
│   ├── filters.py              # Filter dialogs & effects
│   ├── exporter.py             # Multi-format export
│   └── hdri_engine.py          # Core engine & C++ bridge
├── cpp/
│   ├── CMakeLists.txt          # C++ build configuration
│   ├── hdri_processing.h       # C++ API header
│   └── hdri_processing.cpp     # C++ implementations
├── csharp/
│   ├── HDRIImporter.cs         # Unity Editor plugin
│   └── HDRIImporter.csproj     # C# project file
└── assets/
    └── sample_sphere.obj       # Generated on first run
```

## Usage Guide

### Creating an HDRI

1. **Start with a sky**: Use `Filter > Generate Procedural Sky` to create a base
2. **Add layers**: Paint details, clouds, or ground on separate layers
3. **Adjust lighting**: Use HDR intensity > 1.0 for sun/light areas
4. **Apply effects**: Add bloom, color grading, or noise
5. **Preview**: Check the 3D preview to see lighting in real-time
6. **Export**: Save as .hdr for Blender/Unity

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `B` | Brush tool |
| `E` | Eraser tool |
| `G` | Fill tool |
| `I` | Eyedropper |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+I` | Import image |
| `Ctrl+Shift+E` | Export all formats |
| `Ctrl+Shift+N` | New layer |
| `Ctrl+J` | Duplicate layer |
| `Ctrl+E` | Merge down |
| `Ctrl+=` / `Ctrl+-` | Zoom in/out |
| `Ctrl+0` | Fit to view |
| `Middle Mouse` | Pan canvas |
| `Scroll Wheel` | Zoom |

### Using in Blender

1. Export your HDRI as .hdr
2. Use the auto-generated Blender script, or:
3. In Blender: World Properties > Surface > Environment Texture > Open your .hdr file

### Using in Unity

1. Copy `csharp/HDRIImporter.cs` to `Assets/Editor/` in your Unity project
2. Go to `Window > HDRI Maker > Import HDRI`
3. Select your .hdr file and click Import
4. The HDRI will be set as your scene's skybox automatically

## Technology Stack

| Component | Language | Purpose |
|-----------|----------|---------|
| GUI & Core Logic | Python (PySide6) | Application framework |
| Image Processing | C++ (DLL) | High-performance operations |
| Unity Plugin | C# | Editor integration |
| Data Processing | NumPy | Array operations |
| Image I/O | Pillow, imageio | Format support |

## License

MIT License — Free for personal and commercial use.
