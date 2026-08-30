# Changelog

## 0.0.12 (2026-08-05)
- Point skill-ovos-fallback-chatgpt (if installed via ovos-skills-extra) at this persona server, every startup.

## 0.0.11 (2026-08-05)
- Bring versions back under 0.1.0 across the board -- ovos-persona, ovos-skills, ovos-skills-extra. All add-ons stay in the 0.0.x range deliberately until the maintainer decides this is ready for others to see.

## 0.0.10 (2026-08-04)
- Genuine fix, not a guess: pin ovos-persona-server to the exact PR#67 merge commit (not @dev, which regressed within this session), and explicitly disable extra solver plugins that ovos-persona's own unpinned >=0.9.0a6 dependency keeps pulling in (bm25/yes-no/bus/openai-chat), which crash QuestionSolversService.modules's priority-sort since they're not QuestionSolver-shaped. Verified end-to-end in a clean venv with real_chat()'s actual raw-dict call path, not just the lower-level solver service: clean '404' response, no crash. Also noted (not fixed): a real but non-fatal argument-order bug in ovos_persona's own Persona.chat(), confirmed live in this same test (logged 'Expected a language code, got metric').

## 0.0.9 (2026-08-04)
- Remove the run_chat/AgentMessage patch: PR #67 was merged and confirmed present in dev branch directly (verified in a clean venv, not just checking the diff). The patch's own safety assertion would have failed the build the next time it ran, since it checks the fix isn't already applied.

## 0.0.8 (2026-08-04)
- Extend shared /share mycroft.conf convention to stt, wakeword, and persona (merge not overwrite; persona.json stays private but shares XDG_CONFIG_HOME)

## 0.0.7 (2026-08-04)
- Apply build-time patch for the run_chat/run_stream AgentMessage bug (PR #67 pending upstream)

## 0.0.6 (2026-08-03)
- Install ovos-persona-server from git@dev instead of stale PyPI release (missing schemas submodule, under-declared deps)

## 0.0.5 (2026-08-03)
- Add uvicorn: ovos-persona-server's web layer isn't declared as a dependency either

## 0.0.4 (2026-08-03)
- Add ovos-workshop: ovos_persona imports it but ovos-persona-server doesn't declare it as a dependency

## 0.0.3 (2026-08-03)
- Fix schema: list(str)? is not a valid type, use ["str"] for array-of-string options

## 0.0.2 (2026-08-03)
- Fix solver package/entry-point names: ovos-solver-ddg-plugin doesn't exist; correct is package ovos-ddg-solver-plugin registering entry point ovos-solver-plugin-ddg. Drop wikipedia (not persona-server compatible)

## 0.0.1 (2026-08-03)
- Add DOCS.md per add-on; pin versions to 0.0.1 until verified working

## 0.1.0 (2026-08-03)
- Scaffold four add-ons: wyoming-tts, wyoming-stt, wyoming-wakeword, persona
- Add an HTTP bridge (api.py, port 8338) to ovos-persona, matching ovos-core/ovos-skills' pattern -- lets ha-ovos-integration read/edit persona.json's solvers list from HA's own UI.

