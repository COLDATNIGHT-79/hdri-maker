/*
 * HDRI Processing Library
 * High-performance image processing routines for the HDRI Maker tool.
 * 
 * All functions operate on float32 RGBA buffers in row-major order.
 * Memory layout: [R0,G0,B0,A0, R1,G1,B1,A1, ...]
 */

#include "hdri_processing.h"
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ================================================================
 *  UTILITY HELPERS
 * ================================================================ */

static inline float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static inline float lerp(float a, float b, float t) {
    return a + t * (b - a);
}

/* Simple linear-congruential PRNG for noise generation */
static inline unsigned int lcg_next(unsigned int state) {
    return state * 1103515245u + 12345u;
}

static inline float lcg_float(unsigned int state) {
    return (float)(state & 0x7FFFFFFF) / (float)0x7FFFFFFF;
}

/* ================================================================
 *  1-D GAUSSIAN KERNEL
 * ================================================================ */

static std::vector<float> make_gaussian_kernel(float sigma) {
    int radius = (int)std::ceil(sigma * 3.0f);
    if (radius < 1) radius = 1;
    int size = 2 * radius + 1;
    std::vector<float> kernel(size);
    float sum = 0.0f;
    float inv2s2 = 1.0f / (2.0f * sigma * sigma);
    for (int i = 0; i < size; ++i) {
        float x = (float)(i - radius);
        kernel[i] = std::exp(-x * x * inv2s2);
        sum += kernel[i];
    }
    for (int i = 0; i < size; ++i)
        kernel[i] /= sum;
    return kernel;
}

/* ================================================================
 *  GAUSSIAN BLUR (separable, 2-pass)
 * ================================================================ */

HDRI_API void gaussian_blur(float* data, int width, int height, int channels, float sigma) {
    if (sigma <= 0.0f || !data) return;

    auto kernel = make_gaussian_kernel(sigma);
    int radius = (int)(kernel.size() / 2);
    int pixel_count = width * height * channels;

    std::vector<float> temp(pixel_count);

    /* Horizontal pass */
    #pragma omp parallel for schedule(static)
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            float accum[4] = {0, 0, 0, 0};
            for (int k = -radius; k <= radius; ++k) {
                /* Wrap horizontally for equirectangular */
                int sx = (x + k + width) % width;
                int idx = (y * width + sx) * channels;
                float w = kernel[k + radius];
                for (int c = 0; c < channels; ++c)
                    accum[c] += data[idx + c] * w;
            }
            int out_idx = (y * width + x) * channels;
            for (int c = 0; c < channels; ++c)
                temp[out_idx + c] = accum[c];
        }
    }

    /* Vertical pass */
    #pragma omp parallel for schedule(static)
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            float accum[4] = {0, 0, 0, 0};
            for (int k = -radius; k <= radius; ++k) {
                int sy = clampf((float)(y + k), 0.0f, (float)(height - 1));
                int idx = ((int)sy * width + x) * channels;
                float w = kernel[k + radius];
                for (int c = 0; c < channels; ++c)
                    accum[c] += temp[idx + c] * w;
            }
            int out_idx = (y * width + x) * channels;
            for (int c = 0; c < channels; ++c)
                data[out_idx + c] = accum[c];
        }
    }
}

/* ================================================================
 *  BLOOM / GLOW FILTER
 * ================================================================ */

HDRI_API void bloom_filter(float* data, int width, int height, int channels,
                           float threshold, float intensity, float radius) {
    if (!data) return;
    int pixel_count = width * height * channels;

    /* Step 1: Extract bright areas */
    std::vector<float> bright(pixel_count, 0.0f);
    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        float lum = 0.2126f * data[idx] + 0.7152f * data[idx + 1] + 0.0722f * data[idx + 2];
        if (lum > threshold) {
            float factor = (lum - threshold) / lum;
            for (int c = 0; c < std::min(channels, 3); ++c)
                bright[idx + c] = data[idx + c] * factor;
        }
        if (channels == 4) bright[idx + 3] = 1.0f;
    }

    /* Step 2: Blur the bright areas */
    gaussian_blur(bright.data(), width, height, channels, radius);

    /* Step 3: Add back to original */
    #pragma omp parallel for schedule(static)
    for (int i = 0; i < pixel_count; ++i) {
        data[i] += bright[i] * intensity;
    }
}

/* ================================================================
 *  TONE MAPPING - REINHARD
 * ================================================================ */

HDRI_API void tone_map_reinhard(const float* src, float* dst,
                                 int width, int height, int channels, float exposure) {
    if (!src || !dst) return;
    float exp_scale = std::pow(2.0f, exposure);

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        for (int c = 0; c < std::min(channels, 3); ++c) {
            float v = src[idx + c] * exp_scale;
            dst[idx + c] = v / (1.0f + v);  /* Reinhard operator */
        }
        if (channels == 4)
            dst[idx + 3] = src[idx + 3];
    }
}

/* ================================================================
 *  TONE MAPPING - ACES FILMIC
 * ================================================================ */

static inline float aces_curve(float x) {
    /* Attempt at a simple ACES-like filmic curve */
    float a = 2.51f, b = 0.03f, c = 2.43f, d = 0.59f, e = 0.14f;
    return clampf((x * (a * x + b)) / (x * (c * x + d) + e), 0.0f, 1.0f);
}

HDRI_API void tone_map_aces(const float* src, float* dst,
                             int width, int height, int channels, float exposure) {
    if (!src || !dst) return;
    float exp_scale = std::pow(2.0f, exposure);

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        for (int c = 0; c < std::min(channels, 3); ++c) {
            float v = src[idx + c] * exp_scale;
            dst[idx + c] = aces_curve(v);
        }
        if (channels == 4)
            dst[idx + 3] = src[idx + 3];
    }
}

/* ================================================================
 *  LAYER COMPOSITING
 * ================================================================ */

HDRI_API void composite_layers(const float* base, const float* overlay, float* result,
                                int width, int height, int channels,
                                float opacity, int blend_mode) {
    if (!base || !overlay || !result) return;

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        float oa = (channels == 4) ? overlay[idx + 3] * opacity : opacity;

        for (int c = 0; c < std::min(channels, 3); ++c) {
            float b = base[idx + c];
            float o = overlay[idx + c];
            float blended;

            switch ((BlendMode)blend_mode) {
                case BLEND_ADD:
                    blended = b + o;
                    break;
                case BLEND_MULTIPLY:
                    blended = b * o;
                    break;
                case BLEND_SCREEN:
                    blended = 1.0f - (1.0f - b) * (1.0f - o);
                    break;
                case BLEND_OVERLAY:
                    blended = (b < 0.5f) ? (2.0f * b * o) : (1.0f - 2.0f * (1.0f - b) * (1.0f - o));
                    break;
                case BLEND_SOFT_LIGHT: {
                    float d = (b <= 0.25f) ? ((16.0f * b - 12.0f) * b + 4.0f) * b : std::sqrt(b);
                    blended = (o <= 0.5f) ? b - (1.0f - 2.0f * o) * b * (1.0f - b)
                                          : b + (2.0f * o - 1.0f) * (d - b);
                    break;
                }
                case BLEND_NORMAL:
                default:
                    blended = o;
                    break;
            }

            result[idx + c] = lerp(b, blended, oa);
        }

        if (channels == 4) {
            /* Alpha compositing: result alpha is union */
            float ba = base[idx + 3];
            result[idx + 3] = ba + oa * (1.0f - ba);
        }
    }
}

/* ================================================================
 *  COLOR GRADING (Lift / Gamma / Gain)
 * ================================================================ */

HDRI_API void color_grade(float* data, int width, int height, int channels,
                           float lift_r, float lift_g, float lift_b,
                           float gamma_r, float gamma_g, float gamma_b,
                           float gain_r, float gain_g, float gain_b) {
    if (!data) return;
    float lifts[3]  = {lift_r, lift_g, lift_b};
    float gammas[3] = {gamma_r, gamma_g, gamma_b};
    float gains[3]  = {gain_r, gain_g, gain_b};

    /* Invert gammas for pow operation */
    float inv_gammas[3];
    for (int c = 0; c < 3; ++c)
        inv_gammas[c] = (gammas[c] > 0.001f) ? (1.0f / gammas[c]) : 1000.0f;

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        for (int c = 0; c < std::min(channels, 3); ++c) {
            float v = data[idx + c];
            /* Apply gain */
            v *= gains[c];
            /* Apply lift (add to shadows) */
            v += lifts[c] * (1.0f - v);
            /* Apply gamma */
            if (v > 0.0f)
                v = std::pow(v, inv_gammas[c]);
            data[idx + c] = v;
        }
    }
}

/* ================================================================
 *  NOISE GENERATION
 * ================================================================ */

HDRI_API void add_noise(float* data, int width, int height, int channels,
                         float intensity, unsigned int seed) {
    if (!data) return;

    #pragma omp parallel for schedule(static)
    for (int i = 0; i < width * height; ++i) {
        int idx = i * channels;
        unsigned int state = seed ^ (unsigned int)(i * 2654435761u);
        for (int c = 0; c < std::min(channels, 3); ++c) {
            state = lcg_next(state);
            float noise = (lcg_float(state) - 0.5f) * 2.0f * intensity;
            data[idx + c] += noise;
            if (data[idx + c] < 0.0f) data[idx + c] = 0.0f;
        }
    }
}

/* ================================================================
 *  PROCEDURAL SKY GENERATION
 * ================================================================ */

HDRI_API void generate_sky(float* data, int width, int height, int channels,
                            float horizon_r, float horizon_g, float horizon_b,
                            float zenith_r, float zenith_g, float zenith_b,
                            float ground_r, float ground_g, float ground_b,
                            float sun_intensity, float sun_x, float sun_y, float sun_size) {
    if (!data || channels < 3) return;

    /* Convert sun position from normalized [0,1] to spherical angles */
    float sun_theta = sun_x * 2.0f * (float)M_PI;
    float sun_phi = sun_y * (float)M_PI;
    float sun_dir[3] = {
        std::sin(sun_phi) * std::cos(sun_theta),
        std::cos(sun_phi),
        std::sin(sun_phi) * std::sin(sun_theta)
    };

    float cos_sun_size = std::cos(sun_size);

    #pragma omp parallel for schedule(static)
    for (int y = 0; y < height; ++y) {
        float v = (float)y / (float)(height - 1);         /* 0 = top, 1 = bottom */
        float phi = v * (float)M_PI;                       /* polar angle */

        for (int x = 0; x < width; ++x) {
            float u = (float)x / (float)(width - 1);      /* 0 = left, 1 = right */
            float theta = u * 2.0f * (float)M_PI;          /* azimuth */

            /* Direction vector for this pixel */
            float dir[3] = {
                std::sin(phi) * std::cos(theta),
                std::cos(phi),
                std::sin(phi) * std::sin(theta)
            };

            int idx = (y * width + x) * channels;

            float r, g, b;

            if (v < 0.5f) {
                /* Sky: interpolate from horizon to zenith */
                float t = 1.0f - (v / 0.5f);  /* 0 at horizon, 1 at zenith */
                t = t * t;  /* Ease-in for softer gradient */
                r = lerp(horizon_r, zenith_r, t);
                g = lerp(horizon_g, zenith_g, t);
                b = lerp(horizon_b, zenith_b, t);
            } else {
                /* Ground: interpolate from horizon to ground */
                float t = (v - 0.5f) / 0.5f;  /* 0 at horizon, 1 at nadir */
                t = std::sqrt(t);  /* Faster falloff */
                r = lerp(horizon_r, ground_r, t);
                g = lerp(horizon_g, ground_g, t);
                b = lerp(horizon_b, ground_b, t);
            }

            /* Sun disc */
            float dot = dir[0] * sun_dir[0] + dir[1] * sun_dir[1] + dir[2] * sun_dir[2];
            if (dot > cos_sun_size) {
                float sun_factor = (dot - cos_sun_size) / (1.0f - cos_sun_size);
                sun_factor = sun_factor * sun_factor * sun_factor;  /* Sharp falloff */
                r += sun_intensity * sun_factor;
                g += sun_intensity * 0.95f * sun_factor;
                b += sun_intensity * 0.85f * sun_factor;
            }

            /* Sun glow (larger, softer halo) */
            if (dot > 0.0f) {
                float glow = std::pow(dot, 64.0f) * sun_intensity * 0.3f;
                r += glow * 1.0f;
                g += glow * 0.9f;
                b += glow * 0.7f;
            }

            /* Atmospheric scattering near horizon */
            float horizon_blend = std::exp(-std::abs(v - 0.5f) * 10.0f);
            r += horizon_blend * 0.05f;
            g += horizon_blend * 0.03f;
            b += horizon_blend * 0.01f;

            data[idx + 0] = r;
            data[idx + 1] = g;
            data[idx + 2] = b;
            if (channels == 4)
                data[idx + 3] = 1.0f;
        }
    }
}
