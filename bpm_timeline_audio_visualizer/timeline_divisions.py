"""Creation and cleanup of extension-owned timeline markers."""

import json
import uuid

from . import utils


MAX_MARKERS = 5000


def _enabled_fractions(settings):
    fractions = []
    if settings.enable_binary:
        fractions.extend(("1/2", "1/4", "1/8", "1/16", "1/32"))
    if settings.enable_ternary:
        fractions.extend(("1/3", "1/6", "1/12"))
    if settings.enable_tuplets:
        fractions.extend(("1/5", "1/7"))
    return sorted({utils.SUBDIVISIONS[item] for item in fractions}, reverse=True)


def clear_owned_markers(scene, settings):
    try:
        owned_names = set(json.loads(settings.marker_registry))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"El registro de marcas no es válido: {exc}") from exc

    removed = 0
    for marker in list(scene.timeline_markers):
        if marker.name in owned_names:
            scene.timeline_markers.remove(marker)
            removed += 1
    settings.marker_registry = "[]"
    return removed


def apply_divisions(scene, settings):
    if settings.bpm <= 0.0:
        raise ValueError("BPM debe ser mayor que cero.")
    if settings.beats_per_bar <= 0 or settings.duration_bars <= 0:
        raise ValueError("El compás y la duración deben ser mayores que cero.")

    start = utils.music_origin_frame(scene, settings)
    beat_frames = utils.beat_seconds(settings) * utils.scene_fps(scene)
    if beat_frames <= 0.0:
        raise ValueError("La duración del pulso calculada no es válida.")
    beats = settings.beats_per_bar * settings.duration_bars
    fractions = _enabled_fractions(settings)

    marker_count = beats * (
        1 + sum(max(0, round(1.0 / fraction) - 1) for fraction in fractions)
    )
    if marker_count > MAX_MARKERS:
        raise ValueError(f"El rango generaría {marker_count} marcas; el límite es {MAX_MARKERS}.")

    clear_owned_markers(scene, settings)
    batch_id = uuid.uuid4().hex[:8]
    names = []
    occupied_frames = {marker.frame for marker in scene.timeline_markers}
    for beat_index in range(beats):
        frame = round(start + beat_index * beat_frames)
        if frame not in occupied_frames:
            name = f"BPMAV|P|{batch_id}|{beat_index + 1:04d}"
            scene.timeline_markers.new(name, frame=frame)
            names.append(name)
            occupied_frames.add(frame)

        for fraction in fractions:
            subdivisions = round(1.0 / fraction)
            for step in range(1, subdivisions):
                position = start + (beat_index + step * fraction) * beat_frames
                sub_frame = round(position)
                if sub_frame in occupied_frames:
                    continue
                name = f"BPMAV|S|{batch_id}|{beat_index + 1:04d}-{step:02d}"
                scene.timeline_markers.new(name, frame=sub_frame)
                names.append(name)
                occupied_frames.add(sub_frame)

    settings.marker_registry = json.dumps(names)
    return len(names)
