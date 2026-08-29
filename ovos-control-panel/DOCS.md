# OVOS Control Panel

A thin Supervisor wrapper around [OpenVoiceOS/ovos-control-panel](https://github.com/OpenVoiceOS/ovos-control-panel), used entirely unmodified -- the official, unified OVOS web UI: Dashboard, Settings, Skills, Plugins, Personas, Translate, and Backup.

## Why this exists alongside `ha-ovos-integration`

`ha-ovos-integration` deliberately exposes the common cases as native Home Assistant entities (skill settings, persona, voice). This add-on is the escape hatch for everything else -- the full official admin surface, without reimplementing it. Not a replacement for the integration; a companion to it, same relationship `ovos-busmon` has to bus debugging.

## Setup

1. Install and start the other `haos-ovos-addons` add-ons first (this one edits their shared `mycroft.conf` and skill settings, and reads the shared bus for the Dashboard).
2. **Change the `token` option** in this add-on's Configuration tab -- required since this add-on binds beyond `127.0.0.1` (upstream's own default), and there's no separate username, just this one token.
3. Start this add-on (`boot: manual` -- same reasoning as `ovos-busmon`/`ovos-tui`: this tool changes the actual configuration of every OVOS service on this stack, not something to leave running unattended).
4. Open `http://<hostname>:8510/` in a browser.

## Configuration

| Option | Description |
|---|---|
| `token` | Access token -- **change this from the default** before relying on it. |

## What's confirmed to work well in this multi-container setup

- **Dashboard** -- reads the shared bus, same one every other add-on connects to.
- **Settings** -- edits the SAME shared `mycroft.conf` every other add-on reads from (`/share/mycroft/mycroft.conf`), not a private copy.
- **Skills** -- edits `settings.json` files under the shared `/share/mycroft/skills/` directory, the same files the actual running skill processes (in `ovos-skills`/`ovos-skills-extra`) read from.
- **Backup/Restore** -- writes its own `.ovos-webui-backups` directory beside the files it backs up, on the same shared `/share` volume.

## Known limitation: Plugins page likely doesn't do anything useful here

Not tested end-to-end (flagging honestly rather than asserting either way). The Plugins page's own job is finding and **installing** OVOS plugins -- if that means `pip install` inside *this add-on's own container*, it would have no effect on the actual OVOS services, which each run in their own separate containers (`ovos-core`, `ovos-skills`, `ovos-persona`, ...) with their own separate Python environments. A plugin installed here wouldn't be importable by anything that would actually use it. If this turns out to matter to you, verify directly before relying on it -- worth revisiting if it becomes a real blocker.

## Security

Same shape as `ovos-busmon`: binds `0.0.0.0` rather than upstream's own `127.0.0.1`-only default, so the token above is the only thing standing between anyone on your LAN and the ability to reconfigure every OVOS service on this stack. Upstream's own README: "The page changes the configuration of your device, so treat it like a key." No TLS -- credentials go over plain HTTP on your LAN.

## Relationship to the other add-ons

Reads/writes the same shared `mycroft.conf` and skill settings every other add-on in this repo uses, and reads the same shared bus `ovos-core` hosts (`b8e040e3-ovos-core:8181`) for its Dashboard.

## Port

Mapped to host port `8510`, not upstream's own default `8500` -- `ovos-core`'s own add-on already uses `8500` for its synchronous Q&A API, and two add-ons can't publish the same host port.
