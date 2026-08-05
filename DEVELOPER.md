# Developer notes — HA-OVOS project

## The idea

Make it easy for an ordinary HAOS user to discover and use OpenVoiceOS (OVOS) — without them needing to know it's OVOS. HAOS users already know the pattern "go to the Add-on Store, install, fill in a form." Most of the technical foundation (Wyoming bridges, persona server, skill packaging) already exists in the OVOS ecosystem. The job is packaging and integration, not inventing something new.

Two repos: this one (`haos-ovos-addons`, the Supervisor add-ons) and [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) (the HA integration that configures them). Open items and known gaps are tracked as [GitHub Issues](https://github.com/andlo/haos-ovos-addons/issues), not in this file.

## Architecture

**One shared `ovos-messagebus`, hosted by `ovos-core`.** Every other add-on that runs OVOS skill code connects to it by hostname, the same way any two Supervisor add-ons reach each other — not each add-on running its own private, isolated bus.

**`ovos-core` is the skill runtime; `ovos-skills`/`ovos-skills-extra` are the install mechanism — deliberately separate.** Installing or removing a skill is a different, riskier operation (arbitrary dependencies, potential crashes) than running one. A bad install can't take down the live runtime; a runtime bug can't corrupt an install in progress. Skills launch as their own `ovos-skill-launcher` subprocess, connecting to `ovos-core`'s shared bus from inside `ovos-skills`'/`ovos-skills-extra`'s own container — `ovos-core` never needs the skill's files in its own filesystem at all.

**One isolated Python virtual environment per skill**, not a shared `site-packages`. A real, hardware-confirmed incident drove this: installing one skill (`ovos-skill-wolfie`) pulled in a newer `ovos-workshop` incompatible with `ovos-core` and another already-installed skill, corrupting the shared environment for everything, not just the one skill. Per-skill venvs make that structurally impossible. Cost: a rebuild/update reinstalls every skill from scratch (no venv persistence, only a small manifest does) — mitigated by a shared, persistent pip cache (`/share/ovos-pip-cache`) across every add-on, so the underlying packages are usually already fetched.

**Curated (`ovos-skills`) vs. extra (`ovos-skills-extra`) skill catalogs.** The official OVOS skills catalog was never vetted for this project's specific architecture — no `ovos-audio`, no continuous microphone listener. Confirmed for real: several skills that sound like obvious defaults (`ovos-skill-volume`, `ovos-skill-naptime`, OCP-based media skills like `ovos-skill-news`) depend on things this setup doesn't provide, and load without error while silently doing nothing. `ovos-skills` serves a small, hand-verified list; `ovos-skills-extra` is the unrestricted, unverified escape hatch for anything else. Mirrors Debian's main/contrib, or HA's built-in integrations vs. HACS.

**`mycroft.conf` is the master**, not any single add-on's own options. Every add-on that has a `plugin`/`options`-style setting (Wyoming TTS/STT, wakeword) reads the shared `/share/mycroft/mycroft.conf` first and only falls back to its own options field if the shared file has nothing set yet — so a manual edit, `ovos-core`'s own autoconfigure, and an add-on's own config form are three ways of writing to one source of truth, not three competing ones.

**`padacioso`, not `padatious`, as the intent matcher.** `padatious` (the default, a compiled, trained model) took 80-90+ seconds per utterance on real, weaker NUC hardware — not a bug, a genuine performance ceiling on that hardware. `padacioso` is a lightweight, pure-Python drop-in with simpler fuzzy-matching, answering in under a second. A real accuracy/speed trade-off, not a strict improvement.

**Common Query is enabled; the in-core persona pipeline plugin stays disabled.** Common Query answers general-knowledge questions via any installed `CommonQuerySkill` (e.g. Wolfram Alpha) — confirmed to need no external service, same `speak_dialog` mechanism as any other skill. The in-core persona pipeline is a separate, redundant path to this project's own `ovos-persona` add-on and bridge; left off deliberately, not evaluated.

**`ovos-core`'s `/ask` is synchronous, request/response only (v1 scope).** A skill speaking on its own initiative (an alarm firing) needs something pushing audio into HA independent of a question being asked — out of scope for now, would need the same long-running process to also listen for unprompted `speak` events and forward them via `assist_satellite.announce`.

## License

![license](https://img.shields.io/badge/license-Apache--2.0-blue)

Licensed under the [Apache License 2.0](LICENSE), matching OpenVoiceOS's own project license.
