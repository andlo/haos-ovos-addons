# OVOS Wyoming TTS

🚧 **v0.0.x — untested, work in progress.** Version stays below 0.1.0 until this has actually
run successfully on a real HAOS install.

## What it does

Wraps [wyoming-ovos-tts](https://github.com/TigreGotico/wyoming-ovos-tts), exposing any OVOS
TTS plugin via the Wyoming protocol. Once installed, it should appear as a text-to-speech
option in **Settings → Voice assistants → Pipelines**.

## Configuration

| Option | Description |
|---|---|
| `plugin` | OVOS TTS plugin module name, e.g. `ovos-tts-plugin-server`, `ovos-tts-plugin-piper` |
| `plugin_config` | JSON object with plugin-specific settings, e.g. `{"voice": "en_US-lessac-medium"}` |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

The default plugin (`ovos-tts-plugin-server`) uses OVOS's public hosted server and needs no
configuration to try out.

## Known limitations

- `plugin_config` is a single JSON text field, not a per-plugin form — you need to know the
  plugin's own config keys.
- Not yet verified against a real HAOS Supervisor install.
