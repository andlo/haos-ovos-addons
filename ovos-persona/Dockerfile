FROM ghcr.io/home-assistant/base:latest

# Package names here don't match the entry-point names used in persona.json's
# "solvers" list (which is what ovos-persona-server actually resolves at
# runtime via ovos_plugin_manager.solvers.find_question_solver_plugins) — the
# ovos-persona-server README examples are stale. Confirmed by installing and
# inspecting entry points directly:
#   package ovos-ddg-solver-plugin -> registers "ovos-solver-plugin-ddg"
#   package ovos-solver-failure-plugin -> registers "ovos-solver-failure-plugin"
# ovos-wikipedia-plugin (the current PyPI package) only registers the newer
# opm.agents.retrieval entry point, not opm.solver.question, so it is NOT
# usable by ovos-persona-server as-is — dropped from defaults until a
# compatible wikipedia question-solver package is found.
# PyPI's published ovos-persona-server (0.5.0) is stale relative to the
# dev branch — it's missing the ovos_persona_server/schemas submodule
# entirely (ModuleNotFoundError at startup) and under-declares several
# dependencies (ovos-workshop, uvicorn) that dev's pyproject.toml already
# lists. Installing straight from git@dev instead of PyPI until a new
# PyPI release catches up.
RUN apk add --no-cache python3 py3-pip jq git \
 && pip install --no-cache-dir --break-system-packages \
      "git+https://github.com/OpenVoiceOS/ovos-persona-server.git@dev" \
      ovos-ddg-solver-plugin ovos-solver-failure-plugin

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
