# OVOS Wyoming TTS

Exposes any OVOS text-to-speech plugin over the [Wyoming protocol](https://github.com/rhasspy/wyoming), so it appears as a regular TTS option in Home Assistant's own Assist pipeline setup.

## Setup

1. Install and start the add-on.
2. Home Assistant discovers it automatically (Wyoming protocol discovery). It shows up under **Settings → Devices & services → Discovered**.
3. Add it, then select it as the text-to-speech engine in **Settings → Voice assistants → Assist → [your pipeline]**.

## Configuration

| Option | Description |
|---|---|
| `plugin` | OVOS TTS plugin module name, e.g. `ovos-tts-plugin-server`, `ovos-tts-plugin-piper` |
| `plugin_config` | JSON object with plugin-specific settings, e.g. `{"voice": "en_US-lessac-medium"}` |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

The default (`ovos-tts-plugin-server`, OVOS's public hosted server) needs no configuration to try.

## mycroft.conf as the source of truth

This add-on shares `mycroft.conf` with the other OVOS add-ons (`ovos-core` in particular) via `/share`. If `tts.module` is already set there — e.g. by `ovos-core`'s own autoconfigure flow, or by `ha-ovos-integration`'s voice setup — that value wins over this add-on's own `plugin` option. The `plugin`/`plugin_config` options here only take effect the first time, when the shared file has nothing set yet.

## Included patch

`wyoming-ovos-tts` (the underlying package) has an upstream bug that crashes on startup against `wyoming>=1.9` (`TypeError: TtsVoice.__init__() missing 1 required positional argument: 'version'`). The Dockerfile patches this in place. Fixed automatically once [OpenVoiceOS/wyoming-ovos-tts#11](https://github.com/OpenVoiceOS/wyoming-ovos-tts/pull/11) ships in a PyPI release — no action needed here either way.

## Known limitations

- `plugin_config` is a single JSON text field, not a per-plugin form — you need to know the plugin's own config keys.
- Confirmed working end-to-end: builds, starts, discovered by HA, selectable in a pipeline. Actual synthesized speech during a live pipeline run hasn't been separately verified.
