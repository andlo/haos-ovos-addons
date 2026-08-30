# Changelog

## 0.0.8 (2026-08-29)
- prefer Supervisor's own network info over HA's internal_url

## 0.0.7 (2026-08-29)
- auto-detect web_public_url from Home Assistant's own internal_url

## 0.0.6 (2026-08-29)
- use ovos-tui-client's new --web-public-url properly

## 0.0.5 (2026-08-29)
- fix bashio::config returning literal 'null' for empty web_host

## 0.0.4 (2026-08-29)
- wait for own hostname to resolve before binding

## 0.0.3 (2026-08-29)
- fix web_host to not crash, default to mDNS hostname

## 0.0.2 (2026-08-29)
- write shared real log files; ovos-tui: read them

## 0.0.1 (2026-08-29)
- New add-on: ovos-tui (0.0.1) -- andlo/ovos-tui-client in --web mode

