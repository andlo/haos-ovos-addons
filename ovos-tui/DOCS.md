# OVOS TUI

A thin Supervisor wrapper around [andlo/ovos-tui-client](https://github.com/andlo/ovos-tui-client) in its `--web` mode -- a split-pane interface (conversation, activity feed, logs, command palette) for testing and debugging OVOS by typing instead of talking, without a mic or speaker.

## What it's for

Type an utterance and see exactly what OVOS does with it: which skill answered (and which ones tried and gave up), fallback behavior, the intent pipeline order, and a live conversation transcript -- all without needing working audio hardware or a wake word. See the upstream README for the full feature list.

## Setup

1. Install and start the other `haos-ovos-addons` add-ons first (this one connects to their shared bus and reads their shared `mycroft.conf`).
2. Start this add-on (`boot: manual` by default, same reasoning as `ovos-busmon` -- a debugging tool, not something to leave running unattended).
3. Open `http://<hostname>:8000/` in a browser -- reachable via the Home Assistant host's own LAN IP just fine for this first load. But the page's own JS and terminal connection load from this add-on's own hostname by default, regardless of how you reached the page itself -- if the terminal never appears and stays on a plain, unstyled page, set `web_public_url` (see "The web_host problem" below).

## Configuration

| Option | Description |
|---|---|
| `web_public_url` | Only needed if the page loads but stays blank/unstyled. See "The web_host problem" below. |

## The web_host problem

`ovos-tui-client`'s own `--web-host` used to be BOTH the address this add-on's web server binds to AND the address baked into every absolute URL its served HTML embeds (static asset `<script>`/`<link>` tags, the WebSocket endpoint the terminal actually connects through). That coupling made it impossible to satisfy both requirements at once behind Docker port-publishing/NAT -- confirmed by testing directly, in order of what was tried:

- `0.0.0.0` -- binds fine, but bakes `http://0.0.0.0:8000/...` into the page, meaningless to a browser.
- No `--web-host` at all (the tool's own auto-detection) -- resolved to Supervisor's own internal Docker network IP (`172.30.x.x`), not reachable from a browser on the actual LAN.
- The Home Assistant host's own real LAN IP -- **crashed the add-on outright**: `OSError: could not bind on any address out of [...]`. A container can only bind an address one of its own network interfaces actually has; the host's real IP isn't one of them without `host_network: true`, which this add-on deliberately doesn't use (a real, broader privilege tradeoff, not taken here).
- This add-on's own Docker hostname -- bound fine and produced valid URLs, but only resolved for a browser via mDNS (`.local.hass.io`), which isn't available on every network/OS -- confirmed this was the actual blocker on at least one real setup.

**Fixed properly upstream in `ovos-tui-client` v0.1.25**, which added `--web-public-url`: a separate flag that overrides only the URLs baked into the page, completely independent of the bind address. This add-on now always binds `0.0.0.0` (works unconditionally) and passes `web_public_url` through to `--web-public-url`.

**Auto-detected by default**, in order:
1. Supervisor's own `/network/interface/default/info` -- the host's real IP on whichever interface actually has the default route (its normal LAN-facing address). Doesn't depend on you having configured anything. Requires this add-on's `hassio_api: true` permission.
2. Home Assistant Core's own `/api/config` `internal_url`, if (1) gave nothing -- exactly "the address to reach this HA instance from the local network", if you've set it. Requires `homeassistant_api: true`.
3. This add-on's own hostname (works wherever mDNS does) -- the final fallback if neither of the above gave anything usable (confirmed on at least one real setup: a dev VM with no `internal_url` configured still got a working address from step 1 alone).

Both permissions are granted on install/rebuild. Check this add-on's own log line ("Auto-detected public URL: ..." vs "Could not auto-detect...") to see what happened on your system. Set `web_public_url` manually only if none of the above gives you a working page.

## Known limitations

- **Logs come from real files on the shared `/share` volume, not Docker-log-bridging.** `ovos-core`'s own `run.sh` sets `logs.path` in the shared `mycroft.conf` to `/share/mycroft/logs` — confirmed by reading `ovos_utils/log.py` directly, every OVOS service (the bus, this add-on's own skill manager, each launched skill, `ovos-persona-server`, ...) writes its real log file there (in addition to stdout, not instead of it) once that's set. Since `/share` is already read-write-mounted into this add-on too, `--log-dir /share/mycroft/logs` reads those files directly. This covers every add-on in this repo without needing upstream's own Docker-socket-based log-bridging feature at all -- deliberately not wired up, since it would need mounting the host's Docker socket into this container, which upstream's own docs are explicit hands it "effective control over the host's whole Docker daemon", a real privilege escalation for a debugging tool. If Docker-socket access is ever added anyway (e.g. to see something outside this repo's own add-ons), verify the current, correct Supervisor config.yaml mechanism for it first -- not confirmed with the same rigor as the rest of this add-on's design.
- **Service detection (`skillmanager.list`-based) is unaffected by the log-file fix above** and stays limited on this stack for the same reason upstream's own README already documents for distributed, one-process-per-skill installs: that bus message only reports skills loaded in the same process as whichever component answers it. Not something this add-on can fix on its own.
- Not wired into `ha-ovos-integration` -- meant to be opened directly when debugging, same as `ovos-busmon`.
