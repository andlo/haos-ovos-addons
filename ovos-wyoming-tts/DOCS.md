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

## Upstream bug workaround (TODO: remove once fixed upstream)

`wyoming-ovos-tts` has a bug: its `TtsProgram(...)` call passes `version=__version__`, but the
nested `TtsVoice(...)` call omits it entirely. Against `wyoming>=1.9` this crashes at startup
with `TypeError: TtsVoice.__init__() missing 1 required positional argument: 'version'`. The
`Dockerfile` patches the installed source in place to fix this until it's fixed upstream.

- Upstream PR: [OpenVoiceOS/wyoming-ovos-tts#11](https://github.com/OpenVoiceOS/wyoming-ovos-tts/pull/11)
- **Once that PR is merged and a new PyPI release is cut**, remove the `RUN python3 -c "..."`
  patch step from the `Dockerfile` and just install `wyoming-ovos-tts` directly again.

## Known limitations

- `plugin_config` is a single JSON text field, not a per-plugin form — you need to know the
  plugin's own config keys.
- Verified end-to-end on a real HAOS Supervisor as of v0.0.6: builds, starts cleanly, sends
  discovery, appears under Settings → Devices & services → Discovered, and is selectable as a
  TTS engine in an Assist pipeline once confirmed. Not yet verified that synthesized speech
  actually plays correctly through a satellite/pipeline run.
