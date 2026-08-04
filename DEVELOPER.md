# Developer notes — HA-OVOS project

🚧 Work in progress.

## The idea

Make it easy for an ordinary HAOS user to discover and use OpenVoiceOS (OVOS) — without them
needing to know it's OVOS. HAOS users already know the pattern "go to the Add-on Store, install,
fill in a form". Most of the technical foundation (Wyoming bridges, persona server, `SkillsStore`)
already exists in the OVOS ecosystem. The job is packaging and integration, not inventing
something new.

## Current state (supersedes the original 3-repo plan below)

Two repos now, not three — `ovos-skill-browser` and the standalone `haos-ovos-skills` were both
folded into other things (see each repo's own README for the "why", they're archived not
deleted):

- **This repo** (`haos-ovos-addons`) — five Supervisor add-ons: `ovos-wyoming-tts`, `-stt`,
  `-wakeword`, `ovos-persona`, `ovos-skills`. All confirmed working on real hardware; see each
  add-on's own `DOCS.md` for what's verified and what isn't.
- **[ha-ovos-integration](https://github.com/andlo/ha-ovos-integration)** — the HA integration:
  shared config (language/location/units) and per-skill management via config subentries, both
  confirmed working end-to-end on real hardware.

## Next big piece: a shared messagebus, and a real `ovos-core` runtime

Everything built so far makes OVOS components *installable* and *configurable* from HA's own
UI. None of it makes a skill actually *respond* to anything — confirmed and discussed at length,
not assumed: `ovos-skills` only installs a skill's Python package; nothing loads it as a live,
running skill connected to a real intent-matching messagebus. `ovos-persona` and the Wyoming
bridges don't touch OVOS's own intent system at all — persona is a standalone chat-completion
server, and the Wyoming bridges are audio plugins for HA's *own* Assist pipeline.

### The architecture, settled after working through it properly

**One shared `ovos-messagebus`, hosted by a new `ovos-core` add-on**, reachable by every other
OVOS add-on on Supervisor's internal network (the same way add-ons already reach each other by
hostname throughout this project) — not each add-on running its own private, isolated bus, which
is what happens today (`ovos-skills`' bus, for example, never leaves its own container).

- **`ovos-core`** (new add-on): the actual skill runtime — intent matching, skill manager,
  `ovos-core`'s own built-in fallback-skill cascade (`ovos-skill-fallback-chatgpt`,
  `ovos-skill-fallback-unknown` — both already in the catalog, no new mechanism needed), and a
  synchronous question-in/answer-out HTTP endpoint for HA's Assist pipeline to call as a
  conversation agent, same integration point `ovos-persona` already uses. Runs as one
  **persistent, long-running process**, not spun up per request — required for a skill to hold
  any state at all (an in-progress timer, a multi-turn conversation), and what makes the v2
  proactive-speech extension (below) an addition later rather than a rewrite now.
- **`ovos-skills` stays exactly as it is** — the isolated, now-thoroughly-stability-tested
  install/uninstall mechanism, deliberately *not* merged into `ovos-core`'s process. Installing
  or removing a skill is a different, riskier operation (arbitrary pip dependencies, potential
  crashes) than running one, and keeping them apart means a bad skill install can't take down
  the live runtime, and a runtime bug can't corrupt an install in progress.
- **"Hot install" without a restart**: `ovos-skills` already emits
  `ovos.skills.install.complete` internally (confirmed — it's how its own async job status
  works). **Revised, see "Skill runtime: the real design question" below** — pointing the emit
  at the shared bus alone doesn't solve this the way this paragraph originally assumed. A skill
  installed via `ovos-skills`' pip mechanism lands in *its own container's* `site-packages`,
  physically absent from `ovos-core`'s separate container/filesystem — a bus message can't
  make files appear where they don't exist. The persist/restore mechanism `ovos-skills` already
  has (`PERSIST_DIR` on the shared `/share` volume, proven surviving rebuilds) is the piece
  that actually solves file availability; a bus message on top of that can still trigger
  `ovos-core` to reload once the files are actually there.
- **Other OVOS add-ons follow the same pattern later**: `ovos-persona`, and eventually
  `ovos-common-query`, OCP (media-playback skills), etc. — each its own add-on, all talking to
  the one shared bus, all reading/writing the one shared `/share/mycroft/mycroft.conf` (already
  built and proven across five add-ons — new ones just need to follow the same convention).

**Why separate add-ons instead of one big one**: stability and independent lifecycles — updating
`ovos-skills` (or eventually OCP, common-query, etc.) shouldn't require rebuilding or risk
breaking `ovos-core` itself. Matches OVOS's own recommended multi-container pattern
(`ovos-docker`), not something invented here.

**`ovos-core` must be pinned hard** to a specific, individually-verified commit from day one —
not `@dev`, not a loose version range. Directly, repeatedly confirmed this session:
`ovos-persona-server`'s `@dev` chase cost real, hours-long instability (see `ovos-persona`'s
`DOCS.md`) purely from an unpinned `ovos-persona>=0.9.0a6` dependency continuing to drift
underneath a fixed commit. `ovos-core` sits at the center of this new architecture; the same
mistake here would be worse, not equally bad.

### Skill runtime: the real design question (needs its own session, not decided yet)

Raised while working out how `ovos-skills` and `ovos-core` should actually connect over the
shared bus, and it turned into something bigger: a genuine architecture question about *where
skills should run at all*, not just how two add-ons talk to each other.

**The bus address problem that started this.** `ovos-core`'s own `run.sh` writes
`websocket.host: "0.0.0.0"` into the *shared* `/share/mycroft/mycroft.conf` — correct as a
*bind* address (listen on all interfaces), wrong as a *connect* address for any other
container to reach it. Since the file is genuinely shared (same bytes, read by every add-on),
that one key can't hold both a correct bind value for `ovos-core` and a correct connect value
for everyone else at once. `ovos_bus_client.MessageBusClient(host=..., port=...)` does accept
explicit overrides bypassing shared config entirely (confirmed by reading its constructor) —
usable for code we own (our own `api.py`), but not for `ovos-skill-installer`, the external
`SkillsStore` process `ovos-skills` runs, which has no such override and would always read
whatever's in the shared file.

**Checked how OVOS's own official Docker deployment solves this** — SSH'd into a real,
independently-running install (10-day uptime, healthy). Its skills run each in their *own*
container (`ovos-skill-launcher <skill_id>`, `docker.io/smartgic/ovos-skill-*` images) — not
pip-installed into `ovos-core`'s own `site-packages` the way this project's `extra_pip_packages`
currently works. Its shared config genuinely does use `"websocket": {"host": "0.0.0.0"}` across
every container, bind and connect both. **Why that works there and can't be copied here**:
confirmed via `docker inspect --format '{{.HostConfig.NetworkMode}}'` — every one of its
containers runs `network_mode: host`. They all share the *host machine's own network stack*
directly, not Docker's normal isolated bridge network (which is what every Supervisor add-on
in this project uses, each with its own IP, reached by hostname). `"0.0.0.0"`/`"localhost"`
resolving correctly everywhere is a consequence of host networking, not of one-container-per-skill
as an architecture. Running HAOS add-ons in host network mode would be a real, unwanted
security/isolation regression from normal add-on convention — not adopted here. The address
problem above is still real and still needs the hostname-based (or `PERSIST_DIR`-copy) approach
already discussed, regardless of which skill-runtime shape gets picked below.

**The actual, separate question this surfaced**: should skills run *inside* `ovos-core`'s own
process (today's model — `extra_pip_packages` installs into its `site-packages`, loaded via
entry points), or in a separate container, closer to OVOS's own official pattern? Real tradeoff
on both sides:
- **Inside `ovos-core`** (current): simple, fewer moving parts, already proven working
  end-to-end. Real risk: a skill's own bad dependency, or a skill that crashes hard, shares
  `ovos-core`'s process and address space with the actual intent-matching engine — nothing
  isolates the runtime from the skills running inside it.
- **Separate container(s)**, matching OVOS's own official architecture more closely: a bad
  skill can't take down `ovos-core` itself, skills can restart/update independently. Real cost:
  more infrastructure, and — critically — one-add-on-per-skill (which is genuinely how
  `ovos-docker` does it, 15+ separate skill containers) doesn't fit how a HAOS user browses
  the Add-on Store at all. Nobody wants to hunt through 30 individually-listed add-ons to find
  "date and time."

**Direction settled on, not yet built**: not one add-on per skill. Instead, something closer
to a **curated two-tier model**:
- A **default skills add-on/runtime** — ships with a small, chosen set of default skills
  already installed and running (revisiting "default installed skills" from earlier, now that
  `ovos-core` can actually run them), with room to add a few more from a short, *curated* list
  we've actually vetted for this environment — not the full open OVOS catalog. This is the
  "just works" tier for most users.
- A **separate, advanced/extra skills add-on** for open-ended installs — pip package name or
  `git+https://...` URL, anything from the catalog or beyond it. This is close to what
  `ovos-skills` already does today (open pip+git install, no curation) — the idea is to keep
  that *specific* risk (arbitrary code from an arbitrary URL) isolated in its own add-on,
  separate from the curated default set, so a risky advanced install can't destabilize the
  "just works" tier. Same isolation philosophy already applied to keeping `ovos-skills`
  separate from `ovos-core` in the first place — extended one level further.

This directly connects to two other open threads: the "self-hosted, curated skill catalog"
idea above (the curated tier's skill list is exactly what that catalog would need to define),
and "default installed skills" (the default tier's initial contents). Needs its own dedicated
design session before building anything — this paragraph is the direction, not a spec.

### Scope: v1 (synchronous) vs. v2 (proactive)

- **v1** — a skill can *answer* a direct question through the synchronous HTTP endpoint.
  Skills-first, falling back to persona/LLM only if nothing matches — precise, deterministic
  answers (e.g. "what's today's date") beat an LLM guessing. Explicitly does **not** cover a
  skill speaking on its own initiative (a timer firing, an alarm going off) — those need
  something to actively push audio into HA independent of a question being asked, which v1's
  synchronous request/response shape can't do.
- **v2** — the same persistent process also listens on the shared bus for `speak` messages that
  *aren't* a reply to an active HTTP call, and forwards them into HA via
  `assist_satellite.announce`/`tts.speak` (needs an API token back into HA). Additive to v1's
  process, not a rewrite — this is exactly why v1 has to be a persistent process from the start.
  Open question still unresolved: which physical speaker a given proactive alert should play on
  — OVOS's own skill has no concept of "which HA satellite entity"; likely a single, fixed,
  pre-chosen satellite for v2 rather than anything dynamic.
- **Messagebus exposure**: hosting the shared bus means binding beyond `localhost` within the
  container, and `ovos-messagebus` has no built-in access control. Scoped to Supervisor's own
  internal network, not exposed to the LAN — the same tradeoff any Docker-based multi-container
  OVOS install already accepts, not something new introduced here.

### Where this leaves "default installed skills"

Was "not meaningful until `ovos-core` exists" — no longer true, `ovos-core` now runs skills
for real. Superseded by "Skill runtime: the real design question" above, which folds default
skills into the curated-tier design rather than treating it as a standalone decision.

### `ovos-core` add-on: built, deployed, working end-to-end on real hardware

Confirmed for real, not assumed: `POST /ask {"utterance": "what time is it"}` →
`"It is eight twenty one"` from a genuinely running `ovos-skill-date-time`, on Alpine (same
base as every other add-on here), in under a second. Getting there took a long, genuinely
twisty investigation — see `ovos-core/DOCS.md`'s "The investigation" section for the full
trail, including two reasonable-looking fixes (a Debian base image switch, blacklisting
network-dependent pipelines) that turned out not to be the actual cause, kept anyway on their
own merits. Short version: what looked like an infinite hang was actually `padatious` (the
default, C++/SWIG-compiled intent matcher) genuinely taking 80-90+ seconds per match on this
specific weak hardware — not a bug. Fixed by switching the active matcher to `padacioso`, a
lightweight pure-Python drop-in already installed but never configured into
`ovos-config`'s own default `intents.pipeline` list.

Also considered mid-investigation: an HA-aware PHAL plugin, raised as a possible fix for what
looked like stuck skill loading (PHAL normally reports network/internet status to
`ovos-core`). Turned out not to be the actual cause of anything encountered, but the idea
itself — giving OVOS awareness of HA, or exposing HA entities as OVOS "hardware" concepts —
is separate and self-contained, worth keeping for later. Revised into something more concrete
in `ovos-core/DOCS.md`'s own "Future idea" section: not `ha-ovos-integration` talking to a
stock PHAL (HA already owns nearly everything PHAL would normally manage — network status,
volume, mic mute — so that would mostly duplicate state), but a **custom PHAL plugin on the
`ovos-core` side** exposing real HA state (a lux sensor, a door sensor) to skills through
PHAL's own existing plugin interface. Speculative until a concrete skill needs it.

### Three more forward-looking ideas, not yet acted on

**A self-hosted, curated skill catalog.** `ovos-skills`' `/catalog` endpoint currently proxies
OVOS's own official `skills.json` feed directly — no filtering, no vetting. The idea: fork
that feed (same move already made once for `ovos-skill-browser`, later archived once config
subentries made a standalone browse page redundant — see "Original 3-repo plan" below) and
maintain a curated subset, or an added `verified_haos: true`/`false` flag per entry. Refined
during discussion: less about skills that "behave badly" and more about skills that
*structurally* don't make sense in this environment at all — e.g. a desktop application
launcher skill assumes a desktop environment this project has no concept of; a skill needing
a GUI assumes a screen HAOS doesn't provide. Curating against a "doesn't fit this environment"
list, not just a "doesn't work well" one. Real tradeoff, not a free win: a fork needs active
syncing against upstream or it silently goes stale and stops offering skills the community
adds later — a genuine ongoing maintenance commitment, not a one-time fork-and-forget. This is
also exactly the list the curated default/advanced skill tiers (see "Skill runtime" above)
would need to define, so the two ideas converge into one piece of work, not two.

**Default installed skills.** Folded into "Skill runtime: the real design question" above —
the curated tier's initial contents.

**`ovos-config autoconfigure`-style setup choices in `ha-ovos-integration`'s config flow.**
OVOS's own `ovos-config` (v0.3.0+) ships an `autoconfigure` utility that picks sensible
TTS/STT plugin and voice defaults from language + an offline/online + male/female choice,
sourced from the community-maintained
[`OpenVoiceOS/lang_configs`](https://github.com/OpenVoiceOS/lang_configs) data. Right now,
`ha-ovos-integration`'s config flow pre-fills language/location/units from HA's own settings
but leaves TTS/STT plugin choice entirely to each Wyoming add-on's own, separate config —
no cross-add-on "pick offline vs. online, male vs. female" step exists. Adding one would mean
either shelling out to `ovos-config`'s own CLI (adds a dependency inside HA Core's Python
environment, unconfirmed whether that's clean) or reading `lang_configs`' underlying data
directly and replicating the selection logic ourselves (more control, more to maintain).
Neither approach attempted yet — worth spiking properly rather than guessing which is cleaner.

## Original 3-repo plan (superseded, kept for history)

The original idea was three repos: this one, a forked `ovos-skill-browser` for browsing/installing
skills externally, and a deferred `haos-ovos-skills` for actually running them. In practice:
`ovos-skill-browser` was archived once `ha-ovos-integration`'s config subentries made a
standalone browse page redundant, and `haos-ovos-skills` was un-deferred, built, and then merged
into this repo as the `ovos-skills` add-on rather than staying separate — see this repo's own
commit history and `ovos-skills/DOCS.md` for the full reasoning. Neither ran skills live; that's
the `ovos-core` add-on described above, now built and confirmed working.
