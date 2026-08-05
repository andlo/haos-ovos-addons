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

## HTTP bridge (api.py), port 8338

Added so [ha-ovos-integration](https://github.com/andlo/ha-ovos-integration) can read/edit the
`solvers` list from HA's own UI, same pattern as ovos-core and ovos-skills. Deliberately its own,
independent add-on API URL in that integration (not reused from ovos-skills' or ovos-core's) --
a person can genuinely run persona without skills, skills without persona, or both.

`ovos-persona-server` only reads `persona.json` once, at its own startup -- no live-reload -- so
`PUT /settings` restarts the process (`subprocess.Popen`, not the old `exec` this add-on used
before; an `exec`'d process can't be relaunched by anything downstream of it).

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true/false}` -- true when the persona-server subprocess is alive |
| `GET /available-solvers` | Every question-solver plugin actually installed, via `entry_points(group="opm.solver.question")` -- confirmed correct by reading `ovos-plugin-manager`'s own `find_question_solver_plugins()` source, not guessed |
| `GET /settings` | The current `persona.json` content |
| `PUT /settings` | Replace `persona.json`, restart `ovos-persona-server` |

**Known limitation, first cut**: only the `solvers` list (which plugins run, in what order) is
editable via this bridge. `persona.json` also carries per-solver sub-objects (e.g.
`{"ovos-solver-bm25-freebase-plugin": {"enabled": false}}`) for solvers present but disabled, or
needing their own API keys -- genuinely nested config, not the flat, primitive-valued shape the
skills settings UI's inference mechanism (in ha-ovos-integration) was built for. Left for a
follow-up.

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

## Upstream bugs found while packaging this (both filed, both merged)

1. **PyPI release is stale.** `ovos-persona-server` 0.5.0 on PyPI is missing the
   `ovos_persona_server/schemas` submodule entirely (crashes on import) and under-declares
   dependencies (`ovos-workshop`, `uvicorn`) that `dev`'s `pyproject.toml` already lists.
   Still unfixed on PyPI as of this writing — see the pinned-commit note below for why we
   don't just track `@dev` to get around it.
2. **Chat completions crashed for QuestionSolver-based plugins.**
   `run_chat()`/`run_stream()`'s stateless path passed raw OpenAI-style message dicts straight
   to `Persona.chat`/`stream`, whose type contract is `List[AgentMessage]`.
   Upstream PR: [OpenVoiceOS/ovos-persona-server#67](https://github.com/OpenVoiceOS/ovos-persona-server/pull/67)
   — **merged**. No local patch needed for this specific bug anymore.

## Why we install a pinned commit, not `@dev`

Tracking `git+...@dev` proved genuinely unstable *within a single session*: PR #67's fix was
confirmed working end-to-end for hours, then the exact same symptom came back on a later
rebuild — not because the fix regressed, but because `ovos-persona-server` declares its own
`ovos-persona` dependency as an unpinned alpha range (`>=0.9.0a6`), and that dependency kept
publishing new alphas in between that added new default-loaded solver plugins (`ovos-solver-
bm25-*`, `ovos-solver-yes-no-plugin`, `ovos-solver-bus-plugin`, `ovos-chat-openai-plugin`) —
none of which are `QuestionSolver`-shaped, so they lack the `.priority` attribute
`QuestionSolversService.modules`'s sort needs, crashing every chat completion with
`AttributeError: 'OpenAIChatEngine' object has no attribute 'priority'`, unrelated to PR #67
itself.

Fixed two ways together, confirmed in a clean venv against the real `run_chat()` call path
(not just the lower-level solver service) before deploying:
- **Pinned to the exact commit that merged PR #67**
  (`5daafb675520398a888833443e4adecca7e97b58`), not the floating branch.
- **`solver_config` explicitly disables the polluting plugins** (`enabled: false` for each) —
  this is the part that actually matters going forward, since it makes the add-on robust to
  *future* alpha churn adding yet more default-loaded plugins, not just today's known list.

**Also found, not fixed**: a real but non-fatal argument-order bug in a *third* repo,
`OpenVoiceOS/ovos-persona`'s own `Persona.chat()` — it calls
`self.solvers.chat_completion(messages, sess.lang, sess.system_unit)` positionally, but
`chat_completion`'s signature is `(messages, session_id, lang, units)`, so `sess.lang` lands
in `session_id` and `sess.system_unit` lands in `lang`. Confirmed live: logs
`ERROR - Expected a language code, got 'metric'`. Doesn't crash — `FailureSolver` ignores
`lang` entirely (see "404" below) — but does mean any *working* solver currently gets the
wrong language. Not filed upstream yet; revisit alongside the schemas/PyPI staleness issue.

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
