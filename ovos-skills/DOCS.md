# OVOS Skills

🚧 **v0.0.x — work in progress.** See the "What was fixed on real hardware" section below
before trusting the happy path blindly.

## What it does

Installs, lists, and removes OVOS skills via a small HTTP API, bridging to `ovos-core`'s own
`SkillsStore` (`ovos_core.skill_installer`) over a private internal `ovos-messagebus` that
never leaves this container. Not `ovos_skill_manager` (OSM) — that project's own README says
it stopped being supported after ovos-core 0.0.8.

Called by [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration), which manages
skills as config subentries — one per installed skill, in the same place as everything else
in HA.

## API

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` |
| `GET /catalog` | Proxies the official, curated `skills.json` feed (36 skills as of the last check) |
| `GET /skills` | Lists installed skills — **heuristic**: pip packages named `ovos-skill-*`/`skill-*`, not a confirmed mechanism |
| `POST /skills/install` | Body `{"url": "https://github.com/..."}`. Async — returns `{"status": "pending", "poll": "..."}` immediately, doesn't block on pip |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result |
| `DELETE /skills/{skill_id}` | Same async pattern as install |

## Configuration

| Option | Description |
|---|---|
| `allow_pip` | Gates `SkillsStore` itself — it refuses to act at all if this is off |
| `log_level` | `debug`, `info`, `warning`, or `error` |

## What was fixed on real hardware

1. **`error: externally-managed-environment` (PEP 668)** — `SkillsStore`'s own pip calls need
   `skills.installer.break_system_packages: true` in `mycroft.conf`, which it already
   supports but wasn't set. Same class of issue as the other four add-ons hit repeatedly.
2. **Synchronous design timed out.** The first version blocked the HTTP request until pip
   finished — timed out against a 30s client, and would've been a poor fit for eventually
   being called from a HA config flow (which expects quick responses). Rebuilt as
   fire-and-poll instead.

## Known limitations

- `GET /skills` (list installed) is a naming-convention heuristic, not confirmed against a
  real installed skill yet.
- Explicitly does not make skills respond to voice queries — that needs OVOS's
  messagebus/HiveMind bridged into Assist, which doesn't exist yet. This add-on only makes
  skills installable and configurable.
- Multiple skills share one Python environment (unlike `ovos-docker`'s one-container-per-skill
  model) — a deliberately accepted dependency-conflict risk, not a solved problem.
