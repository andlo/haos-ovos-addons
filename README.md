# haos-ovos-addons

<img src="logo.png" width="96" height="96" alt="OpenVoiceOS logo">

Home Assistant OS (Supervisor) add-ons that bring [OpenVoiceOS](https://openvoiceos.org) into Home Assistant's own Assist pipeline — install from the Add-on Store, fill in a form, done. No manual config files, no command line.

## Installation

1. In Home Assistant: **Settings → Add-ons → Add-on Store**.
2. Top right **⋮ → Repositories**, paste `https://github.com/andlo/haos-ovos-addons`, **Add**.
3. The add-ons below now appear in the store. You don't need all of them — see "Which add-ons do I actually need?" below to pick.

## Add-ons in this repo

| Add-on | What it does |
|---|---|
| `ovos-wyoming-tts` | Text-to-speech for Assist, via any OVOS TTS plugin |
| `ovos-wyoming-stt` | Speech-to-text for Assist, via any OVOS STT plugin |
| `ovos-wyoming-wakeword` | Wake word detection for Assist, via any OVOS wake word plugin |
| `ovos-persona` | A conversation agent for open-ended questions (Ollama/OpenAI-compatible) |
| `ovos-core` | The skill runtime — runs skills and answers questions, the engine behind everything below |
| `ovos-skills` | Install a small, tested set of OVOS skills (alarms, weather, general knowledge, ...) |
| `ovos-skills-extra` | Install *any* OVOS skill from PyPI or a git link — nothing pre-checked, use if you know what you're installing |
| `ovos-busmon` | Watch every message OVOS sends internally, live, as it happens — a debugging tool |
| `ovos-tui` | Type what you'd say and watch OVOS answer, without needing a microphone — a testing tool |
| `ovos-control-panel` | The official OpenVoiceOS admin page, for things this project's own integration doesn't cover yet |

See each add-on's own `DOCS.md` (visible from its page in the Add-on Store) for full setup and configuration details.

## Which add-ons do I actually need?

Three different starting points, depending on what you're trying to do. You can mix and match — none of them require each other.

### "I just want better voice recognition/speech in Assist"

Install any combination of `ovos-wyoming-tts`, `ovos-wyoming-stt`, `ovos-wyoming-wakeword`, and `ovos-persona`. That's it — nothing else in this repo is needed.

1. Install and start whichever ones you want.
2. The three `ovos-wyoming-*` add-ons show up automatically under **Settings → Devices & services → Discovered** — add them from there, then pick each one as the engine in **Settings → Voice assistants → Assist → [your pipeline]**.
3. For `ovos-persona`, add Home Assistant's own **Ollama** integration pointed at `http://<hostname>:8337`, then select it as the conversation agent in the same pipeline settings.

### "I want OVOS skills — alarms, weather, trivia — running through Assist"

Install `ovos-core` and `ovos-skills` (add `ovos-skills-extra` and/or `ovos-persona` if you want them too).

1. Install and start `ovos-core` and `ovos-skills`.
2. Install [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) via HACS, then add the **OpenVoiceOS** integration in Home Assistant.
3. In the integration's settings, enter each add-on's address (e.g. `http://<hostname>:8500` for `ovos-core`).
4. From the integration, use **Add sub-entry** to install skills and set up voice/persona — these are normal Home Assistant setup screens, no config files.
5. Select **OpenVoiceOS** as the conversation agent under **Settings → Voice assistants → Assist → [your pipeline]** — this is the step that actually connects your skills to Assist.

### "Something isn't working right, or I want to see/change more than the integration offers"

Three optional tools, each for a different kind of digging:

- **`ovos-tui`** — the fastest way to check "does this skill even work?" Type a sentence, see what OVOS does with it, no microphone or wake word needed. Start here if a skill isn't answering the way you expect.
- **`ovos-busmon`** — when `ovos-tui` isn't enough and you want to see the raw traffic between every OVOS component in real time. More detail, more setup (needs a login you set yourself in its Configuration tab).
- **`ovos-control-panel`** — the official OpenVoiceOS admin page. Covers things `ha-ovos-integration` doesn't yet: installing OVOS plugins, editing personas directly, translating a skill, backing up and restoring settings.

All three are debugging/admin tools, not something to leave running all the time — each one defaults to **not starting automatically** on boot (`boot: manual`), and needs its own login set before you rely on it (see its own `DOCS.md`).

## How they fit together

- `ovos-wyoming-*` plug straight into Assist's own settings — no other add-on needed.
- `ovos-core` hosts the shared messagebus that everything else talks over; `ovos-skills`/`ovos-skills-extra` run each installed skill against it.
- `ovos-persona`, `ovos-busmon`, `ovos-tui`, and `ovos-control-panel` are each independent — install any of them with or without the others.
- Add-ons that share settings (language, which TTS/STT to use, which skills are installed) all read and write the same files on `/share`, so `ovos-control-panel`'s Settings page, `ovos-tui`'s pipeline view, and `ha-ovos-integration`'s own entities all agree with each other automatically.

Day-to-day, most people manage this through [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) — a Home Assistant integration that turns skill installs, voice setup, and persona configuration into ordinary HA setup screens. This repo is the add-ons it talks to; `ovos-busmon`/`ovos-tui`/`ovos-control-panel` are there for when you need to look under the hood.

## License

![license](https://img.shields.io/badge/license-Apache--2.0-blue)

Licensed under the [Apache License 2.0](LICENSE), matching OpenVoiceOS's own project license.

The OpenVoiceOS logo is used with attribution to the [OpenVoiceOS project](https://openvoiceos.org); this project is not officially affiliated with or endorsed by OpenVoiceOS.
