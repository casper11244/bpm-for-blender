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


def redraw_timeline_editors():
    window_manager = bpy.context.window_manager
    if window_manager is None:
        return
    for window in window_manager.windows:
        if window.screen is None:
            continue
        for area in window.screen.areas:
            if area.type == "DOPESHEET_EDITOR":
                area.tag_redraw()


def _update_timeline(_self, _context):
    redraw_timeline_editors()


def _update_audio_path(_self, _context):
    from . import audio_visualizer

    audio_visualizer.stop_audio()
    audio_visualizer.reset_playback_sync()
    audio_visualizer.invalidate_cache()
    redraw_timeline_editors()


def _update_audio_volume(self, _context):
    from . import audio_visualizer

    audio_visualizer.set_audio_volume(self.audio_volume)


def _update_audio_offset(_self, _context):
    from . import audio_visualizer

    audio_visualizer.update_audio_offset()
    redraw_timeline_editors()


def _update_snap_to_music(self, context):
    if context is None or context.scene is None:
        return
    tool_settings = context.scene.tool_settings
    if self.snap_to_music:
        self.snap_previous_enabled = tool_settings.use_snap_anim
        self.snap_previous_element = tool_settings.snap_anim_element
        tool_settings.use_snap_anim = True
        tool_settings.snap_anim_element = "MARKER"
    else:
        tool_settings.use_snap_anim = self.snap_previous_enabled
        tool_settings.snap_anim_element = self.snap_previous_element


def restore_snap_settings(scene):
    if not hasattr(scene, "bpmav_settings"):
        return
    settings = scene.bpmav_settings
    if settings.snap_to_music:
        tool_settings = scene.tool_settings
        tool_settings.use_snap_anim = settings.snap_previous_enabled
        tool_settings.snap_anim_element = settings.snap_previous_element


class BPMAV_Settings(bpy.types.PropertyGroup):
    bpm: FloatProperty(
        name="BPM",
        description="Tempo in beats per minute",
        default=120.0,
        min=0.001,
        max=1000.0,
        precision=2,
        update=_update_timeline,
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
        update=_update_timeline,
    )
    enable_binary: BoolProperty(name="Binarias", default=True, update=_update_timeline)
    enable_ternary: BoolProperty(name="Tresillos", default=False, update=_update_timeline)
    enable_tuplets: BoolProperty(
        name="Quintillos / septillos", default=False, update=_update_timeline
    )
    beats_per_bar: IntProperty(
        name="Pulsos por compás", default=4, min=1, max=32, update=_update_timeline
    )
    offset_beats: FloatProperty(
        name="Desfase (pulsos)",
        description="Desfase musical desde el frame inicial",
        default=0.0,
        update=_update_timeline,
    )
    duration_bars: IntProperty(
        name="Compases", default=8, min=1, max=256, update=_update_timeline
    )
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
    marker_color: FloatVectorProperty(
        name="Color de pulso",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 0.45, 0.08),
        update=_update_timeline,
    )
    division_color: FloatVectorProperty(
        name="Color de subdivisión",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.2, 0.65, 1.0),
        update=_update_timeline,
    )
    audio_filepath: StringProperty(
        name="Archivo WAV",
        subtype="FILE_PATH",
        update=_update_audio_path,
    )
    audio_height: IntProperty(
        name="Alto overlay", default=90, min=30, max=240, update=_update_timeline
    )
    audio_color: FloatVectorProperty(
        name="Color de onda",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.15, 0.75, 0.95),
        update=_update_timeline,
    )
    audio_volume: FloatProperty(
        name="Volumen", default=1.0, min=0.0, max=1.0, update=_update_audio_volume
    )
    audio_enabled: BoolProperty(
        name="Mostrar overlay", default=True, update=_update_timeline
    )
    audio_offset_frames: FloatProperty(
        name="Inicio de audio (frame)",
        description="Frame de inicio de la pista de audio",
        default=0.0,
        update=_update_audio_offset,
    )
    sync_audio_to_playback: BoolProperty(
        name="Audio con Play de Blender",
        description="Iniciar y detener el audio junto con la reproducción de la animación",
        default=True,
    )
    metronome_enabled: BoolProperty(
        name="Metrónomo durante Play", default=False
    )
    metronome_volume: FloatProperty(name="Volumen metrónomo", default=0.7, min=0.0, max=1.0)
    snap_to_music: BoolProperty(
        name="Imán prioriza marcas BPM",
        description="Configurar el imán de animación para ajustar a marcas y divisiones BPM, no a keyframes",
        default=False,
        update=_update_snap_to_music,
    )
    snap_previous_enabled: BoolProperty(default=False, options={"HIDDEN"})
    snap_previous_element: EnumProperty(
        items=(
            ("FRAME", "Frame", ""),
            ("SECOND", "Second", ""),
            ("MARKER", "Marker", ""),
        ),
        default="FRAME",
        options={"HIDDEN"},
    )
