# OVOS Persona

🚧 **v0.0.x — untested, work in progress.** Version stays below 0.1.0 until this has actually
run successfully on a real HAOS install.

## What it does

Wraps [ovos-persona-server](https://github.com/OpenVoiceOS/ovos-persona-server), exposing an
Ollama/OpenAI-compatible chat endpoint on port 8337. Point Home Assistant's **Ollama**
integration at this add-on's address, then select it as the conversation agent in an Assist
pipeline — it replaces HA's built-in intent-matching for open-ended questions.

## Configuration

| Option | Description |
|---|---|
| `solvers` | Ordered list of OVOS solver plugins — the first one that answers wins |
| `solver_config` | JSON object with per-solver settings, e.g. API keys |
| `extra_pip_packages` | Space-separated pip packages to install at startup, for solver plugins not baked into the image |
| `log_level` | `debug`, `info`, `warning`, or `error` |

Default solvers (DuckDuckGo, Wikipedia, plus a failure fallback so it always says something)
need no configuration to try out and don't require an API key.

## Known limitations

- No LLM solver configured by default — add one (e.g. an Ollama-backed solver) via
  `extra_pip_packages` and `solvers` if you want generative answers, not just lookups.
- Not yet verified against a real HAOS Supervisor install or against HA's Ollama integration
  specifically.
