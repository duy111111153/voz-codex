# Voz Codex

Puente local y ligero entre Handy, Codex App Server, audio y un índice RAG de proyectos.

## Desarrollo local

```bash
./voz-codex doctor
./voz-codex serve
```

En otra terminal se puede probar el flujo con `./voz-codex ask "hola"`. Para integrar Handy, instala `handy/transcription` como hook de transcripción. La guía completa está en `docs/`.

## Privacidad

El historial, el índice y los audios permanecen en `$XDG_DATA_HOME/voz-codex`. El repositorio no contiene datos personales, exportaciones, credenciales ni modelos.
