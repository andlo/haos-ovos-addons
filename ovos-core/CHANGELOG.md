# Changelog

## 0.0.25 (2026-08-30)
- GET /config reads the joined effective config, not just the raw file

## 0.0.24 (2026-08-30)
- generic GET/PUT /config alongside /autoconfigure

## 0.0.23 (2026-08-29)
- detect and signal multi-turn dialogs via expect_response

## 0.0.22 (2026-08-29)
- write shared real log files; ovos-tui: read them

## 0.0.21 (2026-08-29)
- switch default intent matcher to padatious, matching upstream

## 0.0.19 (2026-08-07)
- Add user-configurable intent_matcher option: padacioso vs padatious. Exposes this session's investigation as a real, live choice instead of a hardcoded decision -- different hosts have different memory headroom, so the right answer genuinely varies per installation. Explanatory text in the option's own description covers the real tradeoff (padacioso: safe on shared/constrained hosts, slows down as skill count grows; padatious: OVOS's official default, more capable, but memory-heavy enough to segfault under real memory pressure -- confirmed this session, not assumed). Controls the actual pip install/uninstall in run.sh, not just which pipeline keys are active -- padatious is instantiated and trained unconditionally whenever merely importable (confirmed by reading IntentService.__init__ directly), so picking padacioso without actually uninstalling padatious wouldn't avoid its memory cost at all. Dockerfile's build-time uninstall is now just the baked-in default; switching to padatious installs it fresh at runtime (build tools are still present in the image for this, confirmed -- no rebuild needed to switch).

## 0.0.18 (2026-08-07)
- Revert to padacioso with a real, confirmed root cause -- padatious reproducibly segfaulted on this host under genuine memory pressure (free -h: 344MB free, swap 92% full; dmesg: a real OOM-kill already in progress). Confirmed AVX2 is present on this CPU directly, ruling out the instruction-set theory. Not the same claim as the project's original 'padatious is just slow' conclusion -- the real difference from raspOVOS/Mark2 hardware is this host running ~30 other add-on containers simultaneously, not raw CPU strength. padacioso is memory-light enough to survive that pressure; padatious's numpy/scipy/sklearn/fann2 stack isn't. Documented, not assumed, this time.

## 0.0.17 (2026-08-07)
- Reopen padatious vs padacioso: reinstall padatious, switch to OVOS's own official default pipeline order -- deliberate, not a revert. raspOVOS ships padatious as default on RPi3B+/4 (2GB RAM), including the real Mycroft Mark2 hardware (an RPi4 inside) -- all weaker than this NUC. If official OVOS runs fine on weaker hardware with padatious, this project's original 80-90s conclusion is suspect: likely a one-time TRAINING cost measured and mistaken for per-query MATCHING cost. Separately, padacioso itself was measured this session scaling badly with skill count -- the wrong direction for a 20-skill catalog. Testing padatious's real matching speed here, after training completes, to settle this with a real measurement instead of either assumption.

## 0.0.16 (2026-08-07)
- Uninstall ovos-padatious entirely, bump ASK_TIMEOUT to 35s -- confirmed on real hardware: padacioso match times varied 8s-22+s depending on whether padatious's own background training happened to be running concurrently (real CPU contention, confirmed via docker stats, plus real 'dictionary changed size during iteration' training-race errors in the logs) -- from a package we never wanted matching anything, since padacioso is the deliberately-chosen active matcher. ovos-core's own IntentService already handles its absence gracefully via a plain try/except ImportError (confirmed by reading __init__.py directly), so uninstalling is the supported way to opt out, not a workaround. ASK_TIMEOUT bumped too, as real headroom rather than assuming this fully eliminates the variance.

## 0.0.15 (2026-08-07)
- Fix /ask listening for the wrong bus message -- confirmed on real hardware, the final piece: docker stats showed genuine ~380% CPU work for ~10s during a call (padacioso actually matching, not hanging), yet /ask still timed out. Root cause confirmed by reading ovos_workshop/skills/ovos.py's speak() directly inside the running container: this stable-channel ovos-workshop (3.4.0) emits the classic 'speak' message via message.forward('speak', data), not 'ovos.utterance.speak'/SpecMessage.SPEAK, which belongs to a much newer ovos-workshop than stable's coordinated version set installs. api.py was listening for a message nothing in this version ever sends.

## 0.0.14 (2026-08-07)
- Set intents.disable_padacioso: false in mycroft.conf -- confirmed on real hardware by reading IntentService.__init__ directly: it defaults disable_padacioso to True whenever padatious is installed ('to save memory', per its own comment), which it is here. padacioso_high/medium/low were therefore never actually constructed, so they were rejected as invalid right alongside the earlier wrong plugin-id names -- same symptom, different cause. The fix is the exact one named in the module's own LOG.debug hint.

## 0.0.13 (2026-08-07)
- Fix intents.pipeline to use ovos-core 1.3.1's actual matcher keys -- confirmed on real hardware by reading the installed ovos_core/intent_services/__init__.py directly inside the running container. This stable-channel version predates the long ovos-*-pipeline-plugin-* naming entirely; its get_pipeline() has a hardcoded matchers dict keyed by short legacy names built from unconditional imports, not plugin ids. Every entry in the previous list was being silently rejected as an invalid pipeline component, so nothing ever matched and every /ask call hit the 20s timeout. m2v is dropped (no equivalent exists in this version). padacioso still replaces padatious at every confidence tier for the same performance reason as before -- confirmed unconditionally available here (plain import, not an optional plugin).

## 0.0.12 (2026-08-07)
- Fix log_level option being a silent no-op -- confirmed by reading ovos_utils/log.py directly: it's OVOS_DEFAULT_LOG_LEVEL the logger actually reads, not anything this script previously set. The option was declared and shown in the UI the whole time but never had any effect. Needed right now to see the debug-level 'Installed pipeline plugins' log line while diagnosing why every configured intents.pipeline entry is being rejected as invalid after the stable-channel switch.

## 0.0.11 (2026-08-06)
- Pin setuptools<=80.9.0 in ovos-core's own Dockerfile too -- same fix already applied in ovos-skills/ovos-skills-extra. Root cause confirmed on real hardware after the stable-channel switch: ovos-core crashed at startup with ModuleNotFoundError: No module named 'pkg_resources', because stable's coordinated version set resolves a newer setuptools (>=81, which removed pkg_resources) than ovos-plugin-manager's stable-channel release still needs (it still has the old pkg_resources import fallback; our upstream PR #426 fixes this but isn't released to stable yet). Alpha's version set happened to resolve an older setuptools, which is why this was never hit before switching channels.

## 0.0.10 (2026-08-06)
- Revert version scheme back to 0.0.x -- staying on 0.0.x deliberately while pre-1.0, per house rule: patch numbers only until we're ready to actually mean it when a minor bump signals a real feature/behavior change vs a patch. The previous commit's channel switch (alpha -> stable) itself is correct and unchanged, just the version number.

## 0.1.4 (2026-08-04)
- Revert Dockerfile back to Alpine base image, now that the real fix is understood (padacioso, not the OS). Debian never fixed the actual hang -- keeping it would have made ovos-core the only one of six add-ons off Alpine for no remaining reason. run.sh needs no changes; padacioso config is OS-independent.

## 0.1.3 (2026-08-04)
- Switch intents.pipeline to use padacioso instead of padatious -- the real fix for 'The slow NUC'.

## 0.1.2 (2026-08-04)
- It wasn't hanging -- it was just slow. Confirmed: exactly 90s between 'Parsing utterance' and the padatious match log line on this real NUC hardware, vs near-instant on both the sandbox and the known-good VM. Raised ASK_TIMEOUT from 20s to 150s to actually accommodate this hardware's real performance instead of assuming a bug.

## 0.1.1 (2026-08-04)
- Widen /debug/ask-verbose to 180s: network hypothesis ruled out (DNS resolves fast, fails fast), testing whether this is genuinely just slow (weak NUC hardware, CPU-heavy padatious matching) rather than truly hung

## 0.1.0 (2026-08-04)
- Add /debug/network: test whether DNS resolution or outbound connectivity hangs from inside this container -- Debian base image did NOT fix the hang, so testing the network hypothesis directly instead of assuming it was ruled out by the earlier daemon-thread finding
- Switch ovos-core from alpha to stable release channel.

## 0.0.9 (2026-08-04)
- Switch ovos-core to a Debian base image (ghcr.io/home-assistant/${BUILD_ARCH}-base-debian:latest) instead of Alpine -- fixes a real, reproduced bug found via deep investigation.
- Bump versions for ovos-core and the three Wyoming add-ons -- their run.sh got the shared pip-cache change earlier this session but the version number was never bumped, so Supervisor never offered an update and the running containers were still on the old code.

## 0.0.8 (2026-08-04)
- Test hypothesis: blacklist ovos-common-query-pipeline-plugin and ovos-persona-pipeline-plugin -- /ask hangs indefinitely (no response even after 70+s) on real hardware despite an identical ovos-core version working fine in the sandbox, suspect one of these network-dependent matchers is blocking forever on something unreachable from this container that was reachable from the sandbox
- Re-enable ovos-common-query-pipeline-plugin -- the original blacklist reasoning ('needs external services') turned out to be wrong.

## 0.0.7 (2026-08-04)
- Widen /debug/ask-verbose window to 60s: versions are identical to the sandbox spike, so testing whether a pipeline matcher (common-query, persona-pipeline) is genuinely hanging on a slow/failed network call rather than the response simply never coming
- Remove all temporary debug endpoints -- investigation resolved: the 'OVOS-SESSION-1' log lines are genuine, legitimate output from ovos_spec_tools/session.py, a well-documented reference implementation of a formal OVOS session-context specification. The unusual log format (no timestamp/logger name) is just an unconfigured logger falling back to Python's own last-resort stderr handler, not anything injected. The line itself: a _log.warning() firing whenever a bus message sets a registered session field (e.g. persona_id) explicitly to null instead of omitting it -- confirmed by reading the full module source. Real, if noisy, validation output -- not a security concern. The actual follow-up (separate from this cleanup) is finding what's sending persona_id: null explicitly, most likely our own ovos-persona integration code from an earlier session.

## 0.0.6 (2026-08-04)
- Add /debug/versions: send_complete_intent_failure references OVOS-PIPELINE-1 spec messages never seen in the earlier sandbox spike -- checking whether a newer ovos-core got installed on real hardware since constraints-alpha.txt is a live URL fetched hours later at real build time
- narrow /debug/grep-source to .py files only, longer timeout -- the full site-packages tree includes large ML model files that made the previous grep too slow.

## 0.0.5 (2026-08-04)
- Add /debug/processes: our own bus client sees zero response messages despite ovos-core's own log confirming it parsed the utterance -- checking whether a stale duplicate messagebus process from an earlier restart is the culprit
- add /debug/grep-source to investigate a suspicious, non-standard log string ('OVOS-SESSION-1 section reference') appearing in ovos-core's own log, unlike any genuine Python logging output in this stack.

## 0.0.4 (2026-08-04)
- Add /debug/ask-verbose: listen for every raw bus message after emitting the utterance, since resource files and lang were both ruled out. Confirmed the correct raw 'message' JSON keys (type/data/context) by reading Message.serialize() directly rather than guessing.
- Improve /autoconfigure: parse stdout for 'ERROR: X not available for Y' lines (autoconfigure exits 0 even when it found nothing for the requested combination, confirmed by reading its source) and always report the resulting tts_module/stt_module, not just changed_keys. Also documented, with real evidence: OVOS's own official workflow treats plugin selection and plugin installation as two separate steps (ovos-docker's own plugin-install docs, the ovos-installer manual's own advice to run autoconfigure --help after install, and a genuine venv install where the active stt module wasn't even installed) -- and module name to pip package name has no reliable general mapping (ovos-tts-plugin-phoonnx vs the real package phoonnx). So this endpoint doesn't attempt auto-install; it reports what's active so the caller can tell the person and let them add it themselves.

## 0.0.3 (2026-08-04)
- Add /debug/mycroft-conf endpoint: skill resource files ARE present and lang IS correctly en-us, so investigating whether the shared mycroft.conf itself (written to by five other add-ons) has an unexpected setting affecting intent matching that the sandbox spike's clean config never exercised
- Add POST /autoconfigure to ovos-core: runs OVOS's own 'ovos-config autoconfigure' CLI (already a real dependency in this container) against the real, shared mycroft.conf, via subprocess (not importing the click-decorated function directly, so click's own validation stays intact). Reports back every changed key, not just tts/stt, since testing directly confirmed autoconfigure also touches system_unit, lang, and date/time-format keys -- deliberately left for the caller (eventually ha-ovos-integration) to reconcile with fields it manages from HA's own settings, not silently decided here.

## 0.0.2 (2026-08-04)
- Add temporary /debug/skill-files endpoint to confirm whether ovos-skill-date-time's locale/ resource dir made it into the installed package on real Alpine hardware -- real hardware logs 'Unable to find X.intent' and a far smaller m2v prototype count than the sandbox spike had, suggesting resource files may not be packaged/installed correctly in this environment specifically
- Test the shared-bus address hypothesis: bind ovos-messagebus to its own real hostname (b8e040e3-ovos-core) instead of 0.0.0.0. Confirmed by reading ovos-messagebus/ovos-skill-installer/ovos-skill-launcher source: all three read the same shared websocket.host key via Configuration() with no external override, so one value has to work for both bind and connect purposes. 0.0.0.0 works for bind but is meaningless as a connect target for another container -- this is the first real test of whether binding to the own hostname works for both. Also updated run.sh's own readiness check to match (checking the real hostname, not localhost, in case binding to a specific host stops also listening on loopback).

## 0.0.1 (2026-08-04)
- Scaffold ovos-core add-on: config.yaml skeleton plus a thorough DOCS.md writeup of tonight's sandbox spike, which confirmed the full mechanism works end-to-end before any add-on code was written.
- remove all six temporary /debug/* endpoints from api.py (investigation resolved), lower ASK_TIMEOUT from 150s back to a realistic 20s now that padacioso answers in under a second, add ovos-core to the main README's add-on table and status section, and correct config.yaml's version back to 0.0.1.

