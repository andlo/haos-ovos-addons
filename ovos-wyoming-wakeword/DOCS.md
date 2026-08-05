# OVOS Wyoming Wakeword

Exposes OVOS wake word plugins over the [Wyoming protocol](https://github.com/rhasspy/wyoming), so they appear as wake word options in Home Assistant's own Assist pipeline setup.

Unlike the TTS/STT add-ons, there is no single "active plugin" — every wake word defined in `hotwords_config` loads and is made available via Wyoming at once.

## Setup

1. Install and start the add-on.
2. Home Assistant discovers it automatically. It shows up under **Settings → Devices & services → Discovered** as `wake_word.ovos_wakeword_plugins`.
3. Add it, then select a wake word in **Settings → Voice assistants → Assist → [your pipeline]**.

## Configuration

| Option | Description |
|---|---|
| `hotwords_config` | JSON object matching `mycroft.conf`'s `"hotwords"` section — one or more wake words |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for wake word plugins not baked into the image |
| `zeroconf` | Advertise this service via mDNS for auto-discovery |
| `log_level` | `debug`, `info`, `warning`, or `error` |

The default `hotwords_config` sets up `hey_mycroft` using the bundled `precise-lite` plugin — works out of the box for a first test.

## Known limitations

- `hotwords_config` is a single JSON text field describing potentially several wake words — no per-wake-word form yet.
- Confirmed working end-to-end: builds, starts, sends discovery, appears in HA, selectable in a pipeline. Not tested with more than one wake word active simultaneously. Actual wake word detection during a live pipeline run hasn't been separately verified — only that the entity and pipeline wiring are correct.
