"""Safe high-level keyframe insertion and explicit owned-key relocation."""

import json
import math


EPSILON = 1e-4


def _action_curves(obj):
    animation_data = obj.animation_data
    if animation_data is None or animation_data.action is None:
        return []

    action = animation_data.action
    slot = getattr(animation_data, "action_slot", None)
    if slot is None or not hasattr(action, "layers"):
        raise RuntimeError("No se puede inspeccionar con seguridad la Action/slot activa.")

    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type != "KEYFRAME":
                continue
            channelbag_lookup = getattr(strip, "channelbag", None)
            if channelbag_lookup is None:
                raise RuntimeError("La API de channelbag no está disponible.")
            channelbag = channelbag_lookup(slot)
            if channelbag is not None:
                curves.extend(channelbag.fcurves)
    return curves


def _curve_for(obj, data_path, array_index):
    for curve in _action_curves(obj):
        if curve.data_path == data_path and curve.array_index == array_index:
            return curve
    return None


def _has_key_at(curve, frame):
    return any(abs(point.co.x - frame) <= EPSILON for point in curve.keyframe_points)


def _existing_path_keys(obj, data_path, frame):
    for curve in _action_curves(obj):
        if curve.data_path == data_path and _has_key_at(curve, frame):
            return True
    return False


def _get_registry(settings):
    try:
        records = json.loads(settings.key_registry)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"El registro de keyframes no es válido: {exc}") from exc
    if not isinstance(records, list):
        raise RuntimeError("El registro de keyframes tiene un formato inesperado.")
    return records


def insert_keyframe(obj, scene, settings):
    if obj is None:
        raise ValueError("Selecciona un objeto activo para insertar el keyframe.")
    data_path = settings.data_path.strip()
    if not data_path:
        raise ValueError("Indica un data path de propiedad, por ejemplo location.")
    records = _get_registry(settings)

    if settings.keyframe_mode == "BPM":
        from .utils import calculated_keyframe

        target_frame = calculated_keyframe(scene, settings)
        anchor_step = settings.anchor_step
    else:
        target_frame = float(scene.frame_current)
        anchor_step = 0

    # Refuse to overwrite an existing key on any component of this property.
    if _existing_path_keys(obj, data_path, target_frame):
        raise ValueError(
            f"{data_path} ya tiene un keyframe en el frame {target_frame:.4f}; "
            "se cancela para no alterar una clave existente."
        )

    inserted = obj.keyframe_insert(data_path=data_path, frame=target_frame, group="BPM Visualizer")
    if not inserted:
        raise RuntimeError(f"Blender no pudo insertar keyframes para «{data_path}».")

    curves = [curve for curve in _action_curves(obj) if curve.data_path == data_path]
    points = []
    for curve in curves:
        point = next(
            (key for key in curve.keyframe_points if abs(key.co.x - target_frame) <= EPSILON),
            None,
        )
        if point is not None:
            points.append((curve.array_index, float(point.co.y)))
    if not points:
        raise RuntimeError(
            "El keyframe fue insertado, pero Blender no expuso sus channelbags para registrarlo."
        )

    for array_index, value in points:
        records.append({
            "object": obj.name_full,
            "data_path": data_path,
            "array_index": array_index,
            "frame": target_frame,
            "value": value,
            "anchor_step": anchor_step,
        })
    settings.key_registry = json.dumps(records, separators=(",", ":"))
    return target_frame, len(points)


def _matching_point(curve, frame, value):
    return next(
        (
            point for point in curve.keyframe_points
            if abs(point.co.x - frame) <= EPSILON and abs(point.co.y - value) <= EPSILON
        ),
        None,
    )


def _safe_move_point(curve, point, target):
    if abs(point.co.x - target) <= EPSILON:
        return True
    if _has_key_at(curve, target):
        return False

    points = list(curve.keyframe_points)
    index = points.index(point)
    if index and target <= points[index - 1].co.x + EPSILON:
        return False
    if index + 1 < len(points) and target >= points[index + 1].co.x - EPSILON:
        return False

    delta = target - point.co.x
    point.co.x = target
    point.handle_left.x += delta
    point.handle_right.x += delta
    return True


def reanchor_owned_keys(objects, scene, settings):
    from .utils import music_origin_frame, subdivision_step_frames

    records = _get_registry(settings)
    moved = 0
    skipped = 0
    updated = []

    for record in records:
        obj = objects.get(record.get("object", ""))
        if obj is None:
            skipped += 1
            continue
        try:
            curve = _curve_for(obj, record["data_path"], int(record["array_index"]))
        except (KeyError, RuntimeError, TypeError, ValueError):
            skipped += 1
            continue
        if curve is None:
            skipped += 1
            continue
        old_frame = float(record["frame"])
        value = float(record["value"])
        point = _matching_point(curve, old_frame, value)
        if point is None:
            skipped += 1
            continue

        target = music_origin_frame(scene, settings) + (
            int(record.get("anchor_step", 0)) * subdivision_step_frames(scene, settings)
        )
        if not math.isfinite(target) or not _safe_move_point(curve, point, target):
            skipped += 1
            continue

        record["frame"] = target
        moved += 1
        updated.append(record)

    settings.key_registry = json.dumps(records, separators=(",", ":"))
    return moved, skipped
