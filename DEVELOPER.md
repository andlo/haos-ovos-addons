# Developer notes — HA-OVOS project

🚧 Work in progress. This document describes the main outline of the idea and what needs to
be built across the project's three repos. It is not a finished spec, but a working baseline.

## The idea

Make it easy for an ordinary HAOS user to discover and use OpenVoiceOS (OVOS) — without them
needing to know it's OVOS. HAOS users already know the pattern "go to the Add-on Store, install,
fill in a form". Most of the technical foundation (Wyoming bridges, persona server,
skill.json metadata, skill manager) already exists in the OVOS ecosystem. The job is packaging
and integration, not inventing something new.

## The three repos

### 1. `haos-ovos-addons` (this repo) — build first

Real HA Supervisor add-ons. Each add-on: `config.yaml`, `Dockerfile`, `run.sh`, `translations/en.yaml`.

- **ovos-wyoming-tts / -stt / -wakeword**: wrapper around OVOS's Wyoming bridges. `run.sh` builds
  a `mycroft.conf` from the add-on options (`plugin`, `plugin_config` as JSON, `extra_pip_packages`
  to install new plugins without rebuilding the image), then starts the bridge.
- **ovos-persona**: wrapper around `ovos-persona-server`. Options: `solvers` (list),
  `solver_config` (JSON), `extra_pip_packages`. `run.sh` builds `persona.json` and starts the
  server. Exposes an Ollama-compatible endpoint for HA's conversation-agent integration.
- **ovos-skill-config**: wrapper around `ovos-skill-config-tool` (already exists as a pip
  package). Pure packaging, no new logic.

All four require no `docker.sock` access, no sibling containers — plain, "supported" HA add-ons.

### 2. `ovos-skill-browser` — build after #1

Fork of [OpenVoiceOS/OVOS-skills-store](https://github.com/OpenVoiceOS/OVOS-skills-store)
(the repo is explicitly designed to be forked). A self-hosted browse page over the `skills.json`
feed, with icons, descriptions, tags, and "Install Skill" buttons. Runs outside HAOS, e.g. on
Proxmox next to the OVOS stack.

**The first task is to investigate, not build:** check whether the "Install Skill" button talks
directly to a local `ovos-core` instance, or only supports GGWave audio transfer. If a bridge to
`ovos_skill_manager` (OSM) is needed, it's built here.

### 3. `haos-ovos-skills` — deliberately deferred

HAOS variant where multiple skills share the same container/Python environment (unlike
`ovos-docker`'s model of one container per skill). Two open questions before this makes sense:

- **Dependency conflicts**: multiple skills' pip requirements in the same environment can
  collide. This is exactly what one-container-per-skill in `ovos-docker` avoids.
- **Missing plug into Assist**: skills run over OVOS's messagebus/HiveMind, not Wyoming or the
  Ollama API. There is no established "plug" into HA's UI yet.

Revisit once #1 and #2 are in production.
