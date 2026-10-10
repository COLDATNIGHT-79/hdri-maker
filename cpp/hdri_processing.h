/*
 * HDRI Processing Library - High-performance image processing for HDRI Maker
 * Compiled as a shared library (.dll on Windows, .so on Linux)
 * Called from Python via ctypes
 */

#ifndef HDRI_PROCESSING_H
#define HDRI_PROCESSING_H

#ifdef _WIN32
    #define HDRI_API extern "C" __declspec(dllexport)
#else
    #define HDRI_API extern "C" __attribute__((visibility("default")))
#endif

/* Blend modes for layer compositing */
enum BlendMode {
    BLEND_NORMAL = 0,
    BLEND_ADD = 1,
    BLEND_MULTIPLY = 2,
    BLEND_SCREEN = 3,
    BLEND_OVERLAY = 4,
    BLEND_SOFT_LIGHT = 5
};

/* ===================== Image Processing ===================== */

/**
 * Apply Gaussian blur to an HDR image (in-place).
 * @param data      Pointer to float32 RGBA pixel data
 * @param width     Image width in pixels
 * @param height    Image height in pixels
 * @param channels  Number of channels (3 or 4)
 * @param sigma     Blur radius/sigma
 */
HDRI_API void gaussian_blur(float* data, int width, int height, int channels, float sigma);

/**
 * Apply bloom/glow filter to bright areas of an HDR image (in-place).
 * @param data      Pointer to float32 RGBA pixel data
 * @param width     Image width in pixels
 * @param height    Image height in pixels
 * @param channels  Number of channels (3 or 4)
 * @param threshold Brightness threshold for bloom extraction
 * @param intensity Bloom intensity multiplier
 * @param radius    Bloom blur radius
 */
HDRI_API void bloom_filter(float* data, int width, int height, int channels,
                           float threshold, float intensity, float radius);

/**
 * Reinhard tone mapping operator.
 * @param src       Source HDR float32 data
 * @param dst       Destination LDR float32 data (0-1 range)
 * @param width     Image width
 * @param height    Image height
 * @param channels  Number of channels
 * @param exposure  Exposure adjustment
 */
HDRI_API void tone_map_reinhard(const float* src, float* dst,
                                 int width, int height, int channels, float exposure);

/**
 * ACES filmic tone mapping operator.
 * @param src       Source HDR float32 data
 * @param dst       Destination LDR float32 data (0-1 range)
 * @param width     Image width
 * @param height    Image height
 * @param channels  Number of channels
 * @param exposure  Exposure adjustment
 */
HDRI_API void tone_map_aces(const float* src, float* dst,
                             int width, int height, int channels, float exposure);

/**
 * Composite two layers together.
 * @param base      Base layer float32 data
 * @param overlay   Overlay layer float32 data
 * @param result    Output composited float32 data
 * @param width     Image width
 * @param height    Image height
 * @param channels  Number of channels
 * @param opacity   Overlay opacity (0.0 - 1.0)
 * @param blend_mode Blend mode enum value
 */
HDRI_API void composite_layers(const float* base, const float* overlay, float* result,
                                int width, int height, int channels,
                                float opacity, int blend_mode);

/**
 * Apply color grading to an HDR image (in-place).
 * @param data       Pointer to float32 pixel data
 * @param width      Image width
 * @param height     Image height
 * @param channels   Number of channels
 * @param lift_r/g/b Shadow color lift
 * @param gamma_r/g/b Midtone gamma
 * @param gain_r/g/b Highlight gain
 */
HDRI_API void color_grade(float* data, int width, int height, int channels,
                           float lift_r, float lift_g, float lift_b,
                           float gamma_r, float gamma_g, float gamma_b,
                           float gain_r, float gain_g, float gain_b);

/**
 * Add procedural noise to an HDR image (in-place).
 * @param data      Pointer to float32 pixel data
 * @param width     Image width
 * @param height    Image height
 * @param channels  Number of channels
 * @param intensity Noise intensity
 * @param seed      Random seed
 */
HDRI_API void add_noise(float* data, int width, int height, int channels,
                         float intensity, unsigned int seed);

/**
 * Generate a procedural sky gradient.
 * @param data      Output float32 data
 * @param width     Image width
 * @param height    Image height
 * @param channels  Number of channels (must be 4)
 * @param horizon_r/g/b Horizon color
 * @param zenith_r/g/b  Zenith (top) color
 * @param ground_r/g/b  Ground (bottom) color
 * @param sun_intensity  Sun disc intensity
 * @param sun_x/sun_y   Sun position (normalized 0-1)
 * @param sun_size       Sun disc size (radians)
 */
HDRI_API void generate_sky(float* data, int width, int height, int channels,
                            float horizon_r, float horizon_g, float horizon_b,
                            float zenith_r, float zenith_g, float zenith_b,
                            float ground_r, float ground_g, float ground_b,
                            float sun_intensity, float sun_x, float sun_y, float sun_size);

#endif /* HDRI_PROCESSING_H */
