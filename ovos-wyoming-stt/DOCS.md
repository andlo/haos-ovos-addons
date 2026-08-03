# OVOS Wyoming STT

🚧 **v0.0.x — untested, work in progress.** Version stays below 0.1.0 until this has actually
run successfully on a real HAOS install.

## What it does

Wraps [wyoming-ovos-stt](https://github.com/TigreGotico/wyoming-ovos-stt), exposing any OVOS
STT plugin via the Wyoming protocol. Once installed, it should appear as a speech-to-text
option in **Settings → Voice assistants → Pipelines**.

## Configuration

| Option | Description |
|---|---|
| `plugin` | OVOS STT plugin module name, e.g. `ovos-stt-plugin-server`, `ovos-stt-plugin-whisper` |
| `plugin_config` | JSON object with plugin-specific settings |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

The default plugin (`ovos-stt-plugin-server`) uses OVOS's public hosted server and needs no
configuration to try out.

## Known limitations

- `plugin_config` is a single JSON text field, not a per-plugin form — you need to know the
  plugin's own config keys.
- Heavier local STT plugins (e.g. Whisper models) may need more CPU/RAM than a default HAOS
  install has to spare — not yet benchmarked.
- Verified end-to-end on a real HAOS Supervisor: builds, starts cleanly with no errors in the
  log, appears under Settings → Devices & services, and is selectable as an STT engine in an
  Assist pipeline once confirmed. Not yet verified that transcription is actually accurate —
  only that the plumbing works.
