# OVOS Wyoming Wakeword

🚧 **v0.0.x — untested, work in progress.** Version stays below 0.1.0 until this has actually
run successfully on a real HAOS install.

## What it does

Wraps [wyoming-ovos-wakeword](https://github.com/TigreGotico/wyoming-ovos-wakeword), exposing
OVOS wake word plugins via the Wyoming protocol. Unlike the TTS/STT add-ons, there is no single
"active plugin" — every wake word defined in `hotwords_config` is loaded and made available
via Wyoming at once.

## Configuration

| Option | Description |
|---|---|
| `hotwords_config` | JSON object matching `mycroft.conf`'s `"hotwords"` section — one or more wake words |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for wake word plugins not baked into the image |
| `zeroconf` | Advertise this service via mDNS for auto-discovery |
| `log_level` | `debug`, `info`, `warning`, or `error` |

Default `hotwords_config` sets up `hey_mycroft` using the bundled `precise-lite` plugin, so it
should work out of the box for a first test.

## Known limitations

- `hotwords_config` is a single JSON text field describing potentially several wake words —
  no per-wake-word form yet.
- Not yet verified against a real HAOS Supervisor install, and not yet tested with more than
  one wake word active simultaneously.
