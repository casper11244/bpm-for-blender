"""User-facing operators."""

import bpy
from bpy.props import StringProperty

from . import audio_visualizer, keyframe_modes, timeline_divisions, utils


class BPMAV_OT_apply_divisions(bpy.types.Operator):
    bl_idname = "bpmav.apply_divisions"
    bl_label = "Aplicar divisiones"
    bl_description = "Crear marcas para pulsos y subdivisiones musicales"

    def execute(self, context):
        try:
            count = timeline_divisions.apply_divisions(
                context.scene, context.scene.bpmav_settings
            )
        except (ValueError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        utils.redraw_timeline_editors()
        self.report({"INFO"}, f"Se crearon {count} marcas musicales.")
        return {"FINISHED"}


class BPMAV_OT_clear_divisions(bpy.types.Operator):
    bl_idname = "bpmav.clear_divisions"
    bl_label = "Limpiar divisiones"
    bl_description = "Eliminar exclusivamente las marcas creadas por esta extensión"

    def execute(self, context):
        try:
            removed = timeline_divisions.clear_owned_markers(
                context.scene, context.scene.bpmav_settings
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        utils.redraw_timeline_editors()
        self.report({"INFO"}, f"Se eliminaron {removed} marcas de la extensión.")
        return {"FINISHED"}


class BPMAV_OT_test_settings(bpy.types.Operator):
    bl_idname = "bpmav.test_settings"
    bl_label = "Probar configuración"
    bl_description = "Validar el tempo y mostrar la conversión de pulso a fotogramas"

    def execute(self, context):
        settings = context.scene.bpmav_settings
        try:
            seconds = utils.beat_seconds(settings)
            frames = seconds * utils.scene_fps(context.scene)
            if settings.duration_bars < 1 or settings.beats_per_bar < 1:
                raise ValueError("El rango de compases debe ser mayor que cero.")
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Pulso: {seconds:.4f} s / {frames:.4f} frames; rango válido.",
        )
        return {"FINISHED"}


class BPMAV_OT_insert_keyframe(bpy.types.Operator):
    bl_idname = "bpmav.insert_keyframe"
    bl_label = "Insertar keyframe"
    bl_description = "Insertar solo el keyframe de la propiedad indicada"

    def execute(self, context):
        try:
            frame, count = keyframe_modes.insert_keyframe(
                context.active_object, context.scene, context.scene.bpmav_settings
            )
        except (RuntimeError, ValueError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"{count} canal(es) insertado(s) en el frame {frame:.4f}.",
        )
        return {"FINISHED"}


class BPMAV_OT_reanchor_keys(bpy.types.Operator):
    bl_idname = "bpmav.reanchor_owned_keys"
    bl_label = "Reubicar keyframes de la extensión"
    bl_description = "Mover manualmente los keyframes registrados al BPM configurado"

    def invoke(self, context, _event):
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context):
        settings = context.scene.bpmav_settings
        try:
            moved, skipped = keyframe_modes.reanchor_owned_keys(
                bpy.data.objects, context.scene, settings
            )
        except (RuntimeError, ValueError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Reubicados: {moved}; omitidos por seguridad o ausencia: {skipped}.",
        )
        return {"FINISHED"}


class BPMAV_OT_load_audio(bpy.types.Operator):
    bl_idname = "bpmav.load_audio"
    bl_label = "Cargar WAV"
    bl_description = "Seleccionar un archivo WAV PCM para visualizar su forma de onda"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.wav", options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.bpmav_settings
        settings.audio_filepath = self.filepath
        try:
            audio_visualizer.load_waveform(self.filepath)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({"INFO"}, "Forma de onda WAV cargada y cacheada.")
        return {"FINISHED"}

    def invoke(self, context, _event):
        self.filepath = context.scene.bpmav_settings.audio_filepath
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class BPMAV_OT_reload_audio(bpy.types.Operator):
    bl_idname = "bpmav.reload_audio"
    bl_label = "Recargar WAV"
    bl_description = "Invalidar la caché y volver a decodificar el archivo WAV"

    def execute(self, context):
        settings = context.scene.bpmav_settings
        if not settings.audio_filepath:
            self.report({"ERROR"}, "No hay un archivo de audio seleccionado.")
            return {"CANCELLED"}
        audio_visualizer.invalidate_cache()
        try:
            audio_visualizer.load_waveform(settings.audio_filepath)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({"INFO"}, "Forma de onda recargada.")
        return {"FINISHED"}


class BPMAV_OT_play_audio(bpy.types.Operator):
    bl_idname = "bpmav.play_audio"
    bl_label = "Reproducir WAV"
    bl_description = "Reproducir el WAV desde la posición temporal del frame actual"

    def execute(self, context):
        scene = context.scene
        settings = scene.bpmav_settings
        if not settings.audio_filepath:
            self.report({"ERROR"}, "Selecciona un archivo WAV primero.")
            return {"CANCELLED"}
        try:
            _minimum, _maximum, duration = audio_visualizer.load_waveform(
                settings.audio_filepath
            )
            fps = utils.scene_fps(scene)
            start_seconds = (
                scene.frame_current
                - scene.frame_start
                - settings.audio_offset_frames
            ) / fps
            if start_seconds < 0.0 or start_seconds >= duration:
                raise ValueError("El frame actual queda fuera de la duración del WAV.")
            audio_visualizer.play_audio(
                settings.audio_filepath,
                start_seconds=start_seconds,
                volume=settings.audio_volume,
            )
        except (OSError, RuntimeError, ValueError, ZeroDivisionError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        audio_visualizer.reset_playback_sync()
        self.report({"INFO"}, "Reproduciendo WAV desde la posición del frame actual.")
        return {"FINISHED"}


class BPMAV_OT_stop_audio(bpy.types.Operator):
    bl_idname = "bpmav.stop_audio"
    bl_label = "Detener audio"
    bl_description = "Detener la reproducción WAV iniciada por la extensión"

    def execute(self, _context):
        audio_visualizer.stop_audio()
        audio_visualizer.reset_playback_sync()
        self.report({"INFO"}, "Reproducción detenida.")
        return {"FINISHED"}


class BPMAV_OT_move_audio(bpy.types.Operator):
    bl_idname = "bpmav.move_audio"
    bl_label = "Mover audio en Timeline"
    bl_description = "Arrastra horizontalmente en el Timeline para cambiar el inicio de la pista"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.area is None or context.area.type != "DOPESHEET_EDITOR":
            self.report({"ERROR"}, "Inicia este operador desde la barra lateral del Timeline.")
            return {"CANCELLED"}
        self._region = next(
            (region for region in context.area.regions if region.type == "WINDOW"),
            None,
        )
        if self._region is None:
            self.report({"ERROR"}, "No se encontró la región de frames del Timeline.")
            return {"CANCELLED"}
        self._settings = context.scene.bpmav_settings
        self._initial_offset = self._settings.audio_offset_frames
        self._dragging = False
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "Haz clic y arrastra en el área de frames; Esc cancela.")
        return {"RUNNING_MODAL"}

    def _frame_at_mouse(self, window_x):
        region_x = window_x - self._region.x
        return self._region.view2d.region_to_view(region_x, 0)[0]

    def modal(self, context, event):
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            inside_x = self._region.x <= event.mouse_x <= self._region.x + self._region.width
            inside_y = self._region.y <= event.mouse_y <= self._region.y + self._region.height
            if inside_x and inside_y:
                self._dragging = True
                self._initial_mouse_frame = self._frame_at_mouse(event.mouse_x)
                self._initial_offset = self._settings.audio_offset_frames
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            if not self._dragging:
                return {"RUNNING_MODAL"}
            current_mouse_frame = self._frame_at_mouse(event.mouse_x)
            self._settings.audio_offset_frames = (
                self._initial_offset + current_mouse_frame - self._initial_mouse_frame
            )
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._dragging:
            self._dragging = False
            return {"FINISHED"}
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._settings.audio_offset_frames = self._initial_offset
            context.area.tag_redraw()
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}
