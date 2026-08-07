# OVOS Core

The skill runtime and messagebus for the whole project. Hosts the shared `ovos-messagebus` other add-ons connect to, loads OVOS skills (installed via `ovos-skills`/`ovos-skills-extra`), and exposes a synchronous question/answer HTTP bridge for other systems (like `ha-ovos-integration`) to ask it things.

## API (port 8500)

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` |
| `POST /ask` | Body `{"utterance": "what time is it", "lang": "en-us"}`. Injects the utterance as if a real STT transcribed it, waits (up to 20s) for a skill or fallback to answer, returns `{"utterance": "...", "skill": "..."}`. `504` if nothing answered in time. |
| `POST /autoconfigure` | Body `{"lang": "en-us", "online": false, "offline": false, "male": false, "female": false}`. Runs `ovos-config autoconfigure` against the shared `mycroft.conf`, picking TTS/STT plugins for the given language/mode. Returns `changed_keys`, `not_available` (nothing found for that combination), and the resulting `tts_module`/`stt_module`. Doesn't install anything — picking a plugin and installing it are separate steps, same as OVOS's own tooling. |

Requests to `/ask` are serialized (one at a time, not matched by session) — concurrent requests queue rather than racing.

## Configuration

| Option | Description |
|---|---|
| `extra_pip_packages` | Space-separated pip packages to install at startup |
| `log_level` | `debug` / `info` / `warning` / `error` |
| `intent_matcher` | `padacioso` (default) or `padatious` — see "Intent pipeline" below |

## Intent pipeline

`intent_matcher` picks between `ovos-padacioso-pipeline-plugin` (default) and `ovos-padatious-pipeline-plugin`: padacioso is a lightweight, pure-Python matcher; padatious is a compiled, trained one. On weaker hardware (a typical HAOS NUC/Pi), padatious can take 80-90+ seconds per utterance; padacioso answers in under a second, with simpler fuzzy-matching instead of a trained model. This is a real accuracy/speed trade-off, not a strict improvement — pick based on your own hardware's headroom. Switching installs/uninstalls `ovos-padatious` at startup, so the first restart after changing it takes longer than normal.

The pipeline order (in `run.sh`) differs slightly by choice, but both follow the same shape: stop → converse → OCP (media) → intent matcher (padacioso/padatious, high and medium tiers) → adapt → Common Query (general-knowledge questions, answered by any installed CommonQuerySkill, e.g. Wolfram Alpha) → fallback tiers, high to low.

`ovos-persona-pipeline-plugin` stays disabled — this project's own persona bridge (the `ovos-persona` add-on) is a separate, deliberate mechanism, not this in-core one.

## Shared messagebus

Binds on this add-on's own resolvable hostname (not `0.0.0.0`), since `ovos-messagebus`/`ovos-skill-launcher` read the same `websocket.host` value from the shared `mycroft.conf` for both binding and connecting — `ovos-skills`, `ovos-skills-extra`, and every skill's own launched process connect here. `ovos-persona` runs its own, separate, private bus and is not part of this.

## First-boot startup time

The first boot downloads ML models (for the model2vec/Common Query pipeline plugins) from Hugging Face Hub — can take ~90 seconds. Subsequent boots are faster once those models are cached on `/share`. `api.py`'s own `/health` reports readiness rather than blocking.

## Known limitations

- Skill loading depends on `ovos-skills`'/`ovos-skills-extra`'s own venv-per-skill launch mechanism, not OVOS's classic `skills.list` convention — confirmed working via Python entry point discovery.
- No HA conversation-agent wiring yet — nothing currently calls this add-on's `/ask` as an actual Assist conversation agent.
- Concurrent request handling is a simple lock, not OVOS's own session-based request matching.
