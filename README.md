# haos-ovos-addons

<img src="logo.png" width="96" height="96" alt="OpenVoiceOS logo">

Home Assistant OS (Supervisor) add-ons that bring [OpenVoiceOS](https://openvoiceos.org) into Home Assistant's own Assist pipeline — discoverable and configurable the way HAOS users already expect: Add-on Store, install, fill in a form.

## Add-ons in this repo

| Add-on | What it does |
|---|---|
| `ovos-wyoming-tts` | Text-to-speech engine for the Assist pipeline, via any OVOS TTS plugin |
| `ovos-wyoming-stt` | Speech-to-text engine for the Assist pipeline, via any OVOS STT plugin |
| `ovos-wyoming-wakeword` | Wake word engine for the Assist pipeline, via any OVOS wake word plugin |
| `ovos-persona` | Conversation agent (Ollama/OpenAI-compatible), for open-ended questions |
| `ovos-core` | The skill runtime: shared messagebus, intent matching, and a synchronous question/answer API |
| `ovos-skills` | Install/remove/configure a small, curated set of OVOS skills known to work in this setup |
| `ovos-skills-extra` | Install ANY OVOS skill from PyPI or a git URL — unverified, unrestricted |

See each add-on's own `DOCS.md` for setup, configuration, and API details.

## How they fit together

- `ovos-wyoming-*` plug directly into HA's own Assist pipeline settings — no other add-on required.
- `ovos-core` hosts the shared messagebus; `ovos-skills`/`ovos-skills-extra` launch each installed skill's own process against it.
- `ovos-persona` is fully independent — runs with or without any of the others.
- All add-ons that use a shared `mycroft.conf` (language, TTS/STT module, etc.) read and write it via `/share`.

Managed day-to-day through [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration), a Home Assistant integration that turns skill installs, voice setup, and persona configuration into ordinary HA config flows — this repo is the add-ons it talks to.

## License

![license](https://img.shields.io/badge/license-Apache--2.0-blue)

Licensed under the [Apache License 2.0](LICENSE), matching OpenVoiceOS's own project license.

The OpenVoiceOS logo is used with attribution to the [OpenVoiceOS project](https://openvoiceos.org); this project is not officially affiliated with or endorsed by OpenVoiceOS.
