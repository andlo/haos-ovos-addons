# Changelog

## 0.0.4 (2026-08-05)
- Bump versions for ovos-core and the three Wyoming add-ons -- their run.sh got the shared pip-cache change earlier this session but the version number was never bumped, so Supervisor never offered an update and the running containers were still on the old code.

## 0.0.3 (2026-08-04)
- Phase 2 of the mycroft.conf-as-master design: reverse which side wins for TTS/STT/wakeword plugin config.

## 0.0.2 (2026-08-04)
- Extend shared /share mycroft.conf convention to stt, wakeword, and persona (merge not overwrite; persona.json stays private but shares XDG_CONFIG_HOME)

## 0.0.1 (2026-08-03)
- Add DOCS.md per add-on; pin versions to 0.0.1 until verified working
- Add discovery: wyoming to config.yaml so Supervisor registers the Wyoming integration with HA Core (matches openWakeWord/Piper/Whisper)

## 0.1.0 (2026-08-03)
- Scaffold four add-ons: wyoming-tts, wyoming-stt, wyoming-wakeword, persona

