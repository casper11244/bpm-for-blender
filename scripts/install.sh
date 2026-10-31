#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/bpm_timeline_audio_visualizer"
OUTPUT_DIR="$ROOT_DIR/build"
PACKAGE="$OUTPUT_DIR/bpm_timeline_audio_visualizer.zip"
BLENDER_BIN="${BLENDER_BIN:-$(command -v blender || true)}"

if [[ -z "$BLENDER_BIN" ]]; then
    echo "No se encontró Blender. Instálalo o define BLENDER_BIN=/ruta/a/blender." >&2
    exit 1
fi
if [[ ! -x "$BLENDER_BIN" ]]; then
    echo "El ejecutable Blender no existe o no tiene permisos: $BLENDER_BIN" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
"$BLENDER_BIN" --command extension build \
    --source-dir "$SOURCE_DIR" \
    --output-filepath "$PACKAGE"
"$BLENDER_BIN" --command extension install-file \
    -r user_default \
    --enable \
    "$PACKAGE"

printf 'Extensión instalada y activada.\nPaquete: %s\n' "$PACKAGE"
