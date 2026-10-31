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
_AUTO_PLAYBACK_ACTIVE = False
_AUTO_AUDIO_ACTIVE = False
_LAST_PLAYBACK_FRAME = None
_LAST_METRONOME_BEAT = None
_LAST_PLAYBACK_ERROR = None
_METRONOME_SOUNDS = None
_METRONOME_HANDLES = []
_CACHE_BINS = 8192
_MAX_GRID_LINES = 10000


def invalidate_cache():
    _WAVE_CACHE.clear()


def stop_audio():
    global _AUDIO_DEVICE, _AUDIO_HANDLE, _AUDIO_SOUND, _METRONOME_HANDLES
    if _AUDIO_HANDLE is not None:
        _AUDIO_HANDLE.stop()
    for handle in _METRONOME_HANDLES:
        handle.stop()
    _METRONOME_HANDLES.clear()
    _AUDIO_HANDLE = None
    _AUDIO_SOUND = None
    _AUDIO_DEVICE = None


def reset_playback_sync():
    global _AUTO_PLAYBACK_ACTIVE, _AUTO_AUDIO_ACTIVE
    global _LAST_PLAYBACK_FRAME, _LAST_METRONOME_BEAT
    _AUTO_PLAYBACK_ACTIVE = False
    _AUTO_AUDIO_ACTIVE = False
    _LAST_PLAYBACK_FRAME = None
    _LAST_METRONOME_BEAT = None


def update_audio_offset():
    global _AUTO_PLAYBACK_ACTIVE, _AUTO_AUDIO_ACTIVE
    if _AUDIO_HANDLE is None:
        return
    scene = bpy.context.scene
    if scene is None or not hasattr(scene, "bpmav_settings"):
        return
    fps = scene.render.fps / scene.render.fps_base
    elapsed = (
        scene.frame_current
        - scene.frame_start
        - scene.bpmav_settings.audio_offset_frames
    ) / fps
    if elapsed < 0:
        stop_audio()
        _AUTO_PLAYBACK_ACTIVE = False
        _AUTO_AUDIO_ACTIVE = False
        return
    try:
        _AUDIO_HANDLE.position = elapsed
    except RuntimeError as exc:
        _report_playback_error(exc)


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
    except (OSError, RuntimeError, ValueError, aud.error) as exc:
        stop_audio()
        raise RuntimeError(f"No se pudo reproducir el archivo de audio: {exc}") from exc


def _metronome_sounds():
    global _METRONOME_SOUNDS
    if _METRONOME_SOUNDS is None:
        import aud

        sample_rate = 44100
        duration = 0.045
        sample_count = int(sample_rate * duration)
        time = np.arange(sample_count, dtype=np.float32) / sample_rate

        def click(frequency):
            envelope = np.exp(-time * 85.0)
            samples = (np.sin(2.0 * np.pi * frequency * time) * envelope * 0.6)
            return aud.Sound.buffer(samples.reshape((-1, 1)).astype(np.float32), sample_rate)

        _METRONOME_SOUNDS = (click(1760.0), click(1100.0))
    return _METRONOME_SOUNDS


def _play_metronome_click(strong, volume):
    global _AUDIO_DEVICE, _METRONOME_HANDLES
    import aud

    try:
        if _AUDIO_DEVICE is None:
            _AUDIO_DEVICE = aud.Device()
        sound = _metronome_sounds()[0 if strong else 1]
        active_handles = []
        for handle in _METRONOME_HANDLES:
            try:
                if handle.status == aud.STATUS_PLAYING:
                    active_handles.append(handle)
            except RuntimeError:
                continue
        _METRONOME_HANDLES = active_handles
        handle = _AUDIO_DEVICE.play(sound)
        handle.volume = min(1.0, max(0.0, volume * (1.0 if strong else 0.72)))
        _METRONOME_HANDLES.append(handle)
    except aud.error as exc:
        raise RuntimeError(f"No se pudo reproducir el clic del metrónomo: {exc}") from exc


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

            minimum_values = np.full(bins, np.inf, dtype=np.float32)
            maximum_values = np.full(bins, -np.inf, dtype=np.float32)
            chunk_frames = 65536
            for begin in range(0, frame_count, chunk_frames):
                end = min(frame_count, begin + chunk_frames)
                raw = source.readframes(end - begin)
                samples = _decode_pcm(raw, sample_width)
                usable = samples.size - (samples.size % channels)
                if usable == 0:
                    continue
                mono = samples[:usable].reshape((-1, channels)).mean(axis=1)
                frame_indices = np.arange(begin, begin + mono.size, dtype=np.int64)
                bucket_indices = frame_indices * bins // frame_count
                np.minimum.at(minimum_values, bucket_indices, mono)
                np.maximum.at(maximum_values, bucket_indices, mono)
            empty_bins = ~np.isfinite(minimum_values)
            minimum_values[empty_bins] = 0.0
            maximum_values[empty_bins] = 0.0
            result = (minimum_values, maximum_values, frame_count / sample_rate)
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


def _draw_triangles(vertices, color):
    if not vertices:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": vertices})
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


def _waveform_vertices(scene, region, bottom, top, minimum_values, maximum_values, duration):
    fps = scene.render.fps / scene.render.fps_base
    if fps <= 0.0 or duration <= 0.0:
        return []
    center_y = (bottom + top) * 0.5
    sample_peak = max(
        float(np.max(np.abs(minimum_values))),
        float(np.max(np.abs(maximum_values))),
        1e-6,
    )
    amplitude_scale = (top - bottom) * 0.44 / sample_peak
    fill_vertices = []
    contour_vertices = []
    for pixel_x in range(region.width):
        frame = region.view2d.region_to_view(pixel_x, 0)[0]
        elapsed = (frame - scene.frame_start - scene.bpmav_settings.audio_offset_frames) / fps
        if elapsed < 0.0 or elapsed >= duration:
            continue
        bin_index = min(
            len(minimum_values) - 1,
            int(elapsed / duration * len(minimum_values)),
        )
        top_y = center_y - float(maximum_values[bin_index]) * amplitude_scale
        bottom_y = center_y - float(minimum_values[bin_index]) * amplitude_scale
        x_left = max(0, pixel_x - 0.5)
        x_right = min(region.width, pixel_x + 0.5)
        fill_vertices.extend(
            (
                (x_left, center_y), (x_left, top_y), (x_right, top_y),
                (x_left, center_y), (x_right, top_y), (x_right, center_y),
                (x_left, center_y), (x_right, center_y), (x_right, bottom_y),
                (x_left, center_y), (x_right, bottom_y), (x_left, bottom_y),
            )
        )
        contour_vertices.extend(
            ((pixel_x, top_y), (pixel_x, bottom_y))
        )
    return fill_vertices, contour_vertices


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
            minimum_values, maximum_values, duration = load_waveform(settings.audio_filepath)
            fill_vertices, contour_vertices = _waveform_vertices(
                scene,
                region,
                bottom,
                top,
                minimum_values,
                maximum_values,
                duration,
            )
            color = (*settings.audio_color, 0.8)
            _draw_triangles(fill_vertices, color)
            _draw_lines(contour_vertices, (*settings.audio_color, 1.0))
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


def _screen_is_playing():
    window_manager = bpy.context.window_manager
    return bool(
        window_manager
        and any(
            window.screen and window.screen.is_animation_playing
            for window in window_manager.windows
        )
    )


def _current_frame(scene):
    return float(scene.frame_current) + float(scene.frame_subframe)


def _sync_audio_and_metronome():
    global _AUTO_PLAYBACK_ACTIVE, _AUTO_AUDIO_ACTIVE
    global _LAST_PLAYBACK_FRAME, _LAST_METRONOME_BEAT, _LAST_PLAYBACK_ERROR
    if not bpy.app.background:
        window_manager = bpy.context.window_manager
        windows = window_manager.windows if window_manager else ()
        scene = next((window.scene for window in windows if window.scene), None)
    else:
        scene = bpy.context.scene
    if scene is None or not hasattr(scene, "bpmav_settings"):
        return

    settings = scene.bpmav_settings
    playing = _screen_is_playing()
    frame = _current_frame(scene)

    if not playing:
        if _AUTO_PLAYBACK_ACTIVE:
            stop_audio()
        _AUTO_PLAYBACK_ACTIVE = False
        _AUTO_AUDIO_ACTIVE = False
        _LAST_PLAYBACK_FRAME = None
        _LAST_METRONOME_BEAT = None
        return

    if not settings.sync_audio_to_playback and not settings.metronome_enabled:
        return

    fps = scene.render.fps / scene.render.fps_base
    if fps <= 0.0:
        return
    audio_started = False
    if settings.sync_audio_to_playback and settings.audio_filepath and not _AUTO_AUDIO_ACTIVE:
        elapsed = (frame - scene.frame_start - settings.audio_offset_frames) / fps
        if elapsed >= 0.0:
            try:
                _minimum, _maximum, duration = load_waveform(settings.audio_filepath)
                if elapsed < duration:
                    play_audio(
                        settings.audio_filepath,
                        elapsed,
                        settings.audio_volume,
                    )
                    audio_started = True
                    _AUTO_AUDIO_ACTIVE = True
                    _LAST_PLAYBACK_ERROR = None
            except (OSError, RuntimeError, ValueError) as exc:
                _report_playback_error(exc)

    if audio_started or settings.metronome_enabled:
        _AUTO_PLAYBACK_ACTIVE = True

    if settings.metronome_enabled:
        try:
            from . import utils

            beat_frames = utils.beat_seconds(settings) * fps
            origin = utils.music_origin_frame(scene, settings)
            beat_position = (frame - origin) / beat_frames
            beat_index = math.floor(beat_position + 1e-6)
            if _LAST_METRONOME_BEAT is None:
                nearest = round(beat_position)
                if abs(beat_position - nearest) < 0.08:
                    beat_index = nearest
                    _play_metronome_click(
                        beat_index % settings.beats_per_bar == 0,
                        settings.metronome_volume,
                    )
                _LAST_METRONOME_BEAT = beat_index
            elif beat_index > _LAST_METRONOME_BEAT:
                for passed_beat in range(_LAST_METRONOME_BEAT + 1, beat_index + 1):
                    _play_metronome_click(
                        passed_beat % settings.beats_per_bar == 0,
                        settings.metronome_volume,
                    )
                _LAST_METRONOME_BEAT = beat_index
        except (KeyError, ValueError, ZeroDivisionError, RuntimeError) as exc:
            _report_playback_error(exc)
            _LAST_METRONOME_BEAT = None

    _LAST_PLAYBACK_FRAME = frame


def _playback_timer():
    _sync_audio_and_metronome()
    return 0.03


def _report_playback_error(exc):
    global _LAST_PLAYBACK_ERROR
    message = str(exc)
    if message != _LAST_PLAYBACK_ERROR:
        print(f"BPM Timeline audio: {message}")
        _LAST_PLAYBACK_ERROR = message


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
    if not bpy.app.timers.is_registered(_playback_timer):
        bpy.app.timers.register(_playback_timer, first_interval=0.03, persistent=True)


def unregister():
    global _DRAW_HANDLE, _LAST_PLAYBACK_ERROR, _AUTO_AUDIO_ACTIVE
    stop_audio()
    reset_playback_sync()
    _LAST_PLAYBACK_ERROR = None
    _AUTO_AUDIO_ACTIVE = False
    if bpy.app.timers.is_registered(_playback_timer):
        bpy.app.timers.unregister(_playback_timer)
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceDopeSheetEditor.draw_handler_remove(_DRAW_HANDLE, "WINDOW")
        _DRAW_HANDLE = None
    if _refresh_editors in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_refresh_editors)
    invalidate_cache()
