# Changelog

## 0.0.9 (2026-08-30)
- Add optional `ovos_workshop_version` setting -- same mechanism and reasoning as OVOS Skills' own DOCS.md entry (OpenVoiceOS/ovos-workshop#559).

## 0.0.8 (2026-08-30)
- read skill.json for a nicer display name

## 0.0.7 (2026-08-06)
- reduce mycroft.ready broadcast to a single shot -- testing whether repeated reload() calls were corrupting padacioso's own intent registration state, since /ask still timed out even after skills reported themselves ready with the repeated-broadcast version.
- sync ovos-core DOCS.md with 0.0.19 intent_matcher option; remove dead allow_pip option from ovos-skills (0.0.30)
- Fix skill-ovos-stop crash-loop + document /ask 504 blind spot for action-only intents
- add ovos-rake-keyword-extractor to BASELINE_PACKAGES
- add per-skill extra_deps, fix wikipedia's missing translator
- switch default intent matcher to padatious, matching upstream
- add enable/disable per skill via skillmanager.activate/deactivate

## 0.0.6 (2026-08-06)
- Repeat the mycroft.ready broadcast several times, not once -- a single shot only reached whichever skill happened to connect first (1 of 9 loaded on real hardware), the rest were still mid-connect and missed it, the same race narrowed rather than fixed. Now repeats over ~60s to catch stragglers on slower hardware, harmless no-op for anything already loaded.

## 0.0.5 (2026-08-06)
- Fix skills getting stuck in 'Skills service not ready yet' -- both add-ons now self-broadcast mycroft.ready after every launch.

## 0.0.4 (2026-08-05)
- Pin setuptools<=80.9.0 in BASELINE_PACKAGES -- unpinned still failed with the exact same pkg_resources error.
- Externalize the curated catalog into catalog.json, and add 13 newly-verified skills.
- Add upstream PR reference to BASELINE_PACKAGES' pkg_resources comment -- filed OpenVoiceOS/ovos-plugin-manager#426 proposing the actual root-cause fix (stdlib importlib.metadata instead of the importlib_metadata+pkg_resources fallback). Our setuptools pin stays either way, as a safety net for any already-published release.

## 0.0.3 (2026-08-05)
- Add setuptools to BASELINE_PACKAGES -- third, same-class failure confirmed: ovos_plugin_manager's own code does 'import pkg_resources' internally, which newer setuptools no longer bundles by default in a fresh venv. Confirmed by skill-ovos-fallback-chatgpt crashing with ModuleNotFoundError: pkg_resources, 40+ restart attempts, even with the previous ovos-workshop/ovos-plugin-manager baseline already in place.

## 0.0.2 (2026-08-05)
- Pre-install ovos-workshop + ovos-plugin-manager as a baseline in every fresh venv, before the skill's own package.
- Re-enable skill-ovos-stop in the curated catalog, as a default skill again -- confirmed fixed and working on real hardware after the ovos-workshop/ovos-plugin-manager baseline install (see previous commit). Closes #1.

## 0.0.1 (2026-08-05)
- Bring versions back under 0.1.0 across the board -- ovos-persona, ovos-skills, ovos-skills-extra. All add-ons stay in the 0.0.x range deliberately until the maintainer decides this is ready for others to see.

## 0.1.0 (2026-08-05)
- Split skill installation into two add-ons: OVOS Skills (curated, verified) and a new OVOS Skills Extra (free-form PyPI-name-or-git-URL, unverified).
- Fix default-skill seeding installing a broken git/dev-branch version of skill-ovos-stop instead of its correct, working PyPI release.
- Remove skill-ovos-stop from the default set -- confirmed genuinely broken, not a git-vs-PyPI issue.
- Remove skill-ovos-news from usable catalog entries -- confirmed genuinely non-functional in this architecture, same category as ovos-skill-volume/-naptime but a different missing dependency.

