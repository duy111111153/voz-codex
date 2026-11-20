# Arquitectura

Voz Codex se divide en procesos pequeños para que la respuesta de voz no bloquee la captura ni el historial.

1. Handy ejecuta `handy/transcription` cuando termina una transcripción.
2. `voz_codex/service.py` recibe la consulta por un socket local privado.
3. `history.py` guarda la interacción en SQLite con WAL y actualiza el grafo incremental.
4. `codex.py` usa el Codex App Server y conserva el `threadId` real.
5. `speech.py` limpia Markdown, emojis y enlaces, transforma números y unidades a texto natural y envía la frase al sintetizador.
6. `omarchy/local.voz-tracker` lee `task.json` y muestra el estado en la barra.

Los datos de ejecución están en `$XDG_DATA_HOME/voz-codex` y `$XDG_RUNTIME_DIR/voz-codex`. No se escriben credenciales ni conversaciones en el repositorio.

## Rendimiento

Kokoro se mantiene precalentado, las frases se sintetizan en bloques y el servicio publica solo resúmenes de progreso. El historial y Graphify usan SQLite local para evitar embeddings o llamadas adicionales por cada interacción.

## Permisos

La integración instalada para el usuario puede usar `approvalPolicy=never` y `dangerFullAccess` cuando el usuario lo solicita. Esa opción permite ejecutar comandos y modificar archivos sin confirmaciones. Revisa el código antes de activarla en equipos compartidos.
