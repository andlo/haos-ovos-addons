# Changelog

## 0.0.9 (2026-08-05)
- Bump versions for ovos-core and the three Wyoming add-ons -- their run.sh got the shared pip-cache change earlier this session but the version number was never bumped, so Supervisor never offered an update and the running containers were still on the old code.

## 0.0.8 (2026-08-04)
- Phase 2 of the mycroft.conf-as-master design: reverse which side wins for TTS/STT/wakeword plugin config.

## 0.0.7 (2026-08-04)
- Write shared mycroft.conf to /share instead of container-private config (merge, not overwrite)

## 0.0.6 (2026-08-03)
- Fix noisy BrokenPipeError in logs: probe the port with a bare TCP connect instead of writing a malformed Wyoming event

## 0.0.5 (2026-08-03)
- Add bashio::discovery call so the wyoming service actually registers with HA Core (config.yaml discovery: field alone was not enough)

## 0.0.4 (2026-08-03)
- Add discovery: wyoming to config.yaml so Supervisor registers the Wyoming integration with HA Core (matches openWakeWord/Piper/Whisper)

## 0.0.3 (2026-08-03)
- Fix actual root cause: patch missing version= in wyoming-ovos-tts's TtsVoice call; revert wrong wyoming pin (STT/wakeword were never broken)

## 0.0.2 (2026-08-03)
- Bump ovos-wyoming-tts to 0.0.2 to force Supervisor to re-fetch the wyoming pin fix

## 0.0.1 (2026-08-03)
- Add DOCS.md per add-on; pin versions to 0.0.1 until verified working

## 0.1.0 (2026-08-03)
- Scaffold four add-ons: wyoming-tts, wyoming-stt, wyoming-wakeword, persona

