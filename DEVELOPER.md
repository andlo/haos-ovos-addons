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
  works). Pointing that emit at the *shared* bus instead of its own private one means `ovos-core`
  can listen for it and reload its skill list immediately — no add-on restart needed to pick up
  a newly-installed skill.
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

Genuinely not meaningful until `ovos-core` exists — an installed skill is inert either way right
now, no matter how good it is, since nothing loads or runs it. Worth deciding once the runtime
is real, not before.

### `ovos-core` add-on: skeleton scaffolded, sandbox spike confirmed the mechanism works

`config.yaml` exists (`ovos-core/`); `Dockerfile`/`run.sh`/`api.py` don't yet. Before writing
those, a full sandbox spike confirmed the whole chain works end-to-end — see `ovos-core/DOCS.md`
for the complete writeup (exact install recipe copied from OVOS's own official Docker image,
the `swig2.0` build quirk, the ~90s first-boot model-download caveat that initially looked like
a stuck upstream bug but wasn't, and the exact bus messages for the synchronous Q&A mechanism).
Headline result, confirmed for real, not assumed: sent `"what time is it"` in, got back
`"It is ten twenty two"` from a genuinely running `ovos-skill-date-time`, computed correctly.

Also considered mid-spike: an HA-aware PHAL plugin, raised as a possible fix for what looked
like stuck skill loading (PHAL normally reports network/internet status to `ovos-core`). Turned
out not to be the actual cause, but the idea itself — giving OVOS awareness of HA, or exposing
HA entities as OVOS "hardware" concepts — is separate and self-contained, worth keeping for
later, not evaluated further this session.

## Original 3-repo plan (superseded, kept for history)

The original idea was three repos: this one, a forked `ovos-skill-browser` for browsing/installing
skills externally, and a deferred `haos-ovos-skills` for actually running them. In practice:
`ovos-skill-browser` was archived once `ha-ovos-integration`'s config subentries made a
standalone browse page redundant, and `haos-ovos-skills` was un-deferred, built, and then merged
into this repo as the `ovos-skills` add-on rather than staying separate — see this repo's own
commit history and `ovos-skills/DOCS.md` for the full reasoning. Neither ran skills live; that's
the `ovos-core` add-on described above, not yet built.
