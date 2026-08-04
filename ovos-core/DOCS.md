# OVOS Core

🚧 **Built, deployed, working end-to-end on real hardware.** `config.yaml`, `Dockerfile`,
`run.sh`, `api.py`, and `translations/en.yaml` all exist. Confirmed for real: `POST /ask
{"utterance": "what time is it"}` → `{"utterance": "Currently quarter past eight", "skill":
"ovos-skill-date-time.openvoiceos"}`, returned in under a second. Getting here took a long,
genuinely twisty investigation — what looked like an infinite hang turned out to be a real
performance problem with an easy fix once correctly diagnosed. See "The investigation: hang,
Alpine, or just slow?" below for the full trail, including two reasonable-looking fixes that
turned out not to be the actual cause. See "Not yet done" at the end of this file for what's
still open.

## The investigation: hang, Alpine, or just slow?

**Symptom**: `/ask` with `"what time is it"` (a skill genuinely installed, loaded, and ready —
confirmed via logs) never returned anything within any timeout tried, up to 70+ seconds. Not
an error — `ovos_core.intent_services.service:handle_utterance` logged `"Parsing utterance:
[...]"` and then nothing else, ever, for 70+ seconds. No match, no `complete_intent_failure`,
no fallback, no timeout, no exception. `/health` confirmed the messagebus connection stayed
up throughout.

**Hypotheses tested and ruled out, each with concrete evidence, not guessing**:

1. **Alpine build itself broken?** No — it built and started cleanly (`fann-dev` from
   Alpine's `community` repo, `swig2.0` shim). `pip check` was clean.
2. **Resource files (`.intent`/`.dialog`) missing from the installed skill package?** No —
   added a temporary `/debug/skill-files` endpoint and confirmed every locale directory,
   including `locale/en-US/intents/what.time.is.it.intent`, was genuinely present on disk.
3. **Wrong language?** No — confirmed `lang: "en-us"` both via HA's own `text.language`
   entity and by reading it back from the shared `mycroft.conf`.
4. **Something odd in the shared `mycroft.conf`** (written to by five other add-ons)? Read it
   directly via a temporary debug endpoint — nothing unusual, no `intents`/`pipeline`
   overrides.
5. **Stale/duplicate `ovos-messagebus` process from an earlier restart, our API talking to
   the wrong one?** No — `ps aux` via a temporary debug endpoint showed exactly one of each
   process, even after a clean `stop`+`start`.
6. **Newer `ovos-core` installed on real hardware than the sandbox tested** (since
   `constraints-alpha.txt` is a live URL fetched hours apart)? No — `/debug/versions`
   confirmed identical versions (`ovos-core==2.6.0a1`, same `ovos-bus-client`,
   `ovos-workshop`, etc.) on both.
7. **A network-dependent pipeline matcher (`ovos-common-query-pipeline-plugin`,
   `ovos-persona-pipeline-plugin`) hanging forever on an unreachable network call?**
   Blacklisted both via `intents.blacklisted_pipelines` and retested — still hung identically.
   Also: reading `ovos_core`'s own source showed the one confirmed network call after a match
   (`_upload_match_data`, an anonymous metrics upload to `metrics.tigregotico.pt`) runs via
   `create_daemon()` — a genuine background thread that structurally cannot block
   `handle_utterance`'s own return, so it was never a viable culprit even before testing.

**What actually found the real trail**: SSH access to a real, independently-running OVOS
installation (`ovos-installer`-based Docker deployment, 10 days uptime, `ovos_core` container
marked `healthy`) that answers `"what time is it"` correctly. Two things stood out on direct
comparison:

- `docker exec ovos_core cat /etc/os-release` → **Debian GNU/Linux 13 (trixie)**, not Alpine.
- `docker inspect ovos_core` → `docker.io/smartgic/ovos-core:testing` — OVOS's own official
  image. Confirmed via Docker Hub: `smartgic/ovos-core`'s own badges list a "Debian version",
  never Alpine.

This looked like the answer: `ovos-core[lgpl]` pulls in Padatious, a C++ library (via SWIG
bindings) built against `fann2`, and Alpine's `musl` libc vs. glibc is a known source of
subtle misbehavior in compiled C/C++ extensions. **Switched this add-on's base image to
Debian** (`ghcr.io/home-assistant/${BUILD_ARCH}-base-debian:latest`, using the `BUILD_ARCH`
build arg for multi-arch since `build.yaml`'s `build_from` is deprecated as of Supervisor's
2026.04 builder migration) — rebuilt, retested on real hardware.

**Same exact symptom, unchanged, on Debian.** This ruled out Alpine/musl as the cause. The fix
was reasonable given the evidence at the time, but wrong — worth recording *why* it looked
right, not just that it wasn't: matching OVOS's own official platform choice was a genuinely
sound inference, it just wasn't the actual variable that mattered here.

**The real cause, found by testing the "is it just slow?" hypothesis directly**: widened
`/debug/ask-verbose`'s listen window to 180s (up from the original 5s/60s) and checked
`ovos-core`'s own log timestamps across that window instead of assuming a fixed short
timeout was enough. Found exactly **90 seconds** between `"Parsing utterance: [...]"` and the
next log line (`ovos-padatious-pipeline-plugin-high match ...`) — reproduced twice, consistent
each time. It was never hanging. Padatious's matching genuinely took 80-90+ seconds *per
utterance* on this specific hardware (a weak NUC) — instant on the sandbox and the known-good
VM, both presumably running on stronger CPUs. No bug in `ovos-core` at all; a real, measured
performance ceiling on this specific device for this specific matcher.

**The actual fix**: switch the intent matcher, not the OS. `padacioso` is a lightweight,
pure-Python drop-in replacement for `padatious` — same `.intent` file format, same
registration bus messages (`padatious:register_intent` etc., confirmed by reading
`padacioso.opm.PadaciosoPipeline.__init__` directly), simple fuzzy-matching instead of a
trained neural model. It was already installed the whole time (a transitive dependency of
`ovos-core[plugins]`, registers its own `ovos-padacioso-pipeline-plugin` entry point) but
never actually used — `ovos-config`'s own shipped default `intents.pipeline` list only
includes `ovos-padatious-pipeline-plugin-high`, nothing padacioso-related. `run.sh` now
overrides `intents.pipeline` explicitly, swapping padacioso in at the same priority slot
padatious held. Confirmed for real: `POST /ask {"utterance": "what time is it"}` → correct
answer, under a second, no timeout needed.

**Kept anyway, on their own merits**:
- ~~The **Debian base image**~~ — **reverted back to Alpine**: Debian never actually fixed
  anything (the identical hang reproduced on it too), so keeping it would have made this the
  only one of six add-ons off Alpine for no remaining reason once the real cause was
  understood. Confirmed for real after reverting: `POST /ask {"utterance": "what time is
  it"}` → `"It is eight twenty one"`, correct, under a second, on Alpine with padacioso
  configured. Alpine was never the problem.
- The **`intents.blacklisted_pipelines`** entry (`ovos-common-query-pipeline-plugin`,
  `ovos-persona-pipeline-plugin`) added while testing (and ruling out) a hanging-network-call
  hypothesis — harmless to leave, and both are genuinely out of scope for this add-on today
  (they need external services not set up here).

**What this means for real skill performance**: `padacioso`'s fuzzy matching is simpler than
padatious's trained model — likely less accurate on ambiguous or loosely-phrased utterances,
a real trade-off, not a free lunch. Worth keeping in mind once more skills are installed and
real usage patterns emerge — this was the right call for "usably fast at all" over "maximally
accurate but 90 seconds per question," but it's a trade-off, not a strict improvement.


## What this add-on is for

The "next big piece" described in `haos-ovos-addons/DEVELOPER.md`: a real, persistent
`ovos-core` skill runtime — the only thing in this whole project that actually *loads* skills
and can make one respond to a question. Everything built so far (`ovos-skills`, `ovos-persona`,
the Wyoming bridges) makes OVOS components installable/configurable but not "alive" — see
`DEVELOPER.md`'s "Next big piece" section for the full reasoning on why that gap exists and
the architecture decided for closing it (shared messagebus, `ovos-skills` staying separate,
hot-install via that shared bus, v1/v2 scope split).

## Verified in a sandbox spike, then confirmed again against the real `api.py`

Everything below was directly run and confirmed, not assumed — see the session transcript
if the exact commands are ever needed again.


### The install recipe — copied from OVOS's own official Docker image, not invented

Fetched directly from `OpenVoiceOS/ovos-docker`'s real `core/Dockerfile` and
`core/files/requirements.txt` (`dev` branch) rather than guessing a package list:

```
bitstruct
ovos-core[lgpl,plugins]
ovos-skill-boot-finished
```

Installed together, constrained by OVOS's own coordinated version pins:

```
pip install --pre bitstruct "ovos-core[lgpl,plugins]" ovos-skill-boot-finished \
    -c https://raw.githubusercontent.com/OpenVoiceOS/ovos-releases/refs/heads/main/constraints-alpha.txt
```

**Confirmed clean**: `pip check` → "No broken requirements found." after this install — no
version conflicts, unlike the real, hours-long pain `ovos-persona-server`'s unpinned
`ovos-persona>=0.9.0a6` dependency caused earlier this session (see `ovos-persona/DOCS.md`).
The difference: installing everything from one coordinated `requirements.txt` against one
`constraints-${channel}.txt` file, the way OVOS's own image does it, instead of installing
packages one at a time and letting pip resolve them independently.

**`ovos-messagebus` is a separate install**, not pulled in by `ovos-core[plugins]` — confirmed
by it failing to start until installed explicitly. Matches the architecture decision in
`DEVELOPER.md`: the shared bus is conceptually separate from the skill runtime, even though
this add-on will host both.

**Build dependency**: `ovos-core[lgpl]`'s `fann2` wheel needs a `swig2.0` binary specifically
(not just `swig`) — confirmed the build fails with `Couldn't find swig2.0 binary!` without it.
OVOS's own Dockerfile handles this with a symlink shim:
```
apt-get install -y libfann-dev build-essential python3-dev git swig pkg-config
ln -s /usr/bin/swig /usr/bin/swig2.0   # if not already present
```

**Freeze the constraints file at build time**, don't point to the live URL at runtime — pull
it once during the Dockerfile build and `COPY` it in as a local file, so a future edit to
OVOS's `constraints-alpha.txt` upstream can't silently change what a rebuild installs. Still
gives us OVOS's own coordinated version combination, just frozen at build time rather than
floating.

### Skill discovery — confirmed working, but only after ~90s on first boot

Skills installed via `ovos-skills`' own pip mechanism (not OVOS's `skills.list` file
convention) are found correctly via Python entry points — confirmed for real with
`skill-ovos-date-time`, which registers under the newer `opm.skill` group (not the older
`ovos.plugin.skill` group `ovos-skill-boot-finished` uses, which logs a harmless deprecation
warning but still loads fine). `find_skill_plugins()` finds both correctly.

**What looked like a blocking upstream bug, but wasn't**: `ovos-core`'s `SkillManager` waits
for `IntentService` to report ready over the bus (`mycroft.intents.is_ready`) before loading
any skills — confirmed by reading `ovos_core/skill_manager.py` directly. Chased this for a
while suspecting a genuine bug (the message looked unhandled), before confirming it's real:
`IntentService`'s pipeline-plugin loading step (`ovos-m2v-pipeline`,
`ovos-persona-pipeline-plugin`) downloads ML models from HuggingFace Hub on first run, which
took ~90 seconds total in this sandbox. Every earlier attempt gave up well before that
(compounded by an unrelated sandbox quirk: background processes here don't survive across
separate tool calls, only within one — several early attempts looked "stuck" because the
process had simply died between calls, not because anything was actually hanging).

**Confirmed end-to-end once given the full ~90s**: `IntentService is ready` →
`ovos-skill-date-time.openvoiceos` loads → `Skills Manager is ready` → `ovos-core is ready!
additional skills can now be loaded`. Practical implication for the real add-on: don't set an
aggressive healthcheck start-period, and don't assume something's wrong if the log looks quiet
for the first minute or so on a fresh install specifically (subsequent boots should be much
faster once the HuggingFace models are cached on the `/share` volume).

### The synchronous question/answer mechanism — confirmed working, exact messages captured

Found by reading `ovos_bus_client.scripts.ovos_say_to` (the source behind the `ovos-say-to`
CLI tool, itself confirmed present as a console script) and `ovos_workshop.skills.ovos`'s
`speak()` method directly, rather than guessing message names:

- **Inject an utterance**, exactly as if a real STT had transcribed it:
  ```python
  bus.emit(Message("recognizer_loop:utterance", {"utterances": [utt], "lang": lang}))
  ```
- **The response** comes back as (confirmed via `SpecMessage.SPEAK` in
  `ovos_workshop/skills/ovos.py` — note this is `'ovos.utterance.speak'`, not the older
  classic `"speak"` message some tooling still expects):
  ```python
  bus.on('ovos.utterance.speak', handler)
  # message.data = {'utterance': str, 'expect_response': bool, 'meta': {'skill': skill_id, ...}, 'lang': str}
  ```

**Confirmed for real, full round trip, twice**: first via raw bus messages (sent
`recognizer_loop:utterance` with `"what time is it"`, received `ovos.utterance.speak` back
with `{'utterance': 'It is ten twenty two', ...}`), then again — the stronger confirmation —
running the *actual* `api.py` code as a real `uvicorn` HTTP server and sending it a genuine
`POST /ask` request:
```
$ curl -s http://localhost:8500/health
{"bus_connected":true}
$ curl -s -X POST http://localhost:8500/ask -d '{"utterance": "what day is it today"}'
{"utterance":"It is 04 August","skill":"ovos-skill-date-time.openvoiceos"}
```
This is the exact emit-and-wait pattern `ovos-persona`'s `api.py` already uses
(`emit_and_wait_either`) — same shape applies here.

**Concurrent requests were NOT tested** — `api.py` serializes requests with a module-level
lock rather than matching responses to requests via OVOS's session system
(`context["session"]["session_id"]`, which a skill's `speak()` call propagates via
`message.forward()`). That session-based approach is plausible from reading the source, but
unverified, so `api.py` doesn't rely on it yet — see its own docstring for the reasoning. A
lock means concurrent requests queue instead of racing to claim the wrong answer; revisit once
concurrency genuinely matters.

**Not yet decided**: skills-first-then-fallback routing (per `DEVELOPER.md`'s v1 scope) isn't
built — this spike only confirmed a single skill answering directly. `ovos-core`'s own
fallback-skill cascade (`ovos-skill-fallback-chatgpt`, `ovos-skill-fallback-unknown`) should
handle "nothing matched" cases without us building custom routing logic, per the
`DEVELOPER.md` architecture note, but that specifically hasn't been tested yet.

## Future idea: an HA-aware PHAL plugin (revised, more concrete)

First raised mid-investigation as a possible fix for what looked like stuck skill loading
(PHAL normally reports network/internet connectivity status to `ovos-core`) — turned out not
to be the actual cause of anything encountered that night, but the idea itself was worth
refining rather than dropping.

**Not**: `ha-ovos-integration` talking to a standard, unmodified PHAL instance. PHAL is built
to give OVOS awareness of *its own physical platform* — LED rings, physical buttons, volume
mixers, wifi setup UI, device pairing — the things a real OVOS device (a Mark 1/2, a Pi with a
speaker) manages itself. In this project's architecture, HA already owns almost everything
PHAL would normally cover: HA knows its own network status, HA's own media players/Assist
handle volume and playback, HA's satellite entities or the Wyoming-wakeword layer handle mic
mute. Wiring the integration to a stock PHAL would mostly duplicate state HA already owns —
two systems both believing they're authoritative over the same thing.

**Instead**: a **custom PHAL plugin running on the `ovos-core` side**, exposing real HA state
to OVOS skills through PHAL's own existing, standardized plugin interface — something skills
already know how to use, no new API to invent per skill. Concretely: a skill asking "is it
dark outside" could read a HA lux/sun sensor through this PHAL plugin instead of every skill
needing its own bespoke HA API client; OVOS's own "do I have network" status could just always
reflect HA's own, already-known state instead of OVOS trying to detect it independently.

This is a clean, self-contained extension of the architecture already built here (`ovos-core`
as the skill runtime) rather than something that touches `ha-ovos-integration` at all. Worth
picking up once more skills are installed and a real need for HA-state-aware skills shows up —
not before, since it's speculative without a concrete skill that needs it yet.

## Not yet done

- **The shared-bus binding (`websocket.host: 0.0.0.0`) is unverified for real
  container-to-container traffic.** `run.sh` sets it, reasoning from `ovos-skills` never
  needing to (its bus is deliberately private, defaults are enough there) — but nothing so far
  has tested bus access from a genuinely separate container. First real test is wiring
  `ovos-skills` to point at this bus.
- `intents.blacklisted_pipelines` currently blacklists `ovos-common-query-pipeline-plugin` and
  `ovos-persona-pipeline-plugin` in `run.sh` — kept deliberately (see "Kept anyway, on their
  own merits" above), not a loose end.
- **`padacioso`'s accuracy trade-off** (see above) is unverified beyond this one utterance —
  worth testing against a wider range of phrasings once more skills are installed.
- Skills-first vs. fallback routing logic (v1 scope from `DEVELOPER.md`) unbuilt and untested.
- Hot-install via the shared bus (`ovos-skills` emitting `ovos.skills.install.complete` onto
  *this* add-on's bus instead of its own private one) — `ovos-skills` itself hasn't been
  changed to point at a shared bus yet; still using its own private, internal one.
- `/share/mycroft/mycroft.conf` integration beyond the `websocket`/`intents` blocks `run.sh`
  writes — not yet checked whether `ovos-core`'s own config loading conflicts with or needs
  anything different from the convention the other four add-ons already share.
- v2 (proactive speech via `assist_satellite.announce`) — explicitly out of scope until v1
  exists, per `DEVELOPER.md`.
- HA conversation-agent side: nothing built yet on the `ha-ovos-integration` side to actually
  call this add-on's `/ask` endpoint as a conversation agent.
- Concurrent request handling (see above) — serialized via a lock, not session-matched.
