# Instalación en Omarchy

```bash
cd ~/Work/voz-codex
./voz-codex doctor
mkdir -p ~/.local/share/com.pais.handy/hooks ~/.config/systemd/user
install -m 700 handy/transcription ~/.local/share/com.pais.handy/hooks/transcription
install -m 644 systemd/voz-codex.service ~/.config/systemd/user/voz-codex.service
systemctl --user daemon-reload
systemctl --user enable --now voz-codex.service
```

Configura Handy con Paste Method `None` o `External Script` según la versión. Alt+Z conserva el control de grabación de Handy. El binding de Hyprland se cambia después de validar el servicio, usando la ruta absoluta a `.venv/bin/voz-codex toggle`.
