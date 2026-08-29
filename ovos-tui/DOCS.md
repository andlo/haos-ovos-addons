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

- **No log bridging or service detection.** Upstream's own README documents a real feature for exactly this project's shape (a containerized, one-process-per-service OVOS deployment): bridging each container's `docker logs -f` into synthesized log files, and detecting running services via the Docker/Podman socket. Deliberately NOT wired up here -- it requires mounting the host's Docker socket into this add-on's container (`/var/run/docker.sock`), which upstream's own docs are explicit hands this container "effective control over the host's whole Docker daemon", not just the OVOS containers it would actually need to see. That's a real, meaningful privilege escalation for a debugging tool, not something to enable by default without a specific decision to do so. Without it: the Logs pane will report it found nothing (the container has no on-disk log files and no socket to bridge from), and the command palette's service-status view will be limited or empty. The Conversation, Activity, and command-palette features that talk directly to the messagebus are unaffected and fully functional.
- If Docker-socket access is ever added, note the Supervisor-specific mechanism for granting it wasn't confirmed with the same rigor as the rest of this add-on's design during this pass -- verify the current, correct Supervisor config.yaml option (rather than assuming `full_access` or similar) before implementing, and treat it as a deliberate, documented, opt-in decision the same way `ovos-busmon`'s own credentials/binding choices are.
- Not wired into `ha-ovos-integration` -- meant to be opened directly when debugging, same as `ovos-busmon`.
