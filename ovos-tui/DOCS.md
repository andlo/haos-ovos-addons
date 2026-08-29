# OVOS TUI

A thin Supervisor wrapper around [andlo/ovos-tui-client](https://github.com/andlo/ovos-tui-client) in its `--web` mode -- a split-pane interface (conversation, activity feed, logs, command palette) for testing and debugging OVOS by typing instead of talking, without a mic or speaker.

## What it's for

Type an utterance and see exactly what OVOS does with it: which skill answered (and which ones tried and gave up), fallback behavior, the intent pipeline order, and a live conversation transcript -- all without needing working audio hardware or a wake word. See the upstream README for the full feature list.

## Setup

1. Install and start the other `haos-ovos-addons` add-ons first (this one connects to their shared bus and reads their shared `mycroft.conf`).
2. Start this add-on (`boot: manual` by default, same reasoning as `ovos-busmon` -- a debugging tool, not something to leave running unattended).
3. Open `http://<hostname>:8000/` in a browser -- reachable via the Home Assistant host's own LAN IP just fine for this first load. But the page's own JS and terminal connection load from `http://b8e040e3-ovos-tui:8000/...` regardless of how you reached the page itself (see "The web_host problem" below for why) -- if the terminal never appears and stays on a plain, unstyled page, your browser/network likely can't resolve that hostname via mDNS.

## Configuration

| Option | Description |
|---|---|
| `web_host` | Advanced/optional -- see "The web_host problem" below. Leave blank unless the default doesn't work for you. |

## The web_host problem

`ovos-tui-client`'s own `--help` is explicit: `--web-host` is BOTH the address this add-on's web server binds to AND the address baked into every absolute URL its served HTML embeds (static asset `<script>`/`<link>` tags, the WebSocket endpoint the terminal actually connects through). Get it wrong and the page loads with no styling and a permanently stuck "terminal" area that never connects -- confirmed directly: with the naive default of `0.0.0.0`, the browser tried to load `http://0.0.0.0:8000/static/js/textual.js` and open `ws://0.0.0.0:8000/ws`, both meaningless as destinations.

There is no value that's correct for every deployment. Confirmed by testing directly, in order of what was tried:

- `0.0.0.0` -- binds fine, but produces exactly the broken page above.
- No `--web-host` at all (the tool's own auto-detection) -- resolved to Supervisor's own internal Docker network IP (`172.30.x.x`), real but not reachable from a browser on the actual LAN. Same practical failure as `0.0.0.0`.
- The Home Assistant host's own real LAN IP (e.g. `192.168.1.50`) -- **crashes the add-on outright**: `OSError: could not bind on any address out of [...]`. A container can only bind to an address one of its own network interfaces actually has; the host's real IP isn't one of them from inside this add-on's own isolated network namespace. Only works in `host_network: true` mode, which this add-on deliberately doesn't use (a real, broader privilege tradeoff, not taken here without a specific decision to do so).
- **This add-on's own Docker hostname** (`b8e040e3-ovos-tui`, matching this project's own established add-on-hostname convention) -- binds successfully (it's the container's own address) and is advertised on the LAN via HAOS's own mDNS setup (the `hassio_dns`/`hassio_multicast` add-ons/services), the same mechanism other Home Assistant add-ons already rely on for this. **This is the default.**

If your browser or OS doesn't support mDNS (some Windows/network configurations don't), the hostname won't resolve and the page will fail to load at all -- a clear connection error, not the silent broken-styling failure the wrong address produces. There is no other address this add-on's own container can bind to that solves this without host networking, which isn't used here; `web_host` exists as an escape hatch for anyone with a specific alternative that does work for their own network, not a guaranteed fix.

## Known limitations

- **Logs come from real files on the shared `/share` volume, not Docker-log-bridging.** `ovos-core`'s own `run.sh` sets `logs.path` in the shared `mycroft.conf` to `/share/mycroft/logs` — confirmed by reading `ovos_utils/log.py` directly, every OVOS service (the bus, this add-on's own skill manager, each launched skill, `ovos-persona-server`, ...) writes its real log file there (in addition to stdout, not instead of it) once that's set. Since `/share` is already read-write-mounted into this add-on too, `--log-dir /share/mycroft/logs` reads those files directly. This covers every add-on in this repo without needing upstream's own Docker-socket-based log-bridging feature at all -- deliberately not wired up, since it would need mounting the host's Docker socket into this container, which upstream's own docs are explicit hands it "effective control over the host's whole Docker daemon", a real privilege escalation for a debugging tool. If Docker-socket access is ever added anyway (e.g. to see something outside this repo's own add-ons), verify the current, correct Supervisor config.yaml mechanism for it first -- not confirmed with the same rigor as the rest of this add-on's design.
- **Service detection (`skillmanager.list`-based) is unaffected by the log-file fix above** and stays limited on this stack for the same reason upstream's own README already documents for distributed, one-process-per-skill installs: that bus message only reports skills loaded in the same process as whichever component answers it. Not something this add-on can fix on its own.
- Not wired into `ha-ovos-integration` -- meant to be opened directly when debugging, same as `ovos-busmon`.
