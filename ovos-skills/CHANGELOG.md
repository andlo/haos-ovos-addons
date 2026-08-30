# Changelog

## 0.0.37 (2026-08-30)
- Add optional `ovos_workshop_version` setting to opt into a newer `ovos-workshop` for every skill's own venv -- see DOCS.md's "Opting into a newer ovos-workshop" for why (OpenVoiceOS/ovos-workshop#559, fixed only in an alpha release, this stays on stable by default).

## 0.3.3 (2026-08-05)
- Remove skill-ovos-news from usable catalog entries -- confirmed genuinely non-functional in this architecture, same category as ovos-skill-volume/-naptime but a different missing dependency.

## 0.3.2 (2026-08-05)
- Remove skill-ovos-stop from the default set -- confirmed genuinely broken, not a git-vs-PyPI issue.

## 0.3.1 (2026-08-05)
- Fix default-skill seeding installing a broken git/dev-branch version of skill-ovos-stop instead of its correct, working PyPI release.

## 0.3.0 (2026-08-05)
- Split skill installation into two add-ons: OVOS Skills (curated, verified) and a new OVOS Skills Extra (free-form PyPI-name-or-git-URL, unverified).

## 0.2.1 (2026-08-05)
- Prefer a real, published PyPI package over the official skills catalog's git-URL-only source, when one exists under the repo's own name.

## 0.2.0 (2026-08-05)
- Remove all temporary debug endpoints -- investigation resolved: the 'OVOS-SESSION-1' log lines are genuine, legitimate output from ovos_spec_tools/session.py, a well-documented reference implementation of a formal OVOS session-context specification. The unusual log format (no timestamp/logger name) is just an unconfigured logger falling back to Python's own last-resort stderr handler, not anything injected. The line itself: a _log.warning() firing whenever a bus message sets a registered session field (e.g. persona_id) explicitly to null instead of omitting it -- confirmed by reading the full module source. Real, if noisy, validation output -- not a security concern. The actual follow-up (separate from this cleanup) is finding what's sending persona_id: null explicitly, most likely our own ovos-persona integration code from an earlier session.

## 0.1.9 (2026-08-05)
- add /debug/read-file to inspect ovos_spec_tools/session.py directly, the confirmed source of the suspicious log string.

## 0.1.8 (2026-08-05)
- make grep-source async (start + poll) -- a full grep across every skill's venv exceeded typical client request timeouts.

## 0.1.7 (2026-08-05)
- fix grep-source for Alpine's BusyBox grep, which doesn't support --include.

## 0.1.6 (2026-08-05)
- add /debug/grep-source to search every skill's own venv for a suspicious log string ('OVOS-SESSION-1 section reference') appearing live in both ovos-core's and ovos-skills' logs, interleaved with real event-registration lines -- not found in ovos-core's own site-packages, checking each skill's isolated venv next.

## 0.1.5 (2026-08-05)
- Remove temporary /debug/wipe-manifest endpoint -- venv-per-skill architecture confirmed working end-to-end: all four previously-installed skills (alerts, date-time, dictation, news) reinstalled cleanly and running via fresh venvs, both the install-time path (_install_skill_into_venv, now with reliable shebang rewriting) and the container-restart rebuild path (_rebuild_all_venvs_from_manifest, never had the move-related bug since it never moves anything) confirmed working.

## 0.1.4 (2026-08-05)
- Replace the venv-move shebang fix with a reliable one: re-running virtualenv against the moved venv's new path only repairs virtualenv's OWN core files (pip, activate, the python symlink) -- confirmed for real, ovos-skill-alerts happened to work but ovos-skill-date-time failed with the exact same FileNotFoundError right after, meaning the previous fix wasn't actually reliable, just inconsistently lucky.

## 0.1.3 (2026-08-05)
- add /debug/wipe-manifest to clear a stale manifest+venv left from the pre-repair-fix failed install.

## 0.1.2 (2026-08-05)
- Fix skill launch failing with FileNotFoundError right after a fresh install: a venv's own internal scripts (e.g. ovos-skill-launcher) have hardcoded, absolute shebang lines pointing at the venv's path at creation time -- confirmed for real, moving the just-created temp venv to its final skill_id-keyed directory left those shebangs pointing at the now-gone temp path. Re-running virtualenv against the venv's new, final path after the move repairs this in place (idempotent on an existing venv).

## 0.1.1 (2026-08-05)
- Fix skill installs: a bare GitHub repo URL (the catalog's own 'source' convention) needs the git+ scheme prefix for pip to clone it as a VCS source -- confirmed for real, pip otherwise tries to download the URL directly as an archive and gets GitHub's HTML page back ('Cannot determine archive format'). New _pip_installable() adds the prefix when needed, leaves already-prefixed/archive/plain-package sources alone.

## 0.1.0 (2026-08-05)
- Rebuild ovos-skills around one isolated Python venv per skill.

## 0.0.40 (2026-08-05)
- test _pip_show_files() directly.

## 0.0.39 (2026-08-05)
- Remove temporary debug endpoints -- persisted-packages dir wiped, clean-slate add-on reset ahead.

## 0.0.38 (2026-08-05)
- debug endpoint to verify _pip_show_files/_discover work correctly for a freshly-installed package

## 0.0.37 (2026-08-05)
- Fix the deeper cause behind skills going undiscovered after install: replace ALL remaining importlib.metadata usage in this long-running process with fresh subprocess calls (pip list / pip show -f / a fresh python -c for entry_points), matching the pattern _find_installed_package already used reliably.

## 0.0.36 (2026-08-05)
- re-add debug endpoint to check whether wolfie survives a restart (persistence check) and is found via entry_points afterward.
- read skill.json for a nicer display name

## 0.0.35 (2026-08-05)
- Remove the temporary debug endpoints -- investigation concluded: entry_points discovery was never the issue. wolfie was genuinely gone from disk, lost during one of this session's own repeated add-on restarts (deploying the debug endpoints themselves) before it had a chance to be persisted to /share -- an artifact of the investigation process, not a bug in the hot-launch fix itself.
- add enable/disable per skill via skillmanager.activate/deactivate

## 0.0.34 (2026-08-05)
- expand debug endpoint to search filesystem + persist dir, not just importlib.metadata
- switch default intent matcher to padatious, matching upstream

## 0.0.33 (2026-08-05)
- add /debug/entry-points endpoint to investigate why wolfie isn't discovered via entry_points -- will be removed once diagnosed.
- add per-skill extra_deps, fix wikipedia's missing translator

## 0.0.32 (2026-08-05)
- Fix hot-launch (and package persistence) being skipped whenever an install job's own reported bus status is 'failed', even when the install genuinely succeeded.
- add ovos-rake-keyword-extractor to BASELINE_PACKAGES

## 0.0.31 (2026-08-04)
- Remove temporary /debug/is-ready endpoint now that the mystery is solved: it wasn't a bug, it was ovos_workshop's own deliberate exponential-backoff retry (1s to 60s cap) before a launched skill process will load, to avoid hammering a still-starting core. Confirmed ovos-core was already answering ready:true immediately; the skill processes just hadn't hit their next retry yet. Waited it out, no code change needed. Documented the full automatic-startup proof in DEVELOPER.md: four previously-installed skills discovered and launched with zero manual intervention on a fresh ovos-skills restart, /ask answering correctly once the retry window passed.
- Fix skill-ovos-stop crash-loop + document /ask 504 blind spot for action-only intents

## 0.0.30 (2026-08-04)
- Add temporary /debug/is-ready: test directly whether ovos-core's own skill-manager replies to mycroft.skills.is_ready over the shared bus, since every launched skill process is stuck waiting for it.
- sync ovos-core DOCS.md with 0.0.19 intent_matcher option; remove dead allow_pip option from ovos-skills (0.0.30)

## 0.0.29 (2026-08-04)
- skill processes' own stdout/stderr were being captured into a subprocess.PIPE that nothing ever reads, silently swallowing their log output (and any startup errors) unless the process had already died. Now inherits this add-on's own stdout/stderr instead, so each skill's own logging shows up in the normal HA add-on log.
- reduce mycroft.ready broadcast to a single shot -- testing whether repeated reload() calls were corrupting padacioso's own intent registration state, since /ask still timed out even after skills reported themselves ready with the repeated-broadcast version.

## 0.0.28 (2026-08-04)
- Build the real SkillProcessManager: launches and supervises one ovos-skill-launcher <skill_id> subprocess per installed skill, discovered via entry_points (not pip-name guessing), with a restart-with-limit monitor loop and hot-launch on install / stop-on-uninstall wired into the existing job flows. Permanent replacement for the manual /debug/launch-skill endpoint used to first prove the mechanism -- see DEVELOPER.md's 'Skill runtime' section for that proof. New GET /skills/running exposes live status (running/dead, pid, restart count) per skill_id.
- Repeat the mycroft.ready broadcast several times, not once -- a single shot only reached whichever skill happened to connect first (1 of 9 loaded on real hardware), the rest were still mid-connect and missed it, the same race narrowed rather than fixed. Now repeats over ~60s to catch stragglers on slower hardware, harmless no-op for anything already loaded.

## 0.0.27 (2026-08-04)
- Add temporary /debug/launch-skill: run ovos-skill-launcher for an already-installed skill package right here in ovos-skills' own container, connected to the shared bus. The real test of the 'skill runtime lives in its own container' architecture -- if ovos-core's /ask can answer using a skill that's never been in its own site-packages, the whole approach is proven.
- Fix skills getting stuck in 'Skills service not ready yet' -- both add-ons now self-broadcast mycroft.ready after every launch.

## 0.0.26 (2026-08-04)
- Stop starting ovos-skills' own private ovos-messagebus -- caused OSError: [Errno 99] Address not available once the shared mycroft.conf's websocket.host pointed at ovos-core's hostname (a bind address that isn't valid inside ovos-skills' own container). Now waits for the SHARED bus hosted by ovos-core to accept connections instead; ovos-skill-installer and api.py both already read websocket.host from the shared Configuration(), no code change needed there, just no longer racing our own local bus for the same config key.
- Add upstream PR reference to BASELINE_PACKAGES' pkg_resources comment -- filed OpenVoiceOS/ovos-plugin-manager#426 proposing the actual root-cause fix (stdlib importlib.metadata instead of the importlib_metadata+pkg_resources fallback). Our setuptools pin stays either way, as a safety net for any already-published release.

## 0.0.25 (2026-08-04)
- Add temporary /debug/shared-bus-test to ovos-skills: the first real cross-container test of whether ovos-core binding to its own hostname (b8e040e3-ovos-core) instead of 0.0.0.0 is actually reachable from a genuinely separate container, not just within ovos-core's own container as /health already confirmed.
- Externalize the curated catalog into catalog.json, and add 13 newly-verified skills.

## 0.0.24 (2026-08-04)
- Bump version for the truly final uninstall-survives-rebuild test, with PERSIST_DIR removal now fixed too
- Pin setuptools<=80.9.0 in BASELINE_PACKAGES -- unpinned still failed with the exact same pkg_resources error.

## 0.0.23 (2026-08-04)
- Fix the actual reappear-after-rebuild bug: _remove_persisted_package still used the unreliable importlib.metadata.files() to find what to delete from PERSIST_DIR, even after fixing the same issue in _find_installed_package. Consolidated both site-packages and PERSIST_DIR removal into one shared, dist-info-scanning function, verified in a sandbox against both directory structures before deploying.
- Add setuptools to BASELINE_PACKAGES -- third, same-class failure confirmed: ovos_plugin_manager's own code does 'import pkg_resources' internally, which newer setuptools no longer bundles by default in a fresh venv. Confirmed by skill-ovos-fallback-chatgpt crashing with ModuleNotFoundError: pkg_resources, 40+ restart attempts, even with the previous ovos-workshop/ovos-plugin-manager baseline already in place.

## 0.0.22 (2026-08-04)
- Bump version to force rebuild for the final, decisive uninstall-survives-rebuild test
- Re-enable skill-ovos-stop in the curated catalog, as a default skill again -- confirmed fixed and working on real hardware after the ovos-workshop/ovos-plugin-manager baseline install (see previous commit). Closes #1.

## 0.0.21 (2026-08-04)
- Add manual dist-info-based removal as fallback when pip uninstall fails with 'no RECORD file was found' — confirmed for real that our persist/restore cycle doesn't reliably keep a package's RECORD file intact. Verified the manual removal logic in a clean sandbox against a package with a deliberately emptied RECORD file, including catching and fixing a normalization bug (dist-info dirs use PEP 503 underscored names with a hyphen only as the version separator, not consistently one or the other) before trusting it. Removed debug logging now that the full picture is understood.
- Pre-install ovos-workshop + ovos-plugin-manager as a baseline in every fresh venv, before the skill's own package.

## 0.0.20 (2026-08-04)
- Fix _find_installed_package for real: switch from importlib.metadata.distributions() (confirmed unreliable inside this long-running process even after invalidate_caches()+reload() both, via explicit logging: 85 packages seen, target skill absent) to a fresh 'pip list' subprocess, matching the already-proven-reliable approach the /skills endpoint uses.
- Bring versions back under 0.1.0 across the board -- ovos-persona, ovos-skills, ovos-skills-extra. All add-ons stay in the 0.0.x range deliberately until the maintainer decides this is ready for others to see.

## 0.0.19 (2026-08-04)
- Add importlib.invalidate_caches() alongside reload(): confirmed via logging that the skill was completely absent from distributions() (85 packages, not among them) even after reload() alone. site-packages has been scanned repeatedly since process start, unlike a freshly sys.path-inserted dir in earlier isolated testing — its FileFinder cache needs explicit invalidation.

## 0.0.18 (2026-08-04)
- Round 5 debugging: log the actual names list _find_installed_package sees, to find why the reload fix still isn't resolving the exact match

## 0.0.17 (2026-08-04)
- Round 4 debugging: the reload fix resolved package_name lookup but the skill still reappears after uninstall reports complete. Adding trace back to find what's actually happening at the pip subprocess level now.

## 0.0.16 (2026-08-04)
- Fix root cause found via explicit tracing: _find_installed_package never reloaded importlib.metadata, so it couldn't see packages restored via run.sh's file-copy (as opposed to a real pip install run inside this process) — same staleness _persist_new_packages already reloads to avoid. This silently made uninstall fall back to a guessed, nonexistent package name, reporting success ('Skipping ... as it is not installed') while removing nothing. Removed debug logging/endpoint added while diagnosing.

## 0.0.15 (2026-08-04)
- Round 3 debugging: explicit LOG.warning tracing through the entire uninstall path (package_name resolved, files found/removed in PERSIST_DIR, full pip subprocess output) to find the real cause without guessing from ambiguous log fragments

## 0.0.14 (2026-08-04)
- Round 2 diagnostics: skill reappeared after a fully controlled uninstall+rebuild test with no possible interference, so round 1's conclusion was wrong. Investigating properly this time.

## 0.0.13 (2026-08-04)
- Bump version to force rebuild for the final, controlled uninstall-survives-rebuild test

## 0.0.12 (2026-08-04)
- Remove temporary debug endpoint: confirmed no bug. The skill's own files were correctly removed from PERSIST_DIR by _remove_persisted_package (verified via the endpoint) — the reappearance after rebuild was a real, independent reinstall via the subentry UI, confirmed by the person, not a persistence bug.

## 0.0.11 (2026-08-04)
- Add temporary /debug/persist-dir endpoint to investigate a skill reappearing after uninstall+rebuild despite _remove_persisted_package running correctly

## 0.0.10 (2026-08-04)
- Bump version to force a rebuild for the uninstall-persists-across-rebuild test

## 0.0.9 (2026-08-04)
- Add local uninstall bridge, bypassing SkillsStore's currently-stubbed one. Runs pip uninstall directly with a protected-package list mirroring SkillsStore's own hardcoded fallback (checked independently of our own empty constraints file, which would otherwise silently disable protection). Fixed a real bug found via testing: a bare 'pip' resolved to the wrong interpreter and reported false success; switched to sys.executable -m pip everywhere, matching SkillsStore's own approach. Deliberately documented as a temporary bridge, not the destination — revisit once a PyPI release resolves the ovos-messagebus version conflict blocking SkillsStore's real uninstall.

## 0.0.8 (2026-08-04)
- Bump version to force a real rebuild for the persist-across-rebuild test

## 0.0.7 (2026-08-04)
- Skills now survive an add-on rebuild: copy newly-installed package files to /share after each install, restore on every container start. PIP_TARGET/PYTHONPATH tried and rejected after directly testing it — broke pip's build isolation AND importlib.metadata detection, confirmed in a clean venv before writing any real code.

## 0.0.6 (2026-08-04)
- Add settingsmeta/settings endpoints. Confirmed for real (not guessed): settingsmeta.json is inconsistent across skills (date-time has it, fallback-chatgpt doesn't), and the catalog's package_name doesn't always match what pip actually installs it as (skill-ovos-fallback-chatgpt vs catalog's ovos-skill-ovos-fallback-chatgpt) — handled with a normalized fuzzy match against actually-installed packages, verified against that exact real mismatch.

## 0.0.5 (2026-08-04)
- Revert to PyPI ovos-core: git@dev broke the build (incompatible with ovos-messagebus, whose own dev branch doesn't match either — two independently drifting branches). Install stays fully working; uninstall documented as a known upstream stub, not chased further tonight.

## 0.0.4 (2026-08-04)
- Fix real bug: uninstall was a stub on PyPI's ovos-core (2.1.1). Install from git@dev instead, confirmed to have a real implementation. Also document that skills don't survive add-on rebuilds (real gap, not yet fixed) and confirm the list heuristic works against a real install.

## 0.0.3 (2026-08-04)
- Fix real bug: pip list doesn't accept --break-system-packages (that flag is install/uninstall only). Confirmed on hardware: install actually works end-to-end now (skill-ovos-date-time installed successfully, 17 packages) — this bug was only in the list heuristic, not the install path.

## 0.0.2 (2026-08-04)
- Actually bump version this time — previous sed pattern didn't match YAML syntax

## 0.0.1 (2026-08-04)
- Consolidate haos-ovos-skills into this repo as a fifth add-on (ovos-skills), matching the existing multi-add-on pattern. Reconsidered: the repo already handles heterogeneous add-ons (persona needed a dev-branch git install + build-time patch, wyoming bridges didn't) with fully independent per-add-on versioning — the earlier argument for a separate repo didn't actually hold up. Only ha-ovos-integration stays separate, since HACS integration vs Supervisor add-on is a genuinely different distribution mechanism.

