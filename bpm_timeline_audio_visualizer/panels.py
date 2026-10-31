"""Sidebar panels for timeline, keyframe, and audio controls."""

import bpy

from . import utils


class BPMAV_PT_timeline(bpy.types.Panel):
    bl_label = "BPM Timeline"
    bl_idname = "BPMAV_PT_timeline"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BPM Timeline"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bpmav_settings
        layout.prop(settings, "bpm")
        layout.prop(settings, "beat_unit")
        row = layout.row(align=True)
        row.prop(settings, "beats_per_bar")
        row.prop(settings, "duration_bars")
        layout.prop(settings, "offset_beats")

        box = layout.box()
        box.label(text="Subdivisiones")
        box.prop(settings, "enable_binary")
        box.prop(settings, "enable_ternary")
        box.prop(settings, "enable_tuplets")
        box.prop(settings, "marker_color")
        box.prop(settings, "division_color")
        row = layout.row(align=True)
        row.operator("bpmav.apply_divisions", icon="MARKER")
        row.operator("bpmav.clear_divisions", icon="TRASH")
        layout.operator("bpmav.test_settings", icon="CHECKMARK")


class BPMAV_PT_keyframes(bpy.types.Panel):
    bl_label = "Keyframes"
    bl_idname = "BPMAV_PT_keyframes"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BPM Timeline"
    bl_parent_id = "BPMAV_PT_timeline"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.bpmav_settings
        layout.prop(settings, "keyframe_mode")
        layout.prop(settings, "data_path")
        if settings.keyframe_mode == "BPM":
            layout.prop(settings, "key_subdivision")
            layout.prop(settings, "anchor_step")
            try:
                frame = utils.calculated_keyframe(scene, settings)
                layout.label(text=f"Se insertará en el frame {frame:.4f}")
            except (KeyError, ValueError, ZeroDivisionError) as exc:
                layout.label(text=str(exc), icon="ERROR")
        else:
            layout.label(text=f"Frame actual: {scene.frame_current}")
        layout.operator("bpmav.insert_keyframe", icon="KEY_HLT")
        layout.operator("bpmav.reanchor_owned_keys", icon="TIME")
        layout.label(text="Alcance: propiedad del objeto activo")


class BPMAV_PT_audio(bpy.types.Panel):
    bl_label = "Audio Visualizer"
    bl_idname = "BPMAV_PT_audio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BPM Timeline"
    bl_parent_id = "BPMAV_PT_timeline"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bpmav_settings
        layout.prop(settings, "audio_filepath")
        row = layout.row(align=True)
        row.operator("bpmav.load_audio", icon="FILE_FOLDER")
        row.operator("bpmav.reload_audio", icon="FILE_REFRESH")
        row = layout.row(align=True)
        row.operator("bpmav.play_audio", icon="PLAY")
        row.operator("bpmav.stop_audio", icon="PAUSE")
        layout.prop(settings, "audio_enabled")
        layout.prop(settings, "audio_height")
        layout.prop(settings, "audio_color")
        layout.prop(settings, "audio_volume")
        layout.label(text="Onda y subdivisiones siguen el zoom del Timeline.")
