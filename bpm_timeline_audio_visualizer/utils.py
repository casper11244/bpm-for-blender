"""Scene settings and shared musical-time helpers."""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)


NOTE_VALUES = {
    "WHOLE": 4.0,
    "HALF": 2.0,
    "QUARTER": 1.0,
    "EIGHTH": 0.5,
    "SIXTEENTH": 0.25,
}

SUBDIVISIONS = {
    "1": 1.0,
    "1/2": 0.5,
    "1/3": 1.0 / 3.0,
    "1/4": 0.25,
    "1/5": 0.2,
    "1/6": 1.0 / 6.0,
    "1/7": 1.0 / 7.0,
    "1/8": 0.125,
    "1/12": 1.0 / 12.0,
    "1/16": 1.0 / 16.0,
    "1/32": 1.0 / 32.0,
}


def scene_fps(scene):
    return scene.render.fps / scene.render.fps_base


def beat_seconds(settings):
    if settings.bpm <= 0.0:
        raise ValueError("BPM debe ser mayor que cero.")
    return 60.0 / settings.bpm * NOTE_VALUES[settings.beat_unit]


def music_origin_frame(scene, settings):
    return scene.frame_start + settings.offset_beats * beat_seconds(settings) * scene_fps(scene)


def subdivision_step_frames(scene, settings):
    return beat_seconds(settings) * SUBDIVISIONS[settings.key_subdivision] * scene_fps(scene)


def calculated_keyframe(scene, settings):
    return music_origin_frame(scene, settings) + (
        settings.anchor_step * subdivision_step_frames(scene, settings)
    )


def _update_audio_path(_self, _context):
    from . import audio_visualizer

    audio_visualizer.invalidate_cache()


class BPMAV_Settings(bpy.types.PropertyGroup):
    bpm: FloatProperty(
        name="BPM",
        description="Tempo in beats per minute",
        default=120.0,
        min=0.001,
        max=1000.0,
        precision=2,
    )
    beat_unit: EnumProperty(
        name="Unidad de pulso",
        description="Nota que representa un pulso a este BPM",
        items=(
            ("WHOLE", "Redonda", "Cuatro negras por pulso"),
            ("HALF", "Blanca", "Dos negras por pulso"),
            ("QUARTER", "Negra", "Una negra por pulso"),
            ("EIGHTH", "Corchea", "Media negra por pulso"),
            ("SIXTEENTH", "Semicorchea", "Un cuarto de negra por pulso"),
        ),
        default="QUARTER",
    )
    enable_binary: BoolProperty(name="Binarias", default=True)
    enable_ternary: BoolProperty(name="Tresillos", default=False)
    enable_tuplets: BoolProperty(name="Quintillos / septillos", default=False)
    beats_per_bar: IntProperty(name="Pulsos por compás", default=4, min=1, max=32)
    offset_beats: FloatProperty(
        name="Desfase (pulsos)", description="Desfase musical desde el frame inicial", default=0.0
    )
    duration_bars: IntProperty(name="Compases", default=8, min=1, max=256)
    keyframe_mode: EnumProperty(
        name="Modo de inserción",
        items=(
            ("FRAME", "Fotograma", "Insertar en el fotograma actual"),
            ("BPM", "BPM", "Insertar en el paso musical indicado"),
        ),
        default="FRAME",
    )
    key_subdivision: EnumProperty(
        name="Anclaje BPM",
        description="Fracción del pulso principal por paso",
        items=tuple((key, key, f"Cada {key} de pulso") for key in SUBDIVISIONS),
        default="1",
    )
    anchor_step: IntProperty(
        name="Índice del paso", description="Paso contado desde el origen musical", default=0
    )
    data_path: StringProperty(
        name="Propiedad del objeto",
        description="Data path de la propiedad que se insertará, por ejemplo location",
        default="location",
    )
    marker_registry: StringProperty(default="[]", options={"HIDDEN"})
    key_registry: StringProperty(default="[]", options={"HIDDEN"})
    audio_filepath: StringProperty(
        name="Archivo WAV",
        subtype="FILE_PATH",
        update=_update_audio_path,
    )
    audio_height: IntProperty(name="Alto overlay", default=90, min=30, max=240)
    audio_color: FloatVectorProperty(
        name="Color de onda",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.15, 0.75, 0.95),
    )
    audio_enabled: BoolProperty(name="Mostrar overlay", default=True)
