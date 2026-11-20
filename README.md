# Voz Codex

Puente local para conversar con Codex desde Handy en Omarchy. Convierte voz a texto, retoma el hilo correcto, envía consultas al Codex App Server, lee la respuesta con una voz neuronal local y muestra el progreso en la barra de Omarchy.

## Funciones

- Atajo de Handy para dictar y enviar consultas a Codex.
- Voz local con Kokoro o Piper y fallback a eSpeak NG.
- Pronunciación en español de números, temperaturas, porcentajes y unidades como GB, GHz, km/h y Celsius.
- Detección de nombres técnicos en inglés como YouTube, NVIDIA, GitHub y Python.
- Historial SQLite privado, búsqueda entre chats y selección de hilos existentes.
- Grafo local compatible con Graphify, actualizado de forma incremental.
- Captura opcional de pantalla para preguntas como «qué ves en mi pantalla».
- Tarjeta de actividad en la barra de Omarchy con X para ocultarla, doble clic para abrir el hilo y Alt+X para cancelar.

## Instalación rápida en Omarchy

```bash
git clone https://github.com/duy111111153/voz-codex.git ~/Work/voz-codex
cd ~/Work/voz-codex
chmod +x voz-codex handy/transcription
./voz-codex doctor
less docs/instalacion.md
```

Consulta [docs/instalacion.md](docs/instalacion.md), [docs/uso.md](docs/uso.md), [docs/arquitectura.md](docs/arquitectura.md) y [docs/privacidad.md](docs/privacidad.md).

## Desarrollo y pruebas

```bash
python -m unittest discover -s tests -q
python -m compileall -q voz_codex
./voz-codex doctor
```

## Licencia

Apache-2.0. Consulta [LICENSE](LICENSE) y [CONTRIBUTING.md](CONTRIBUTING.md).
