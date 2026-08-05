# OVOS Persona

Wraps [ovos-persona-server](https://github.com/OpenVoiceOS/ovos-persona-server), exposing an Ollama/OpenAI-compatible chat endpoint. Point Home Assistant's **Ollama** integration at this add-on's address, then select it as the conversation agent in an Assist pipeline — it replaces HA's built-in intent-matching for open-ended questions.

## Setup

1. Install and start the add-on.
2. In HA, add the **Ollama** integration, pointing its server URL at `http://<this add-on's hostname>:8337`.
3. Select the resulting conversation agent in **Settings → Voice assistants → Assist → [your pipeline]**.

## Configuration

| Option | Description |
|---|---|
| `solvers` | Ordered list of OVOS solver plugins — the first one that answers wins |
| `solver_config` | JSON object with per-solver settings, e.g. API keys, or `{"enabled": false}` to disable a plugin without uninstalling it |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for solver plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

Default solvers: `ovos-solver-plugin-ddg` (DuckDuckGo Instant Answers) and `ovos-solver-failure-plugin` (a guaranteed, if unhelpful, fallback). Neither needs an API key.

⚠️ **A solver's PyPI package name and its registered plugin id are not the same string, and don't follow a predictable pattern.** Example: package `ovos-ddg-solver-plugin` registers as `ovos-solver-plugin-ddg` — that's the id `solvers` needs, not the package name. Use `GET /available-solvers` (below) to see the real, installed ids rather than guessing from a package name.

## HTTP bridge (api.py), port 8338

Lets [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) read/edit the `solvers` list from HA's own UI. Independent of `ovos-skills`'/`ovos-core`'s own API URLs — this add-on runs standalone, with or without the others installed.

`ovos-persona-server` only reads its config once, at startup — `PUT /settings` restarts the process for a change to take effect.

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` — true when the persona-server process is alive |
| `GET /available-solvers` | Every question-solver plugin actually installed, by real plugin id |
| `GET /settings` | The current persona configuration |
| `PUT /settings` | Replace the configuration, restart `ovos-persona-server` |

**Current limitation**: only the `solvers` list (which plugins run, in what order) is editable via this bridge. Per-solver settings (enabled flags, API keys) aren't yet exposed there — edit `solver_config` directly in the add-on's own configuration for now.

## Automatic fallback-skill wiring

If [skill-ovos-fallback-chatgpt](https://github.com/OpenVoiceOS/skill-ovos-fallback-chatgpt) is installed (via `ovos-skills-extra`, not this add-on -- an unverified, community skill), every startup rewrites its `settings.json` to point at this persona server instead of the real OpenAI API, with a dummy API key (the skill requires one to be present, but this server doesn't validate it). This gives `ovos-core`'s own skill pipeline a native, last-resort fallback to persona before giving up entirely -- OVOS's own fallback-priority mechanism handling the decision, not something bolted on from outside. `ha-ovos-integration`'s persona setup flow installs the skill automatically, if `ovos-skills-extra` is also configured.

## Known limitations

- **No LLM solver configured by default.** The default solvers do direct lookups, not open-ended reasoning — for a natural-feeling assistant, add an LLM-backed solver (e.g. Ollama-based) via `extra_pip_packages` and `solvers`.
- **`ovos-solver-plugin-ddg` only answers direct topic lookups** ("Isaac Newton"), not conversational questions ("what is the capital of Denmark") — it returns nothing for most everyday questions, and the chain falls through to `ovos-solver-failure-plugin`, whose entire response (in every language) is the literal string `"404"`. Add a real solver if you want useful answers, not a placeholder.
