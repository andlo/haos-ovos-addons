# OVOS Wyoming STT

Exposes any OVOS speech-to-text plugin over the [Wyoming protocol](https://github.com/rhasspy/wyoming), so it appears as a regular STT option in Home Assistant's own Assist pipeline setup.

## Setup

1. Install and start the add-on.
2. Home Assistant discovers it automatically. It shows up under **Settings → Devices & services → Discovered**.
3. Add it, then select it as the speech-to-text engine in **Settings → Voice assistants → Assist → [your pipeline]**.

## Configuration

| Option | Description |
|---|---|
| `plugin` | OVOS STT plugin module name, e.g. `ovos-stt-plugin-server`, `ovos-stt-plugin-whisper` |
| `plugin_config` | JSON object with plugin-specific settings |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

The default (`ovos-stt-plugin-server`, OVOS's public hosted server) needs no configuration to try.

## mycroft.conf as the source of truth

Shares `mycroft.conf` with the other OVOS add-ons via `/share`. If `stt.module` is already set there (e.g. via `ovos-core`'s autoconfigure flow, or `ha-ovos-integration`'s voice setup), that value wins over this add-on's own `plugin` option. `plugin`/`plugin_config` here only take effect the first time, when the shared file has nothing set yet.

## Known limitations

- `plugin_config` is a single JSON text field, not a per-plugin form — you need to know the plugin's own config keys.
- Heavier local STT plugins (e.g. Whisper models) may need more CPU/RAM than a default HAOS install has spare — not benchmarked.
- Confirmed working end-to-end: builds, starts, discovered by HA, selectable in a pipeline. Transcription accuracy hasn't been separately benchmarked — only that the plumbing works.
