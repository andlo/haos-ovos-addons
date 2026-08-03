# haos-ovos-addons

![status](https://img.shields.io/badge/status-work%20in%20progress-orange)

<img src="logo.png" width="96" height="96" alt="OpenVoiceOS logo">

> 🚧 **Work in progress.** Nothing here has been tested in production yet. Use at your own risk.

Home Assistant OS (Supervisor) add-ons that bridge [OpenVoiceOS](https://openvoiceos.org)
into Home Assistant's Assist pipeline. Each add-on is a thin, well-defined wrapper around an
existing, already-maintained OVOS component — not new, unproven code.

## Add-ons in this repo

| Add-on | Function | Wraps |
|---|---|---|
| `ovos-wyoming-tts` | TTS slot in the Assist pipeline | [wyoming-ovos-tts](https://github.com/OpenVoiceOS/wyoming-ovos-tts) |
| `ovos-wyoming-stt` | STT slot in the Assist pipeline | wyoming-ovos-stt |
| `ovos-wyoming-wakeword` | Wakeword slot in the Assist pipeline | wyoming-ovos-wakeword |
| `ovos-persona` | Conversation agent (Ollama-compatible) | [ovos-persona-server](https://github.com/OpenVoiceOS/ovos-persona-server) |
| `ovos-skill-config` | Graphical configuration of installed skills | [ovos-skill-config-tool](https://github.com/OscillateLabsLLC/ovos-skill-config-tool) |

## Why

HAOS users already know the pattern: go to the Add-on Store, click install, fill in a form.
OVOS's Wyoming bridges and persona server already exist and are maintained by the OVOS project —
they just need this packaging to show up in HA's own world.

## Status

No add-ons are finished yet. See [DEVELOPER.md](DEVELOPER.md) in this repo for the overall
architecture and decisions behind the project.

## Related repos

- [ovos-skill-browser](https://github.com/andlo/ovos-skill-browser) — web-based skill store, runs outside HAOS
- [haos-ovos-skills](https://github.com/andlo/haos-ovos-skills) — deferred: skills directly inside a single HAOS container

## About

Part of the **HA-OVOS** project: making it easy for a Home Assistant OS user to discover and
use OpenVoiceOS, through interfaces that feel native to HAOS. This repo builds the actual
Supervisor add-ons — see the other repos for the web-based skill browser and the deferred
full-skills add-on.

## License

![license](https://img.shields.io/badge/license-Apache--2.0-blue)

Licensed under the [Apache License 2.0](LICENSE), matching OpenVoiceOS's own project license.

The OpenVoiceOS logo is used with attribution to the [OpenVoiceOS project](https://openvoiceos.org); this project is not officially affiliated with or endorsed by OpenVoiceOS.
