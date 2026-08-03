# OVOS Persona

🚧 **v0.0.x — work in progress, verified running with known gaps.** Version stays below 0.1.0
until the default solver set gives genuinely useful answers, not just "no crash."

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

Default solvers: `ovos-solver-plugin-ddg` (DuckDuckGo Instant Answers) plus
`ovos-solver-failure-plugin` (always says *something*, even if it's just "404" — see Known
limitations). Neither needs configuration or an API key to try out.

⚠️ The solver package names and the plugin identifiers used in the `solvers` list are
**not the same string** and don't follow an obvious pattern — `ovos-persona-server`'s own
README examples are stale. Confirmed by installing packages and inspecting their registered
entry points directly:
- package `ovos-ddg-solver-plugin` → registers plugin id `ovos-solver-plugin-ddg`
- package `ovos-solver-failure-plugin` → registers plugin id `ovos-solver-failure-plugin` (matches, this one's fine)
- `ovos-wikipedia-plugin` (the current PyPI package) only registers the newer
  `opm.agents.retrieval` entry point, not `opm.solver.question` — **not usable** by
  `ovos-persona-server` as-is. Dropped from defaults until a compatible package is found.

## Upstream bugs found while packaging this (both filed)

1. **PyPI release is stale.** `ovos-persona-server` 0.5.0 on PyPI is missing the
   `ovos_persona_server/schemas` submodule entirely (crashes on import) and under-declares
   dependencies (`ovos-workshop`, `uvicorn`) that the `dev` branch's `pyproject.toml` already
   lists. Workaround: install straight from `git@dev` instead of PyPI (see `Dockerfile`).
2. **Chat completions crashed for QuestionSolver-based plugins.**
   `run_chat()`/`run_stream()`'s stateless path passed raw OpenAI-style message dicts straight
   to `Persona.chat`/`stream`, whose type contract is `List[AgentMessage]` — any
   QuestionSolver-based plugin then crashed on `messages[-1].content` (`'dict' object has no
   attribute 'content'`), surfacing to callers as a confusing `'NoneType' object has no
   attribute 'split'`. Fixed with a build-time patch (`patch_persona.py`) until merged upstream.
   - Upstream PR: [OpenVoiceOS/ovos-persona-server#67](https://github.com/OpenVoiceOS/ovos-persona-server/pull/67)
   - **Once merged and released**, remove `patch_persona.py` and its `Dockerfile` step, and
     switch the install back to plain `ovos-persona-server` from PyPI once a release exists
     that includes both this fix and the `schemas` submodule.

## Known limitations

- No LLM solver configured by default — add one (e.g. an Ollama-backed solver) via
  `extra_pip_packages` and `solvers` if you want generative answers, not just lookups.
- **The default solver set gives weak or joke answers, not a bug but a real UX gap.**
  DuckDuckGo's Instant Answer API is built for direct topic lookups ("Isaac Newton"), not
  natural questions ("what is the capital of Denmark") — it legitimately returns nothing for
  most conversational queries. When it does, the chain correctly falls through to
  `ovos-solver-failure-plugin`, whose entire fallback vocabulary — in every language, since it
  ships **no locale dialog files at all** — is the single hardcoded string `"404"`. Confirmed
  end-to-end on real hardware: `HTTP 200`, response content literally `"404"`. Not something to
  patch; the practical fix is adding a real LLM solver for anyone who wants this add-on to feel
  like an actual assistant rather than a search-box-shaped disappointment.
- Verified end-to-end on a real HAOS Supervisor as of v0.0.7: builds, starts, `/v1/models`
  returns the persona, `/v1/chat/completions` returns `HTTP 200` with a real (if underwhelming)
  answer. Not yet tested against HA's Ollama integration specifically, only via direct HTTP call.
