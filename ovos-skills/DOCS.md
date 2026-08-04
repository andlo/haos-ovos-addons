# OVOS Skills

🚧 **v0.0.x — work in progress.** See the "What was fixed on real hardware" section below
before trusting the happy path blindly.

## What it does

Installs, lists, and removes OVOS skills via a small HTTP API, bridging to `ovos-core`'s own
`SkillsStore` (`ovos_core.skill_installer`) over a private internal `ovos-messagebus` that
never leaves this container. Not `ovos_skill_manager` (OSM) — that project's own README says
it stopped being supported after ovos-core 0.0.8.

Called by [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration), which manages
skills as config subentries — one per installed skill, in the same place as everything else
in HA.

## API

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` |
| `GET /catalog` | Proxies the official, curated `skills.json` feed (36 skills as of the last check) |
| `GET /skills` | Lists installed skills — **heuristic**: pip packages named `ovos-skill-*`/`skill-*`, not a confirmed mechanism |
| `POST /skills/install` | Body `{"url": "https://github.com/..."}`. Async — returns `{"status": "pending", "poll": "..."}` immediately, doesn't block on pip |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result |
| `DELETE /skills/{skill_id}` | Same async pattern as install |

## Configuration

| Option | Description |
|---|---|
| `allow_pip` | Gates `SkillsStore` itself — it refuses to act at all if this is off |
| `log_level` | `debug`, `info`, `warning`, or `error` |

## What was fixed on real hardware

1. **`error: externally-managed-environment` (PEP 668)** — `SkillsStore`'s own pip calls need
   `skills.installer.break_system_packages: true` in `mycroft.conf`, which it already
   supports but wasn't set. Same class of issue as the other four add-ons hit repeatedly.
2. **Synchronous design timed out.** The first version blocked the HTTP request until pip
   finished — timed out against a 30s client, and would've been a poor fit for eventually
   being called from a HA config flow (which expects quick responses). Rebuilt as
   fire-and-poll instead.
3. **`SkillsStore`'s default constraints file is stale.** It pins
   `ovos-skill-date-time<0.5.0,>=0.4.20`, but that skill's actual `dev`-branch HEAD is
   `1.1.14a2` — installing it via the default "stable" pin list fails immediately with
   `ResolutionImpossible`. This is an upstream OVOS release-management gap (the pin list
   hasn't tracked the skill repo's own state), not a bug on our side. Worked around by
   pointing `skills.installer.constraints` at an empty local file instead of OVOS's default
   URL — `SkillsStore` still requires a valid, existing constraints file, an empty one just
   pins nothing.
4. **Uninstall is currently a stub upstream, staying that way for now.** The published
   `ovos-core` (2.1.1, PyPI) has `handle_uninstall_skill()` return
   `"pip uninstall not yet implemented"`. `dev` has a real implementation, but switching to
   it broke the build: `ovos-core@dev` requires much newer `ovos_bus_client`/`ovos-config`
   than `ovos-messagebus` provides, and `ovos-messagebus`'s own `dev` branch doesn't match
   either (confirmed via `pip check` — real conflicts remain, two independently drifting dev
   branches, not a matched pair). Reverted to PyPI: install is fully verified working
   end-to-end; **`DELETE /skills/{id}` currently fails with "pip uninstall not yet
   implemented"** until a PyPI release catches up or a genuinely compatible combination is
   found.

## Known limitations

- **`DELETE /skills/{id}` doesn't work yet** — upstream `SkillsStore.handle_uninstall_skill()`
  is a stub on the current PyPI `ovos-core`. See "What was fixed on real hardware" above.
- `GET /skills` (list installed) is a naming-convention heuristic — confirmed working against
  a real installed skill (`ovos-skill-date-time`), but still just a heuristic, not a
  guaranteed-correct mechanism for skills that don't follow the naming convention.
- Explicitly does not make skills respond to voice queries — that needs OVOS's
  messagebus/HiveMind bridged into Assist, which doesn't exist yet. This add-on only makes
  skills installable and configurable.
- Multiple skills share one Python environment (unlike `ovos-docker`'s one-container-per-skill
  model) — a deliberately accepted dependency-conflict risk, not a solved problem.

## Skills now survive an add-on rebuild/update

Was a known gap; fixed. `pip install` writes into the container's own filesystem layer, which
does not survive a rebuild — confirmed on real hardware: an installed skill wiped clean by the
next version bump.

Fixed with a before/after `pip list` diff, not a pip-redirection trick. `PIP_TARGET`/
`PYTHONPATH` was tried first and rejected after directly testing it: it broke pip's own build
isolation for new installs (`pip subprocess to install build dependencies did not run
successfully`), and packages installed that way weren't found by `importlib.metadata` at all
even with the target directory added to `sys.path` — which would have silently broken the
settingsmeta/settings endpoints built earlier, since they depend on it.

What actually works, verified end-to-end **on real hardware, not just in a sandbox**: installed
`skill-ovos-date-time`, confirmed it in `/skills`, forced a genuine rebuild (a real version
bump + Supervisor update, not just a restart — a restart alone wouldn't have wiped anything;
this is the exact operation that lost the skill before), and after the new container started,
`/skills` still showed `ovos-skill-date-time`. Went one step further: fetched its
`settingsmeta.json` again post-rebuild and got the correct `show_time` checkbox field back —
confirming not just that the files survived, but that `importlib.metadata`-based detection
(what both `/skills` and the settingsmeta endpoint depend on) works correctly against a
restored package, not only a freshly-`pip install`ed one.

**Minor loose end, not functionality-blocking**: `_persist_new_packages`'s own `LOG.info` line
never showed up in the container log, even though the persist step demonstrably ran (the
restore step on the next start found real files to copy). Likely a `logging` configuration
gap — this logger was never explicitly wired to a handler/level, so it may be silently
swallowed rather than actually failing. Worth a quick look, not urgent.
