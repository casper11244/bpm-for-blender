# BPM Timeline & Audio Visualizer

Extensión de Blender 5.0+ para crear marcas musicales, insertar keyframes en
fotograma o por BPM y mostrar una forma de onda WAV en el Viewport 3D.

## Instalación

1. Descarga o clona este repositorio.
2. Comprime la carpeta `bpm_timeline_audio_visualizer/` conservando
   `blender_manifest.toml` en la raíz del ZIP. No incluyas la carpeta `.git`.
3. En Blender 5.0 o posterior, abre **Edit > Preferences > Get Extensions** y
   usa **Install from Disk** para seleccionar el ZIP.
4. Activa **BPM Timeline & Audio Visualizer**. El panel aparece en el
   **3D Viewport > Sidebar (N) > BPM Timeline**.

También se puede instalar la carpeta del paquete con las herramientas de
desarrollo de Extensions de Blender. `blender_manifest.toml` es la fuente de
metadatos y declara `blender_version_min = "5.0.0"`.

## Marcas musicales

- Define BPM, unidad de pulso, pulsos por compás, número de compases y desfase
  inicial en pulsos. El origen musical es `scene.frame_start` más ese desfase.
- BPM predeterminado es 120; la negra es la unidad predeterminada. Se usa el
  FPS efectivo de la escena (`fps / fps_base`).
- Activa subdivisiones binarias, tresillos y/o quintillos-septillos y pulsa
  **Aplicar divisiones**. Las marcas se nombran `BPMAV|P|...` (pulso) y
  `BPMAV|S|...` (subdivisión). `bpy.types.TimelineMarker` no ofrece color
  individual, por lo que la distinción se hace por nombre.
- **Limpiar divisiones** elimina únicamente los nombres registrados por esta
  extensión. Las marcas existentes de otros usos se conservan.
- **Probar configuración** informa duración del pulso en segundos y frames.

Blender guarda las marcas de timeline en frames enteros. Si el pulso/subdivisión
cae entre frames, la marca visual se redondea al frame más cercano; el cálculo
de keyframes BPM conserva su posición fraccionaria.

## Inserción de keyframes

El modo y el data path se eligen en el panel **Keyframes**. El alcance es la
propiedad indicada del objeto activo (por ejemplo, `location`, `rotation_euler`,
`scale` o un data path de propiedad personalizada válido); no opera sobre una
selección completa ni sobre canales aislados del editor.

- **Fotograma** llama a `obj.keyframe_insert(data_path=..., frame=scene.frame_current)`.
- **BPM** calcula el frame desde BPM, unidad, FPS, desfase, subdivisión e índice
  del paso. El resultado exacto se muestra antes de insertar y se usa sin
  redondeo.
- Se cancela la inserción si la propiedad ya tiene una clave en ese frame: así
  no se reemplaza una clave preexistente. Las claves creadas se registran en la
  escena junto con objeto, data path, canal, frame y valor.
- Cambiar modo, BPM, unidad, desfase o subdivisión nunca mueve ni borra claves.
  Una clave BPM queda en su frame de creación. El único comando para reubicar
  claves registradas es **Reubicar keyframes de la extensión**, una acción
  manual separada con confirmación; también conserva las claves de usuario.
- La reubicación omite claves ausentes o editadas desde su creación, conflictos
  de destino y movimientos que cambiarían el orden de claves en una F-Curve.
  Solo trabaja sobre acciones de objeto con slots/canales accesibles en el
  modelo de Actions de Blender 5.0+.

Se usan F-Curves vía `action.layers`, strips, `strip.channelbag(slot)` y
`channelbag.fcurves` únicamente para detectar colisiones/rastrear y reubicar
claves registradas. La inserción normal usa la API de alto nivel
`obj.keyframe_insert`; no se usa `action.fcurves`.

## Visualizador de audio

Selecciona un WAV PCM sin compresión con **Cargar WAV**. La forma de onda
resumida se cachea y se dibuja como overlay POST_PIXEL en la franja inferior del
**Viewport 3D**; la línea amarilla sigue el tiempo de la escena con el frame
actual. **Recargar WAV** invalida la caché explícitamente. Color y altura son
configurables.

La API pública de Blender no expone una región propia para dibujar dentro de la
parte inferior del editor Timeline. Por eso el visualizador no pretende
insertarse en ese editor: usa el overlay de `SpaceView3D` como alternativa
documentada. No modifica la inserción de keyframes. Se decodifican WAV PCM de 8,
16, 24 o 32 bits con `wave` y NumPy; otros formatos/códecs no se convierten.
La decodificación se resume en 512 bloques y se cachea por ruta mientras dure
la sesión. No hay reproducción de audio.

## Limitaciones y compatibilidad

- Requiere Blender 5.0 o posterior. El paquete no depende de
  `TIME_MT_marker`, `bgl`, ni del antiguo `action.fcurves`.
- Referencias oficiales: [Extensions manifest](https://docs.blender.org/manual/en/5.0/advanced/extensions/getting_started.html),
  [Action API](https://docs.blender.org/api/5.0/bpy.types.Action.html),
  [ActionKeyframeStrip API](https://docs.blender.org/api/5.0/bpy.types.ActionKeyframeStrip.html),
  [GPU API](https://docs.blender.org/api/5.0/gpu.html) y
  [Object.keyframe_insert](https://docs.blender.org/api/5.0/bpy.types.bpy_struct.html#bpy.types.bpy_struct.keyframe_insert).
- Las marcas de `scene.timeline_markers` son enteras y no soportan color
  individual desde esta API.
- La inserción solo admite un objeto activo y un `data_path` introducido por el
  usuario; el path debe ser válido para ese objeto.
- El registro de claves es metadato de escena. Si se elimina la escena o se
  pierde el registro, la extensión no intenta adivinar qué claves son propias.
- WAV inválido, PCM comprimido, ausencia de objeto y colisiones producen un
  mensaje de error y cancelan la operación afectada.

## Pruebas manuales / criterios de aceptación

1. Instala y activa el ZIP en Blender 5.0+; verifica que no hay excepción y que
   aparece el panel. El registro no consulta `TIME_MT_marker`.
2. Con FPS 24, BPM 120, negra, offset 0: aplica marcas y verifica pulsos cada
   12 frames (0,5 s); cambia FPS a 30 y verifica 15 frames.
3. Activa solo binarias, después tresillos y finalmente ambas; vuelve a aplicar
   y comprueba `P`/`S` y los intervalos correspondientes.
4. Crea marcas manuales ajenas, limpia divisiones y comprueba que solo se
   eliminan las registradas por el addon; comprueba que ningún keyframe cambia.
5. Inserta una marca ajena con nombre similar y verifica que no la elimina la
   limpieza. Prueba un rango grande y verifica el límite de seguridad de 5000.
6. Carga un WAV PCM válido: la forma de onda debe aparecer en la parte inferior
   del Viewport y el cursor debe seguir el frame. Sin WAV, el addon debe seguir
   funcionando. Prueba archivo ausente, corrupto y formato comprimido.
7. En modo Fotograma, inserta `location` y comprueba que todos sus canales
   aparecen en el frame actual.
8. En modo BPM con 120 BPM, negra, FPS 24, subdivisión `1` e índice 4, verifica
   que la vista previa e inserción indican frame 48.
9. Anota posiciones de claves manuales; cambia de modo, BPM, subdivisión y
   desfase, vuelve a insertar en otros frames y comprueba que las antiguas no
   se mueven ni desaparecen.
10. Intenta insertar encima de una clave existente: la operación debe cancelarse
    en lugar de reemplazarla. Ejecuta **Reubicar keyframes de la extensión**
    explícitamente y verifica que solo mueve claves rastreadas, omitiendo
    conflictos y claves cuyo valor ya se editó.
