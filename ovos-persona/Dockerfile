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
RUN apk add --no-cache python3 py3-pip jq \
 && pip install --no-cache-dir --break-system-packages \
      ovos-persona-server ovos-workshop uvicorn ovos-ddg-solver-plugin ovos-solver-failure-plugin

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
