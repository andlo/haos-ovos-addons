# haos-ovos-addons

<img src="logo.png" width="96" height="96" alt="OpenVoiceOS logo">

Home Assistant OS (Supervisor) add-ons that bring [OpenVoiceOS](https://openvoiceos.org) into Home Assistant's own Assist pipeline — discoverable and configurable the way HAOS users already expect: Add-on Store, install, fill in a form.

## Installation

1. In Home Assistant: **Settings → Add-ons → Add-on Store**.
2. Top right **⋮ → Repositories**, paste `https://github.com/andlo/haos-ovos-addons`, **Add**.
3. The add-ons below now appear in the store. Install the ones you need — see "Two ways to use this" below for which ones.

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

## Two ways to use this

These add-ons work at two different levels, and you don't need the second to use the first.

### 1. Extend Assist with better building blocks

Install just `ovos-wyoming-tts`, `ovos-wyoming-stt`, `ovos-wyoming-wakeword`, and/or `ovos-persona` — pick any combination. Each one plugs directly into HA's own, existing Assist pipeline settings as an alternative TTS/STT/wake-word engine or conversation agent. Nothing else in this repo is required.

**Setup:**
1. Install and start whichever of the four add-ons you want.
2. `ovos-wyoming-*` add-ons announce themselves automatically — they show up under **Settings → Devices & services → Discovered**. Add them, then select each as the engine in **Settings → Voice assistants → Assist → [your pipeline]**.
3. For `ovos-persona`, add HA's own **Ollama** integration, pointed at the add-on's address (`http://<hostname>:8337`), then select the resulting agent in the same pipeline settings.

This is the whole story for this path — no `ha-ovos-integration`, no `ovos-core`, no skills.

### 2. A full OVOS backend — skills, its own conversation agent, all managed from HA

Install `ovos-core` plus `ovos-skills` (and optionally `ovos-skills-extra` and `ovos-persona`) to get a real, running OVOS skill runtime behind Assist — alarms, weather, general-knowledge answers, and anything else a skill can do, not just better TTS/STT.

**Setup:**
1. Install and start `ovos-core`, `ovos-skills`, and any of `ovos-skills-extra`/`ovos-persona` you also want.
2. Install [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) via HACS, then add the **OpenVoiceOS** integration in HA.
3. Fill in each add-on's own API URL under the integration's entities (e.g. `http://<hostname>:8500` for `ovos-core`).
4. Use the integration's **Add sub-entry** to install skills, run guided voice setup, and configure persona — all as ordinary HA config flows.
5. Select **OpenVoiceOS** as the conversation agent in **Settings → Voice assistants → Assist → [your pipeline]** — this is what actually connects Assist to your installed skills.

Nothing stops you combining both: use the Wyoming add-ons for TTS/STT/wake-word (path 1) while also running the full skill backend (path 2) in the same pipeline.

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
