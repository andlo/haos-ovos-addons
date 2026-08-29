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
| `intent_matcher` | `padatious` (default) or `padacioso` — see "Intent pipeline" below |
| `secondary_langs` | Space-separated language tags to also build intent-matcher containers for, beyond the shared config's primary `lang` — see "Intent pipeline" below |

## Hardware requirements

**This add-on needs a host with genuine free RAM headroom (several GB, not just technically available) — not a "runs on anything HAOS supports" add-on.** `padatious`, the default and only currently-supported intent matcher (see below), pulls in a memory-heavy dependency stack (numpy/scipy/sklearn/fann2). Confirmed by direct reproduction on an under-resourced production host running ~30 add-ons simultaneously: `free -h` showed 344MB free / swap 92% full, `dmesg` showed an active OOM-kill, and padatious segfaulted (`Fatal Python error: Segmentation fault`) rather than raising a clean Python error. AVX2 was confirmed present on that CPU via `/proc/cpuinfo` — this is a memory-pressure problem, not a weak-CPU or instruction-set one.

**Practical guidance:** run this add-on on hardware with meaningful RAM to spare beyond whatever else is running on the same host — a dedicated or lightly-loaded mini-PC-class machine, not a NUC already saturated with 30 other add-ons. If this host can't offer that, either free up headroom elsewhere or don't run the full OVOS skill stack on it.

## Intent pipeline

`intent_matcher` picks between `ovos-padatious-pipeline-plugin` (default) and `ovos-padacioso-pipeline-plugin`. **`padatious` is the correct default**: it's OVOS's own official default, and what OpenVoiceOS's own reference Docker images (`OpenVoiceOS/ovos-docker`, published to `docker.io/smartgic/ovos-core`) actually ship — confirmed by reading their `core/Dockerfile` directly, which compiles real `padatious` via the same `[lgpl,plugins]` extras this add-on uses, with no fallback matcher at all. Aligning with that reference, rather than maintaining a bespoke lightweight-by-default setup, is the deliberate choice here — see "Hardware requirements" above for what it costs.

**Confirmed working end-to-end on `haos-ovos-dev` (2026-08-29, 16GB/8-core VM):** with `padatious` active, 6 of the 9 curated catalog skills matched their own intent directly (date-time, alerts, fallback-unknown, weather, personal, dad-jokes); the other 3 (wikihow, ddg, wikipedia) correctly route through `common_qa` instead, which is the intended mechanism for that style of general-knowledge skill, not a matching failure. This also surfaced and fixed a real, separate `ovos-padatious` concurrency bug — see `ovos-skills/DOCS.md`'s "Skill launches are staggered" section.

**`secondary_langs` (see Configuration above) is required for any non-primary language to match at all, and still isn't sufficient on its own.** Confirmed by reading `padatious.opm`/`padacioso.opm` directly: intent-matcher containers are built once at startup from `lang` + `secondary_langs`, never rebuilt on a runtime language switch. Setting it, clearing the intent cache, and confirming real trained `.net` models exist for the secondary language (da-DK, 87 of them, including the exact skill training phrase tested) was NOT enough to make matching succeed in that language during testing on 2026-08-29 — every da-dk query still fell through to `fallback-unknown`, for a reason not yet found (registration and training both appeared to succeed; something in the match-time lang resolution inside `ovos-core`'s own `intent_services.py` is the next place to look, not yet done). Treat multi-language support as **not working** until this is resolved, regardless of `secondary_langs` being set.

**`padacioso` is currently broken on this stack and not recommended.** It was originally the default here, chosen after a real, reproduced padatious segfault under memory pressure (see "Hardware requirements") — a legitimate concern for resource-constrained hosts. But integration testing on `haos-ovos-dev` (2026-08-29, 16GB/8-core VM, so not itself memory-constrained) found that with padacioso active, **none of the installed skills' intents ever matched, in either English or Danish** — every utterance fell through to `common_qa`/`fallback-unknown` regardless of phrasing. Investigated at length: confirmed `padacioso.opm.PadaciosoPipeline` does register the correct bus handlers (`padatious:register_intent`/`register_entity`, same names padatious itself uses), confirmed the installed skills ship the expected legacy `.intent` resource files in the correct locale directories, confirmed pipeline plugin construction happens before skill loading (no race condition), confirmed `padatious.instant_train: true` doesn't fix it. The actual root cause was not found — something between skills emitting `padatious:register_intent` and padacioso's `register_intent()` handler is silently dropping every registration, for reasons not yet identified. Given padatious is the properly-supported, reference-matching choice anyway, this was deprioritized rather than debugged further. If picking padacioso is ever revisited, start by watching live bus traffic for `padatious:register_intent` events rather than re-reading the static source — that's the next concrete diagnostic step, not yet done.

The pipeline order (in `run.sh`) differs slightly by choice, but both follow the same shape: stop → converse → OCP (media) → intent matcher (padatious/padacioso, high and medium tiers) → adapt → Common Query (general-knowledge questions, answered by any installed CommonQuerySkill, e.g. Wikipedia) → fallback tiers, high to low.

`ovos-persona-pipeline-plugin` stays disabled — this project's own persona bridge (the `ovos-persona` add-on) is a separate, deliberate mechanism, not this in-core one.

## Shared messagebus

Binds on this add-on's own resolvable hostname (not `0.0.0.0`), since `ovos-messagebus`/`ovos-skill-launcher` read the same `websocket.host` value from the shared `mycroft.conf` for both binding and connecting — `ovos-skills`, `ovos-skills-extra`, and every skill's own launched process connect here. `ovos-persona` runs its own, separate, private bus and is not part of this.

## Shared log files

Sets `logs.path` to `/share/mycroft/logs` in the shared `mycroft.conf` — confirmed by reading `ovos_utils/log.py`'s own `init_service_logger()`/`get_logs_config()` directly: every OVOS service that calls this (the messagebus, this add-on's own skill manager, each skill `ovos-skills` launches, `ovos-persona-server`, ...) reads this same shared config for where to write its own log file, and logs to **both** the file and stdout once this is set — `docker logs` on any individual add-on keeps working exactly as before, this is purely additive. Since `/share` is already read-write-mounted into every add-on in this repo, this is what lets `ovos-tui` (see that add-on's own DOCS.md) read real log files directly with no Docker socket access needed at all.

## First-boot startup time

The first boot downloads ML models (for the model2vec/Common Query pipeline plugins) from Hugging Face Hub — can take ~90 seconds. Subsequent boots are faster once those models are cached on `/share`. `api.py`'s own `/health` reports readiness rather than blocking.

## Known limitations

- **`/ask` conflates "matched but silent" with "nothing matched".** Built-in action-only intents (e.g. the `stop_high`/`stop_medium` pipeline stages, which just emit a bus message and stop active skills) are matched and handled at the bus level with no `speak` event — `/ask` has nothing to listen for, so it blocks the full 35s and returns `504` even though the utterance was genuinely handled. Confirmed via `handle_utterance` logs showing `stop_medium match ... handled=True` immediately, followed by 35s of silence before the `504`. A caller using `/ask` as a conversation agent (e.g. `ha-ovos-integration`) currently sees this as a failed request. Fix would need `_ask_sync` to also listen for the pipeline's own match/handled signal, not just `speak`, and return a distinct "handled, no spoken response" result promptly instead of waiting out the timeout — not yet built.
- The curated catalog's `skill-ovos-stop.openvoiceos` (an old, alpha-only PyPI package using a legacy `mycroft`-namespace entry point) crash-loops on this stack (`ModuleNotFoundError: No module named 'mycroft'`) and was uninstalled from hardware — it also appears to duplicate `ovos-core`'s own built-in `stop_high`/`stop_medium` matchers, which already handle plain "stop" utterances without it. Removed from the curated catalog's default set; see `ovos-skills/DOCS.md`.
- Skill loading depends on `ovos-skills`'/`ovos-skills-extra`'s own venv-per-skill launch mechanism, not OVOS's classic `skills.list` convention — confirmed working via Python entry point discovery.
- No HA conversation-agent wiring yet — nothing currently calls this add-on's `/ask` as an actual Assist conversation agent.
- Concurrent request handling is a simple lock, not OVOS's own session-based request matching.
- **Multi-language matching doesn't work**, even with `secondary_langs` configured and real trained models confirmed present for the secondary language — see "Intent pipeline" above. English-only deployments are unaffected.
