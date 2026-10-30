"""WAV waveform cache and a lightweight 3D View POST_PIXEL overlay."""

import math
import os
import wave

import bpy
import numpy as np
import gpu
import blf
from gpu_extras.batch import batch_for_shader


_WAVE_CACHE = {}
_DRAW_HANDLE = None


def invalidate_cache():
    _WAVE_CACHE.clear()


def _decode_pcm(raw, sample_width):
    if sample_width == 1:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if sample_width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if sample_width == 3:
        values = np.frombuffer(raw, dtype=np.uint8).reshape((-1, 3)).astype(np.int32)
        signed = values[:, 0] | (values[:, 1] << 8) | (values[:, 2] << 16)
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        return signed.astype(np.float32) / 8388608.0
    raise ValueError(f"WAV PCM con {sample_width} bytes por muestra no está soportado.")


def load_waveform(filepath, bins=512):
    path = bpy.path.abspath(filepath)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("Selecciona un archivo WAV existente.")
    cache_key = os.path.realpath(path)
    if cache_key in _WAVE_CACHE:
        return _WAVE_CACHE[cache_key]

    try:
        with wave.open(path, "rb") as source:
            if source.getcomptype() != "NONE":
                raise ValueError("Solo se admiten archivos WAV PCM sin compresión.")
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            frame_count = source.getnframes()
            sample_rate = source.getframerate()
            if channels < 1 or frame_count < 1 or sample_rate < 1:
                raise ValueError("El archivo WAV no contiene audio válido.")

            peak_values = np.zeros(bins, dtype=np.float32)
            for bucket in range(bins):
                begin = bucket * frame_count // bins
                end = (bucket + 1) * frame_count // bins
                if end <= begin:
                    continue
                source.setpos(begin)
                raw = source.readframes(end - begin)
                samples = _decode_pcm(raw, sample_width)
                usable = samples.size - (samples.size % channels)
                if usable == 0:
                    continue
                samples = samples[:usable].reshape((-1, channels))
                mono = samples.mean(axis=1)
                peak_values[bucket] = float(np.max(np.abs(mono)))
            result = (peak_values, frame_count / sample_rate)
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"No se pudo leer el WAV: {exc}") from exc

    _WAVE_CACHE[cache_key] = result
    return result


def _draw_lines(vertices, color):
    if not vertices:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_overlay():
    context = bpy.context
    scene = context.scene
    if scene is None or not hasattr(scene, "bpmav_settings"):
        return
    settings = scene.bpmav_settings
    if not settings.audio_enabled:
        return

    path = settings.audio_filepath
    if not path:
        return
    try:
        peaks, duration = load_waveform(path)
    except (OSError, ValueError) as exc:
        blf.position(0, 12, 24, 0)
        blf.size(0, 11)
        blf.color(0, 1.0, 0.35, 0.25, 1.0)
        blf.draw(0, f"Audio no disponible: {exc}")
        return

    region = context.region
    if region is None:
        return
    width = region.width
    height = settings.audio_height
    bottom = 18
    center_y = bottom + height * 0.5
    scale_y = height * 0.44
    waveform = []
    count = len(peaks)
    for index, peak in enumerate(peaks):
        x = index * width / max(1, count - 1)
        amplitude = max(1.0, float(peak) * scale_y)
        waveform.extend(((x, center_y - amplitude), (x, center_y + amplitude)))

    gpu.state.blend_set("ALPHA")
    _draw_lines(waveform, (*settings.audio_color, 0.9))
    fps = scene.render.fps / scene.render.fps_base
    elapsed = (scene.frame_current - scene.frame_start) / fps
    cursor_x = min(width, max(0.0, elapsed / duration * width))
    _draw_lines(((cursor_x, bottom), (cursor_x, bottom + height)), (1.0, 0.85, 0.2, 0.95))
    gpu.state.blend_set("NONE")

    blf.position(0, 12, bottom + height + 4, 0)
    blf.size(0, 11)
    blf.color(0, 1.0, 1.0, 1.0, 0.9)
    blf.draw(0, f"WAV: {os.path.basename(bpy.path.abspath(path))}")


def _refresh_viewports(_scene, _depsgraph=None):
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def register():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceView3D.draw_handler_add(
            _draw_overlay, (), "WINDOW", "POST_PIXEL"
        )
    if _refresh_viewports not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_refresh_viewports)


def unregister():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
    if _refresh_viewports in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_refresh_viewports)
    invalidate_cache()
