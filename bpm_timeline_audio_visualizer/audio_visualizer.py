"""Timeline waveform, musical-grid overlay, and WAV playback."""

import math
import os
import wave

import bpy
import blf
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader


_WAVE_CACHE = {}
_DRAW_HANDLE = None
_AUDIO_DEVICE = None
_AUDIO_HANDLE = None
_AUDIO_SOUND = None
_CACHE_BINS = 8192
_MAX_GRID_LINES = 10000


def invalidate_cache():
    _WAVE_CACHE.clear()


def stop_audio():
    global _AUDIO_DEVICE, _AUDIO_HANDLE, _AUDIO_SOUND
    if _AUDIO_HANDLE is not None:
        _AUDIO_HANDLE.stop()
    _AUDIO_HANDLE = None
    _AUDIO_SOUND = None
    _AUDIO_DEVICE = None


def set_audio_volume(volume):
    if _AUDIO_HANDLE is not None:
        _AUDIO_HANDLE.volume = min(1.0, max(0.0, volume))


def play_audio(filepath, start_seconds=0.0, volume=1.0):
    global _AUDIO_DEVICE, _AUDIO_HANDLE, _AUDIO_SOUND
    import aud

    path = bpy.path.abspath(filepath)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("Selecciona un archivo WAV existente.")
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("La posición de reproducción no es válida.")
    stop_audio()
    try:
        _AUDIO_DEVICE = aud.Device()
        _AUDIO_SOUND = aud.Sound(path)
        _AUDIO_HANDLE = _AUDIO_DEVICE.play(_AUDIO_SOUND)
        _AUDIO_HANDLE.volume = min(1.0, max(0.0, volume))
        if start_seconds:
            _AUDIO_HANDLE.position = start_seconds
        if not _AUDIO_HANDLE.status:
            stop_audio()
            raise RuntimeError("Blender no pudo iniciar la reproducción del WAV.")
    except Exception as exc:
        stop_audio()
        raise RuntimeError(f"No se pudo reproducir el archivo de audio: {exc}") from exc


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


def load_waveform(filepath, bins=_CACHE_BINS):
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
                mono = samples[:usable].reshape((-1, channels)).mean(axis=1)
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


def _draw_background(left, right, bottom, top):
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(
        shader,
        "TRI_FAN",
        {"pos": ((left, bottom), (right, bottom), (right, top), (left, top))},
    )
    shader.bind()
    shader.uniform_float("color", (0.015, 0.02, 0.025, 0.78))
    batch.draw(shader)


def _visible_frame_range(region):
    left = region.view2d.region_to_view(0, 0)[0]
    right = region.view2d.region_to_view(region.width, 0)[0]
    return min(left, right), max(left, right)


def _enabled_subdivisions(settings):
    subdivisions = set()
    if settings.enable_binary:
        subdivisions.update((2, 4, 8, 16, 32))
    if settings.enable_ternary:
        subdivisions.update((3, 6, 12))
    if settings.enable_tuplets:
        subdivisions.update((5, 7))
    return sorted(subdivisions)


def _grid_vertices(scene, settings, region, x_min, x_max, bottom, top):
    from . import utils

    beat_frames = utils.beat_seconds(settings) * utils.scene_fps(scene)
    if beat_frames <= 0.0:
        return [], []
    total_beats = settings.beats_per_bar * settings.duration_bars
    if total_beats <= 0:
        return [], []
    origin = utils.music_origin_frame(scene, settings)
    first_beat = max(0, math.floor((x_min - origin) / beat_frames))
    last_beat = min(total_beats - 1, math.ceil((x_max - origin) / beat_frames))
    if last_beat < first_beat:
        return [], []
    beats_visible = max(0, last_beat - first_beat + 1)
    subdivisions = _enabled_subdivisions(settings)
    line_count = beats_visible * (1 + sum(value - 1 for value in subdivisions))
    if line_count > _MAX_GRID_LINES:
        return [], []

    major = []
    minor = []
    to_x = region.view2d.view_to_region
    for beat_index in range(first_beat, last_beat + 1):
        frame = origin + beat_index * beat_frames
        if x_min <= frame <= x_max:
            x = to_x(frame, 0, clip=False)[0]
            major.extend(((x, bottom), (x, top)))
        for divisions in subdivisions:
            for step in range(1, divisions):
                frame = origin + (beat_index + step / divisions) * beat_frames
                if x_min <= frame <= x_max:
                    x = to_x(frame, 0, clip=False)[0]
                    minor.extend(((x, bottom), (x, top)))
    return major, minor


def _waveform_vertices(scene, region, bottom, top, peaks, duration):
    fps = scene.render.fps / scene.render.fps_base
    if fps <= 0.0 or duration <= 0.0:
        return []
    center_y = (bottom + top) * 0.5
    amplitude_scale = max(1.0, (top - bottom) * 0.44)
    vertices = []
    for pixel_x in range(region.width):
        frame = region.view2d.region_to_view(pixel_x, 0)[0]
        elapsed = (frame - scene.frame_start) / fps
        if elapsed < 0.0 or elapsed >= duration:
            continue
        bin_index = min(len(peaks) - 1, int(elapsed / duration * len(peaks)))
        amplitude = max(1.0, float(peaks[bin_index]) * amplitude_scale)
        vertices.extend(((pixel_x, center_y - amplitude), (pixel_x, center_y + amplitude)))
    return vertices


def _draw_overlay():
    context = bpy.context
    scene = context.scene
    area = context.area
    region = context.region
    if (
        scene is None
        or area is None
        or area.type != "DOPESHEET_EDITOR"
        or region is None
        or region.type != "WINDOW"
        or not hasattr(scene, "bpmav_settings")
    ):
        return

    settings = scene.bpmav_settings
    height = settings.audio_height if settings.audio_enabled and settings.audio_filepath else 28
    height = min(height, max(20, region.height - 2))
    bottom = 2
    top = bottom + height
    x_min, x_max = _visible_frame_range(region)

    gpu.state.blend_set("ALPHA")
    _draw_background(0, region.width, bottom, top)
    try:
        major, minor = _grid_vertices(scene, settings, region, x_min, x_max, bottom, top)
        _draw_lines(minor, (*settings.division_color, 0.7))
        _draw_lines(major, (*settings.marker_color, 0.95))
    except (KeyError, ValueError, ZeroDivisionError, OverflowError):
        pass

    if settings.audio_enabled and settings.audio_filepath:
        try:
            peaks, duration = load_waveform(settings.audio_filepath)
            waveform = _waveform_vertices(
                scene, region, bottom, top, peaks, duration
            )
            _draw_lines(waveform, (*settings.audio_color, 0.95))
            blf.position(0, 8, top + 3, 0)
            blf.size(0, 11)
            blf.color(0, 0.95, 0.98, 1.0, 0.95)
            blf.draw(0, f"WAV: {os.path.basename(bpy.path.abspath(settings.audio_filepath))}")
        except (OSError, ValueError) as exc:
            blf.position(0, 8, top + 3, 0)
            blf.size(0, 11)
            blf.color(0, 1.0, 0.35, 0.25, 1.0)
            blf.draw(0, f"Audio no disponible: {exc}")

    playhead_x = region.view2d.view_to_region(scene.frame_current, 0, clip=False)[0]
    if 0 <= playhead_x <= region.width:
        _draw_lines(
            ((playhead_x, bottom), (playhead_x, top)),
            (1.0, 0.85, 0.2, 1.0),
        )
    gpu.state.blend_set("NONE")


def _refresh_editors(_scene, _depsgraph=None):
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()


def register():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE = bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            _draw_overlay, (), "WINDOW", "POST_PIXEL"
        )
    if _refresh_editors not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_refresh_editors)


def unregister():
    global _DRAW_HANDLE
    stop_audio()
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
    if _refresh_editors in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_refresh_editors)
    invalidate_cache()
