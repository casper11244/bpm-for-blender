"""BPM Timeline & Audio Visualizer Blender Extension."""

bl_info = {
    "name": "BPM Timeline & Audio Visualizer",
    "author": "BPM Timeline & Audio Visualizer contributors",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > BPM Timeline",
    "description": "Musical timeline divisions, safe keyframes, and audio waveform",
    "category": "Animation",
}

import bpy

from . import audio_visualizer, operators, panels, utils


_CLASSES = (
    utils.BPMAV_Settings,
    operators.BPMAV_OT_apply_divisions,
    operators.BPMAV_OT_clear_divisions,
    operators.BPMAV_OT_test_settings,
    operators.BPMAV_OT_insert_keyframe,
    operators.BPMAV_OT_reanchor_keys,
    operators.BPMAV_OT_load_audio,
    operators.BPMAV_OT_reload_audio,
    panels.BPMAV_PT_timeline,
    panels.BPMAV_PT_keyframes,
    panels.BPMAV_PT_audio,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.bpmav_settings = bpy.props.PointerProperty(type=utils.BPMAV_Settings)
    audio_visualizer.register()


def unregister():
    audio_visualizer.unregister()
    if hasattr(bpy.types.Scene, "bpmav_settings"):
        del bpy.types.Scene.bpmav_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
