# OVOS Core

🚧 **Not built yet.** This is a skeleton (`config.yaml` only) plus a thorough writeup of a
sandbox spike that verified the whole mechanism works end-to-end, before any add-on code was
written. Read this before touching `Dockerfile`/`run.sh`/`api.py` — it saves re-deriving
everything below the hard way.

## What this add-on is for

The "next big piece" described in `haos-ovos-addons/DEVELOPER.md`: a real, persistent
`ovos-core` skill runtime — the only thing in this whole project that actually *loads* skills
and can make one respond to a question. Everything built so far (`ovos-skills`, `ovos-persona`,
the Wyoming bridges) makes OVOS components installable/configurable but not "alive" — see
`DEVELOPER.md`'s "Next big piece" section for the full reasoning on why that gap exists and
the architecture decided for closing it (shared messagebus, `ovos-skills` staying separate,
hot-install via that shared bus, v1/v2 scope split).

## Verified in a sandbox spike, not yet packaged into this add-on

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

**Confirmed for real, full round trip**: emitted `recognizer_loop:utterance` with
`"what time is it"`, received `ovos.utterance.speak` back with
`{'utterance': 'It is ten twenty two', 'meta': {'skill': 'ovos-skill-date-time.openvoiceos'}}`
— a genuinely correct, computed answer, not a stub. This is the exact emit-and-wait pattern
`ovos-persona`'s `api.py` already uses (`emit_and_wait_either`) — same shape applies here.

**Not yet decided**: skills-first-then-fallback routing (per `DEVELOPER.md`'s v1 scope) isn't
built — this spike only confirmed a single skill answering directly. `ovos-core`'s own
fallback-skill cascade (`ovos-skill-fallback-chatgpt`, `ovos-skill-fallback-unknown`) should
handle "nothing matched" cases without us building custom routing logic, per the
`DEVELOPER.md` architecture note, but that specifically hasn't been tested yet.

## Considered during the spike: an HA-aware PHAL plugin

Raised as a possible fix for what looked like a stuck skill-loading process (PHAL normally
reports network/internet connectivity status to `ovos-core`). Turned out not to be the actual
cause — the real blocker was first-boot model downloads, unrelated to network/internet
*status* reporting. The idea itself is still worth keeping: a PHAL plugin giving OVOS
awareness of HA (exposing HA entities as OVOS "hardware" concepts, or the reverse) is a
genuinely separate, self-contained idea from this add-on's core purpose, not evaluated further
this session.

## Not yet done

- No `Dockerfile`/`run.sh`/`api.py` written — this is a skeleton `config.yaml` only.
- Skills-first vs. fallback routing logic (v1 scope from `DEVELOPER.md`) unbuilt and untested.
- Hot-install via the shared bus (`ovos-skills` emitting `ovos.skills.install.complete` onto
  *this* add-on's bus instead of its own private one) — `ovos-skills` itself hasn't been
  changed to point at a shared bus yet; still using its own private, internal one.
- `/share/mycroft/mycroft.conf` integration for this add-on specifically — not yet checked
  whether `ovos-core`'s own config loading conflicts with or needs anything different from the
  convention the other four add-ons already share.
- v2 (proactive speech via `assist_satellite.announce`) — explicitly out of scope until v1
  exists, per `DEVELOPER.md`.
- HA conversation-agent side: nothing built yet on the `ha-ovos-integration` side to actually
  call this add-on's future synchronous endpoint as a conversation agent.
