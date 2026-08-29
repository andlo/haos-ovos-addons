# OVOS TUI

A thin Supervisor wrapper around [andlo/ovos-tui-client](https://github.com/andlo/ovos-tui-client) in its `--web` mode -- a split-pane interface (conversation, activity feed, logs, command palette) for testing and debugging OVOS by typing instead of talking, without a mic or speaker.

## What it's for

Type an utterance and see exactly what OVOS does with it: which skill answered (and which ones tried and gave up), fallback behavior, the intent pipeline order, and a live conversation transcript -- all without needing working audio hardware or a wake word. See the upstream README for the full feature list.

## Setup

1. Install and start the other `haos-ovos-addons` add-ons first (this one connects to their shared bus and reads their shared `mycroft.conf`).
2. Start this add-on (`boot: manual` by default, same reasoning as `ovos-busmon` -- a debugging tool, not something to leave running unattended).
3. Open `http://<hostname>:8000/` in a browser.

## Configuration

None yet -- `--host`/`--port` point at the shared bus, `--mycroft-conf` at the shared `mycroft.conf`, and `--lang` is read from that same shared file automatically, all hardcoded in `run.sh` to match every other add-on's own shared-infrastructure conventions rather than exposed as options with only one correct value in this project.

## Known limitations

- **Logs come from real files on the shared `/share` volume, not Docker-log-bridging.** `ovos-core`'s own `run.sh` sets `logs.path` in the shared `mycroft.conf` to `/share/mycroft/logs` — confirmed by reading `ovos_utils/log.py` directly, every OVOS service (the bus, this add-on's own skill manager, each launched skill, `ovos-persona-server`, ...) writes its real log file there (in addition to stdout, not instead of it) once that's set. Since `/share` is already read-write-mounted into this add-on too, `--log-dir /share/mycroft/logs` reads those files directly. This covers every add-on in this repo without needing upstream's own Docker-socket-based log-bridging feature at all -- deliberately not wired up, since it would need mounting the host's Docker socket into this container, which upstream's own docs are explicit hands it "effective control over the host's whole Docker daemon", a real privilege escalation for a debugging tool. If Docker-socket access is ever added anyway (e.g. to see something outside this repo's own add-ons), verify the current, correct Supervisor config.yaml mechanism for it first -- not confirmed with the same rigor as the rest of this add-on's design.
- **Service detection (`skillmanager.list`-based) is unaffected by the log-file fix above** and stays limited on this stack for the same reason upstream's own README already documents for distributed, one-process-per-skill installs: that bus message only reports skills loaded in the same process as whichever component answers it. Not something this add-on can fix on its own.
- Not wired into `ha-ovos-integration` -- meant to be opened directly when debugging, same as `ovos-busmon`.
