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

## Build dependencies (why this Dockerfile looks heavier than TTS/STT)

Getting this one running on a real HAOS Supervisor took four separate fixes, none of them
code bugs — all missing pieces in the build/runtime environment:

1. `pyaudio` (a transitive dependency) has no prebuilt wheel for this base image and must
   compile from source → needs `build-base`, `portaudio-dev`, `python3-dev`.
2. `ovos_plugin_manager` imports `pkg_resources` → needs `setuptools` installed explicitly.
3. Recent `setuptools` (83.0.0+) dropped `pkg_resources` entirely → pinned to
   `setuptools<=80.9.0`.
4. `zeroconf` python package missing, needed because `zeroconf: true` is the default option.

## Known limitations

- `hotwords_config` is a single JSON text field describing potentially several wake words —
  no per-wake-word form yet.
- Verified end-to-end on a real HAOS Supervisor as of v0.0.4: builds, starts cleanly, sends
  discovery, appears as `wake_word.ovos_wakeword_plugins`, and is selectable as a wake word
  engine in an Assist pipeline. Not yet tested with more than one wake word active
  simultaneously, and not yet confirmed that saying "Hey Mycroft" actually triggers detection
  on a real satellite — only that the entity and pipeline wiring are correct.
