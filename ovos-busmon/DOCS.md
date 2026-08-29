# OVOS Bus Monitor

A thin Supervisor wrapper around [OpenVoiceOS/ovos-busmon](https://github.com/OpenVoiceOS/ovos-busmon), used entirely unmodified -- a live monitor, capture, and injection tool for the shared OVOS messagebus every other add-on in this repo connects to.

## What it's for

Debugging: watch every bus message live as it happens (filter by type, inspect payloads, group by session into per-interaction timelines), test a skill by sending it a chat message and watching the bus handle the turn, or inject an arbitrary message onto the bus by hand. Not something to leave running unattended -- see "Security" below.

## Setup

1. Install and start the other `haos-ovos-addons` add-ons first (this one connects to their shared bus, hosted by `ovos-core`).
2. **Change the username/password** in this add-on's own Configuration tab -- upstream ships `ovos`/`ovos` as its default, and this add-on inherits that same default until changed.
3. Start this add-on (`boot: manual` by default -- deliberately not started automatically on every boot, see "Security").
4. Open `http://<hostname>:8005/` in a browser.

## Security

This add-on binds `0.0.0.0` (reachable on your LAN), not upstream's own default `127.0.0.1` (local-machine-only) -- the whole point is opening it from a browser elsewhere on the network. That makes the credentials above the *only* thing standing between anyone on your LAN and:

- Reading every bus message, including whatever a skill puts in one (confirmed by upstream's own docs: no redaction of any kind)
- **Injecting arbitrary messages onto the bus** -- upstream's own README: "gives anyone who can reach it full ability to emit any message on the bus"

`boot: manual` and real credentials are both deliberate defaults, not just upstream's own choices carried over unexamined -- this is a genuine power tool, not something to run unattended the way the other add-ons in this repo are designed to.

## Configuration

| Option | Description |
|---|---|
| `username` | HTTP Basic auth username |
| `password` | HTTP Basic auth password -- **change this from the default** |
| `buffer_size` | In-memory ring buffer capacity (messages) for the timeline view and JSONL export |

## Relationship to the other add-ons

Connects to the same shared `ovos-messagebus` `ovos-core` hosts for `ovos-skills`/`ovos-skills-extra`/`ovos-persona` (`b8e040e3-ovos-core:8181`) -- read-only for normal monitoring, but the Inject panel can genuinely affect the running system, same as any other client on that bus.

## Known limitations

- Not wired into `ha-ovos-integration` in any way (no API URL field, no link) -- this add-on is meant to be opened directly in a browser when debugging, not something the HA integration needs to know about for its own normal operation.
- No HTTPS -- upstream's own README is explicit about this ("It has no TLS"). Credentials go over plain HTTP on your LAN.
- **Build-time workaround for a real upstream bug**: `ovos-busmon`'s own `service.py` looks for its web UI's `static/` directory as a *sibling of the installed `ovos_busmon/` package* (`Path(__file__).parent.parent / "static"`), but neither the PyPI release nor a plain git install ever puts anything there -- confirmed by testing both directly: the FastAPI service starts fine and genuinely connects to the bus (`GET /api/status` responds correctly), but `GET /` 404s regardless of install source. This Dockerfile installs the real PyPI release, then copies `static/` from a throwaway shallow git clone into the exact sibling location Python resolves at build time (not a hardcoded `site-packages` path, so a future base-image Python version bump doesn't silently break this again). Reported upstream: [OpenVoiceOS/ovos-busmon#65](https://github.com/OpenVoiceOS/ovos-busmon/issues/65). Revisit removing this workaround once fixed there.
