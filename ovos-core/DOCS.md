# OVOS Core

The skill runtime and messagebus for the whole project. Hosts the shared `ovos-messagebus` other add-ons connect to, loads OVOS skills (installed via `ovos-skills`/`ovos-skills-extra`), and exposes a synchronous question/answer HTTP bridge for other systems (like `ha-ovos-integration`) to ask it things.

## API (port 8500)

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` |
| `POST /ask` | Body `{"utterance": "what time is it", "lang": "en-us"}`. Injects the utterance as if a real STT transcribed it, waits (up to 35s) for a skill or fallback to *speak* a response, returns `{"utterance": "...", "skill": "..."}`. `504` if nothing spoke in time — **note:** this also fires for utterances that were matched and handled but produced no spoken response (e.g. "stop"), not only for genuinely unmatched ones; see Known limitations. |
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

- **`/ask` conflates "matched but silent" with "nothing matched".** Built-in action-only intents (e.g. the `stop_high`/`stop_medium` pipeline stages, which just emit a bus message and stop active skills) are matched and handled at the bus level with no `speak` event — `/ask` has nothing to listen for, so it blocks the full 35s and returns `504` even though the utterance was genuinely handled. Confirmed via `handle_utterance` logs showing `stop_medium match ... handled=True` immediately, followed by 35s of silence before the `504`. A caller using `/ask` as a conversation agent (e.g. `ha-ovos-integration`) currently sees this as a failed request. Fix would need `_ask_sync` to also listen for the pipeline's own match/handled signal, not just `speak`, and return a distinct "handled, no spoken response" result promptly instead of waiting out the timeout — not yet built.
- The curated catalog's `skill-ovos-stop.openvoiceos` (an old, alpha-only PyPI package using a legacy `mycroft`-namespace entry point) crash-loops on this stack (`ModuleNotFoundError: No module named 'mycroft'`) and was uninstalled from hardware — it also appears to duplicate `ovos-core`'s own built-in `stop_high`/`stop_medium` matchers, which already handle plain "stop" utterances without it. Removed from the curated catalog's default set; see `ovos-skills/DOCS.md`.
- Skill loading depends on `ovos-skills`'/`ovos-skills-extra`'s own venv-per-skill launch mechanism, not OVOS's classic `skills.list` convention — confirmed working via Python entry point discovery.
- No HA conversation-agent wiring yet — nothing currently calls this add-on's `/ask` as an actual Assist conversation agent.
- Concurrent request handling is a simple lock, not OVOS's own session-based request matching.
