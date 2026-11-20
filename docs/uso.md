# Uso

El icono de terminal de Voz Codex en la barra de Omarchy muestra u oculta
la tarjeta de actividad. La tarjeta resume la tarea en curso y su resultado.
Haz doble clic para abrir el mismo hilo de Codex en una terminal. Con el
puntero sobre la tarjeta, pulsa **Alt+X** para interrumpir el turno activo.

En Omarchy con Hyprland puedes dictar «¿Qué ves en pantalla?» o «Mira mi
pantalla y explícame el error». Voz Codex adjunta al turno una captura
JPEG del monitor activo, reducida a un máximo de 1280 píxeles por el lado
largo. La captura temporal se borra al terminar la consulta. Codex recibe
la imagen para analizarla y puede conservarla en su conversación.

`voz-codex doctor` revisa dependencias. `voz-codex status` muestra el hilo y proyecto activos. `voz-codex chat-search palabra` busca chats locales. `voz-codex chat-select THREAD_ID` retoma uno. `voz-codex cancel` detiene la lectura. La respuesta también se guarda en SQLite.

## Continuidad entre chats y grafo local

El último hilo utilizado por Voz Codex se conserva tras reiniciar. Si la
consulta encaja con otro chat o un área indexada, la respuesta puede sugerir
ese destino. Puedes decir «cambia a la sugerencia» o «cambia a Graphify»
y dictar la siguiente consulta cuando confirme el cambio. «Nuevo chat» abre
un hilo nuevo. Si Codex no puede reabrir un hilo, su historial local sigue
disponible y el servicio mantiene la selección.

Comandos útiles:

```bash
voz-codex chat-current
voz-codex chat-sync
voz-codex chat-route "retoma lo de Graphify" --dry-run
voz-codex chat-new "Graphify y memoria"
voz-codex topic-list
voz-codex topic-alias topic-graphify graphify
voz-codex graph-export
```

`graph-export` escribe un JSON pequeño y atómico en
`$XDG_DATA_HOME/voz-codex/graphify-out/graph.json`, con nodos de tema y
conversación y aristas con procedencia SQLite. Se actualiza al guardar cada
interacción; los eventos pendientes son idempotentes y permiten reanudar una
actualización después de un corte. La base usa WAL y una migración no
destructiva (`user_version=2`). No se exportan instrucciones del sistema,
credenciales, audio ni payloads de herramientas.

`chat-sync` consulta los hilos visibles del App Server de Codex, incluyendo
sesiones anteriores. `chat-search` y `chat-select` sincronizan antes de operar;
por eso un hilo remoto puede seleccionarse y reanudarse usando su `threadId`
real.

La cohesión es deliberadamente local y ligera: alias, coincidencia léxica,
recencia y vínculos tema↔hilo. Esto funciona sin descargar un modelo de
embeddings ni consumir tokens; una capa semántica opcional puede añadirse más
adelante sin cambiar el esquema ni el contrato del router.
