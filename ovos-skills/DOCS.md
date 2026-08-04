# OVOS Skills

🚧 **v0.0.x — work in progress.**

## Current architecture: one isolated Python venv per skill

Rebuilt after a real, hardware-confirmed incident: installing `skill-ovos-wolfie` pulled in a
newer `ovos-workshop` than `ovos-core` and `ovos-skill-dictation` are compatible with,
corrupting the single, shared `site-packages` environment every skill and `ovos-core` used to
share. Everything below the "Historical: the old shared-site-packages design" heading
documents that earlier design and the real bugs it took to get *it* working — kept for
history, not current behavior.

**No more shared Python environment, no more `ovos-core`/`ovos-messagebus`/`SkillsStore`
dependency at all.** Each skill gets its own `virtualenv`, created fresh at install time
directly by this add-on (`pip install <source>` into that venv, then `<venv>/bin/
ovos-skill-launcher <skill_id>` to run it) — structurally impossible for one skill's
dependencies to affect another's, or `ovos-core`'s own.

**Persistence model — deliberately minimal.** Venvs themselves live in this container's own
filesystem layer, which does NOT survive a rebuild/update (same underlying fact the old
design also had to work around, just handled completely differently now). The *only* thing
persisted to `/share/ovos-skills/manifest.json` is `{skill_id: {source, package_name}}` — a
few bytes per skill. On every container start, every venv is rebuilt from scratch (a fresh
`pip install <source>` per manifest entry) before any skill is launched. `settings.json` is
untouched by any of this — it already lived on `/share` via `XDG_CONFIG_HOME`, keyed by
`skill_id`, independent of where the skill's own code lives.

This also incidentally eliminates the entire class of `importlib.metadata`-in-a-long-running-
process unreliability the old design spent real hardware-testing time chasing (see the
historical section) — there's no shared `site-packages` left to scan; the manifest file is
now the sole, always-fresh-off-disk source of truth for what's installed.

## API

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true}` — always true now; kept for API-shape compatibility, no messagebus connection exists to report on anymore |
| `GET /catalog` | Proxies the official, curated `skills.json` feed |
| `GET /skills` | `{"skills": [{"skill_id", "package_name", "source", "version"}, ...]}` — straight from the manifest, version looked up live per-skill via that skill's own venv's pip |
| `GET /skills/running` | Per-skill process status (running/dead, PID, restart count) |
| `POST /skills/install` | Body `{"url": "https://github.com/..."}`. Async — returns `{"status": "pending", "poll": "..."}` immediately |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result; success includes the confirmed-real `skill_id` |
| `DELETE /skills/{skill_id}` | `rm -rf` of that skill's own venv + manifest removal — no protected-package list needed anymore, a skill's venv structurally can't touch anything critical |
| `GET /skills/{skill_id}/settingsmeta` | Unchanged shape; `package_name` query param now optional/ignored — the manifest already has the confirmed-real name |
| `GET`/`PUT /skills/{skill_id}/settings` | Unchanged — always was independent of where the skill's code lives |

## Configuration

| Option | Description |
|---|---|
| `allow_pip` | No longer read by this add-on (was `SkillsStore`'s own gate) — kept as a schema option for now, not wired to anything |
| `log_level` | `debug`, `info`, `warning`, or `error` |

## Known limitations, current design

- **Reinstall-on-restart cost.** A rebuild/update means every installed skill gets a fresh
  `git clone`/PyPI fetch + `pip install` at container start, not instant. Accepted tradeoff
  for the isolation guarantee — see the wolfie incident above for what the alternative costs.
- **Needs network at boot to restore previously-installed skills.** If GitHub/PyPI is
  unreachable when the container starts, previously-working skills won't come back until
  connectivity returns (retried by the normal container-restart path, not on a tight retry
  loop yet).
- **Manifest doesn't pin an exact version.** A rebuild re-fetches whatever `source` currently
  resolves to (e.g. a git URL's default branch HEAD), not necessarily byte-identical to what
  was running before. OVOS skills are generally not pinned to exact versions by their own
  catalog either, so this matches the ecosystem's own looseness rather than introducing new
  risk — but worth knowing.
- **Disk cost of duplication.** Every venv carries its own copy of `ovos-workshop`,
  `ovos-bus-client`, etc. — real but small (megabytes, not gigabytes) on typical HAOS
  hardware; not sized for a Raspberry Pi Zero.

---

## Historical: the old shared-site-packages design

Everything below this line describes the *previous* architecture (all skills sharing one
Python environment, bridged through `ovos-core`'s own `SkillsStore`/`ovos-messagebus`) and the
real bugs it took to get that design working on real hardware. Superseded by the venv-per-skill
rework above — kept for history, since several of the underlying `importlib.metadata`
findings are genuinely useful background even though the fix taken here was to sidestep the
whole problem rather than patch it further.

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

- **No way to update an already-installed skill.** Confirmed directly: calling `pip install
  <package>` again (matching `SkillsStore`'s exact call pattern — `handle_install_skill()`
  never passes `--upgrade`) on an already-installed package is a silent no-op, version stays
  the same. Genuine, small upstream code gap, not a release-drift issue like the ones above —
  filed a PR adding a `skills.installer.upgrade` config option (same pattern as the existing
  `allow_alphas`/`break_system_packages` flags), verified it actually advances the version
  before submitting: [OpenVoiceOS/ovos-core#843](https://github.com/OpenVoiceOS/ovos-core/pull/843).
  Not usable from our side yet — same PyPI-lag problem as uninstall below, since it needs a
  new `ovos-core` release to reach us.
- **`DELETE /skills/{id}` bypasses `SkillsStore` entirely now** — see the section below for
  why, and for the four real bugs (not just one) it took to actually get this working
  end-to-end, confirmed on real hardware across multiple rebuild cycles. Fixed, but
  deliberately not the long-term destination.
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

**Known remaining fragility**: `get_settingsmeta`'s own `importlib.metadata.files(real_name)`
call (after resolving the name via the now-fixed `_find_installed_package`) still uses the
same `importlib.metadata` approach proven unreliable for uninstall. It tested successfully
earlier, but that may have been a timing coincidence (tested shortly after a fresh container
start) rather than a guarantee — hasn't been re-verified against a package that's been sitting
restored for a while, the way the uninstall bug only showed up after that. Worth switching to
the same dist-info-scanning approach if it turns out to matter.

## `DELETE /skills/{id}` now works — via a local bridge, not SkillsStore

Was documented as broken (upstream stub); fixed, but deliberately as a temporary bridge, not
the destination. `SkillsStore.handle_uninstall_skill()` is fixed in `ovos-core`'s `dev`
branch already — the actual blocker is that `dev` needs newer `ovos_bus_client`/`ovos-config`
than `ovos-messagebus` currently provides, a release-coordination problem across two repos
that no PR against this add-on could resolve. So `DELETE` now bypasses `SkillsStore`/the
messagebus entirely and runs `pip uninstall` directly — same approach as the `/skills` list
and the persist-on-install logic already use.

This took three separate, genuinely confirmed bugs to actually get working end-to-end —
worth recording all three, since each one looked fixed after the previous one but wasn't:

1. **Wrong package name.** `_find_installed_package()` originally used
   `importlib.metadata.distributions()` to resolve the catalog's `package_name` hint to the
   real installed name. For a package restored via `run.sh`'s file-copy (rather than a `pip
   install` run inside this process), that call returned it not being found at all —
   confirmed directly via logging: 85 packages seen, the target skill genuinely on disk and
   shown by `pip list`, not among them. Uninstall silently fell back to a guessed,
   nonexistent package name, and `pip uninstall` reported success ("Skipping ... as it is not
   installed") while touching nothing.
2. **`reload()` alone wasn't enough, `invalidate_caches()` wasn't either.** Tried both
   `importlib.reload(importlib.metadata)` and `importlib.invalidate_caches()` before that
   call — same 85-packages-seen, target-absent result, confirmed again via logging. Whatever
   the exact cause, `importlib.metadata` run inside this long-running process is not
   trustworthy for packages that appeared via file-copy. Fixed by switching
   `_find_installed_package()` to a fresh `pip list` subprocess instead — the same mechanism
   `/skills` already used successfully.
3. **`no RECORD file was found`.** With the right package name finally in hand, `pip
   uninstall` itself failed — the persist/restore cycle doesn't reliably keep a package's
   `RECORD` file intact. Added a fallback that finds the package's dist-info directory
   directly (PEP 503 normalized-name match) and its module(s) via `top_level.txt`, deleting
   both without needing `RECORD` at all.
4. **Found on top of all that**: `_remove_persisted_package()` (the PERSIST_DIR-cleanup half,
   separate from removing the package from live site-packages) still used the same unreliable
   `importlib.metadata.files()` approach bug #1 already disproved — just in a different
   function I'd missed. It silently removed nothing from `PERSIST_DIR`, so the "uninstalled"
   skill reappeared on the very next rebuild. Confirmed this exact failure on real hardware
   (uninstalled, verified gone, forced a rebuild, it was back), then consolidated both
   site-packages and `PERSIST_DIR` removal into one shared, dist-info-scanning function so
   there's only one mechanism to get right, not two silently-different ones.

**Final verification, on real hardware, not a sandbox**: uninstalled `ovos-skill-date-time`,
confirmed gone from `/skills`, forced a genuine rebuild (version bump + Supervisor update),
confirmed it stayed gone. Repeated once more after the `PERSIST_DIR` fix specifically, since
bug #4 was the one that had passed every earlier check right up until a rebuild.

Two more things confirmed by testing before trusting them:

- **Protected packages.** Mirrors `SkillsStore`'s own hardcoded fallback list
  (`ovos-core`, `ovos-utils`, `ovos-plugin-manager`, `ovos-config`, `ovos-bus-client`,
  `ovos-workshop`) — checked independently of our own `constraints` file, not by reusing it.
  That file is deliberately empty (see the stale-constraints fix above), and `SkillsStore`
  reads protected packages from that *same* file, so reusing it here would have silently
  disabled protection entirely. Confirmed: attempting to uninstall `ovos-core` is refused.
- **`sys.executable -m pip`, not a bare `pip`.** A bare `["pip", "uninstall", ...]` reported
  success while silently targeting a *different* Python's pip than the one actually running
  the add-on — `pip show` afterward still showed the package installed. Switched to
  `[sys.executable, "-m", "pip", ...]` everywhere (matching `SkillsStore`'s own approach),
  including the `/skills` list endpoint, which had the same bare-`pip` pattern.

**Revisit once upstream catches up**: prefer switching back to calling `SkillsStore`'s real
uninstall over maintaining this bridge indefinitely, once a PyPI release resolves the
`ovos-messagebus` version conflict.
