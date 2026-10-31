# BPM Timeline & Audio Visualizer

Extensión de Blender 5.0+ para divisiones musicales, keyframes seguros,
visualización de audio sincronizada con el zoom del Timeline y reproducción WAV.

## Descarga e instalación automática

Instala Blender 5.0+ desde [blender.org/download](https://www.blender.org/download/)
y Git desde [git-scm.com](https://git-scm.com/downloads), si aún no están
instalados. Abre una terminal en la ubicación deseada:

```bash
git clone <URL_DEL_REPOSITORIO>
cd "Bpm dor blender"
```

El repositorio debe incluir `bpm_timeline_audio_visualizer/` y `scripts/`.
Los scripts empaquetan, instalan y activan la extensión en el repositorio de
usuario de Blender mediante `blender --command extension`. Blender debe estar
instalado; estos scripts no instalan el programa Blender.

**Linux (bash):**

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

Si Blender no está en `PATH`:

```bash
BLENDER_BIN="/ruta/a/blender" ./scripts/install.sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Si Blender no se detecta automáticamente:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -BlenderPath "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

El paquete se genera en `build/bpm_timeline_audio_visualizer.zip`; el script lo
instala y activa. Para instalarlo manualmente, en Blender elige
**Edit > Preferences > Get Extensions > Install from Disk**, abre el ZIP y
activa la extensión. Los controles aparecen en **3D Viewport > Sidebar (N) >
BPM Timeline**. La onda y la rejilla se dibujan en la franja inferior del editor
Timeline/Dope Sheet.

Si Blender ya estaba abierto durante la instalación, ciérralo y vuelve a
iniciarlo para que cargue la extensión.

`blender_manifest.toml` es la fuente de metadatos de la extensión y declara
`blender_version_min = "5.0.0"`.

## Marcas y rejilla musical

- Configura BPM (predeterminado 120), unidad de pulso (negra por defecto),
  pulsos por compás, duración en compases y desfase desde `scene.frame_start`.
- El FPS efectivo se calcula como `fps / fps_base`. A 120 BPM con negra, cada
  pulso dura 0,5 segundos.
- Activa divisiones binarias, tresillos y/o quintillos-septillos y pulsa
  **Aplicar divisiones**. **Limpiar divisiones** elimina exclusivamente marcas
  registradas por esta extensión.
- En el overlay del Timeline, pulsos y subdivisiones se dibujan en colores
  separados y sus posiciones conservan fracciones de frame. El overlay se
  actualiza al cambiar el rango visible/zoom del editor y respeta el número de
  compases configurado. La rejilla no modifica ningún keyframe.
- Las marcas de `scene.timeline_markers` se guardan en frames enteros. Si una
  división cae entre frames, la marca nativa se redondea al frame más cercano;
  la rejilla de pantalla, en cambio, conserva la posición subframe exacta.
- **Probar configuración** muestra el tiempo y frames que dura un pulso.

## Inserción de keyframes

El panel **Keyframes** trabaja con la propiedad indicada del objeto activo
(por ejemplo `location`, `rotation_euler`, `scale` o un data path válido).
No opera sobre toda la selección ni sobre canales aislados del editor.

- **Fotograma** inserta en `scene.frame_current`.
- **BPM** calcula el frame con BPM, unidad, FPS, offset, subdivisión e índice de
  paso. El resultado se muestra antes de insertar y no se redondea.
- Si ya existe una clave para esa propiedad en el frame destino, cancela en vez
  de reemplazarla. Las claves nuevas se registran con objeto, canal, frame y
  valor.
- Cambiar modo, BPM, unidad, subdivisión o desfase nunca mueve ni borra claves.
  Las claves creadas en modo BPM permanecen en el frame donde se insertaron.
- La única reubicación disponible es el operador manual **Reubicar keyframes de
  la extensión**, con confirmación. Solo actúa sobre claves registradas que
  sigan coincidiendo con el frame y valor registrados; omite conflictos,
  claves cambiadas o movimientos que alteren el orden de la curva.

La inserción usa `obj.keyframe_insert`. Para comprobar y reubicar claves se
accede a `action.layers`, strips, `strip.channelbag(slot)` y
`channelbag.fcurves` del modelo de Actions de Blender 5.0+; no se usa el antiguo
`action.fcurves`.

## Audio: onda y reproducción

1. Abre un editor Timeline/Dope Sheet.
2. En **Audio Visualizer**, pulsa **Cargar WAV** y selecciona WAV PCM sin
   compresión. La onda aparece como una envolvente rellena en el color
   configurado, mostrando amplitudes positivas y negativas; no es una línea
   decorativa uniforme.
3. Haz zoom o pan en el Timeline: la onda corresponde al rango de frames
   visible y la línea amarilla sigue el frame actual.
4. En la pestaña **BPM Audio** del sidebar del Timeline, pulsa **Mover audio en
   Timeline** y después haz clic y arrastra horizontalmente dentro del área de
   frames. La posición inicial de la onda cambia según el movimiento; suelta
   para confirmar o pulsa Esc para cancelar. También puedes escribir
   **Inicio de audio (frame)** manualmente.
5. Activa **Audio con Play de Blender** para iniciar/parar automáticamente la
   música al reproducir/detener la animación con los controles estándar de
   Blender. La pista se alinea al frame actual y respeta su inicio desplazado.
   **Reproducir WAV** permite iniciar manualmente desde el frame; controla el
   nivel con **Volumen** y usa **Detener audio** para parar. **Recargar WAV**
   invalida y vuelve a crear la caché.
6. Activa **Metrónomo durante Play** para oír un clic en cada pulso mientras
   Blender reproduce la animación. El primer pulso del compás usa un tono más
   agudo y fuerte. Está desactivado por defecto y tiene control de volumen.

La opción **Imán prioriza marcas BPM** está en el panel Keyframes. Al activarla,
configura el ajuste de animación de Blender para usar marcas (en vez de
keyframes) como objetivo del imán. Aplica primero las divisiones para crear
marcas BPM. Desactívala para restaurar el ajuste de imán anterior. Blender solo
puede ajustar el imán nativo a marcas enteras; la rejilla visual mantiene sus
posiciones fraccionarias, pero las marcas nativas siguen redondeadas.

La reproducción usa `aud.Device` de Blender y la salida de audio del sistema.
Si no se escucha, comprueba el dispositivo de salida, el volumen del sistema,
el volumen del panel y que el frame actual caiga dentro de la duración del
archivo. La opción de reproducción automática observa el estado de Play de
Blender con un timer de baja frecuencia. El audio se inicia al detectar playback
y se detiene al pausar/parar. La sincronización no corrige continuamente
fluctuaciones de FPS ni audio externo ya en reproducción.

Se admiten WAV PCM de 8, 16, 24 y 32 bits. WAV comprimido, archivos corruptos y
otros formatos no se convierten. La envolvente de amplitud se calcula por
bloques y se cachea por archivo para limitar el trabajo en la interfaz.
No se dibuja dentro del editor Timeline como una región propia (la API pública
no ofrece tal región); se utiliza un overlay POST_PIXEL del editor
`SpaceDopeSheetEditor`, que sigue su rango visible.

## Limitaciones y referencias

- Requiere Blender 5.0 o posterior. No depende de `TIME_MT_marker`, `bgl` ni
  `action.fcurves`.
- Las marcas nativas del timeline son enteras y no admiten color individual.
  El overlay aporta colores y posiciones fraccionarias.
- El modo de inserción solo admite un objeto activo y un data path válido.
- El registro de claves es metadato de escena. Si se elimina, no se intenta
  adivinar ni modificar claves.
- Referencias: [Extensions manifest](https://docs.blender.org/manual/en/5.0/advanced/extensions/getting_started.html),
  [Action API](https://docs.blender.org/api/5.0/bpy.types.Action.html),
  [ActionKeyframeStrip API](https://docs.blender.org/api/5.0/bpy.types.ActionKeyframeStrip.html),
  [GPU API](https://docs.blender.org/api/5.0/gpu.html),
  [Object.keyframe_insert](https://docs.blender.org/api/5.0/bpy.types.bpy_struct.html#bpy.types.bpy_struct.keyframe_insert).

## Pruebas manuales / criterios de aceptación

1. Ejecuta el script de instalación del sistema operativo, verifica que instala
   y activa la extensión, y comprueba que el panel aparece sin excepciones.
2. A 24 FPS, 120 BPM, negra y offset 0, verifica pulsos cada 12 frames; cambia a
   30 FPS y verifica intervalos de 15 frames. La posición inicial sigue
   `scene.frame_start`.
3. Activa/desactiva binarias y ternarias; comprueba el cambio de marcas y de
   colores en la rejilla del editor.
4. Haz zoom/pan en Timeline y comprueba que la forma de onda se ajusta al rango
   visible, la rejilla mantiene el ritmo y el cursor sigue el frame actual.
5. Arrastra la onda con **Mover audio en Timeline**; verifica que el inicio y
   playback cambian con el desplazamiento, y que Esc cancela.
6. Activa/desactiva **Audio con Play de Blender** y prueba Play/Pause/Stop con
   metrónomo encendido y apagado. El metrónomo debe sonar solo durante Play.
7. Activa **Imán prioriza marcas BPM**, aplica divisiones y comprueba que el
   modo de ajuste de animación cambia a marcas y se restaura al desactivar.
8. Crea marcas manuales, regenera y limpia divisiones; solo deben eliminarse
   las marcas del addon y ningún keyframe debe cambiar.
9. Carga un WAV válido, reproduce desde distintos frames, cambia volumen y
   detén. Comprueba el dispositivo de salida del sistema. Prueba WAV ausente,
   corrupto y comprimido; Blender debe seguir funcionando y mostrar errores.
10. En modo Fotograma, comprueba que `location` se inserta en el frame actual.
   En modo BPM, con `scene.frame_start = 0`, 120 BPM, FPS 24, negra,
   subdivisión `1` e índice 4, comprueba que la previsualización y la inserción
   dan frame 48.
11. Cambia de modo/BPM/subdivisión/offset tras insertar claves y verifica que
   ninguna clave previa se mueve o desaparece. Intenta insertar encima de una
   clave existente: debe cancelarse. Prueba la reubicación manual y confirma
   que omite claves ajenas, editadas o en conflicto.
