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
# lists.
#
# Pinned to the exact commit that merged PR #67, NOT @dev: floating on
# the branch proved genuinely unstable within a single session — the
# AgentMessage fix (PR #67) was confirmed working for hours, then broke
# again on a later rebuild with the identical symptom. Root cause traced
# to ovos-persona-server's own transitive ovos-persona dependency
# (declared as >=0.9.0a6, an unpinned alpha range) continuing to publish
# new alphas that kept adding new default-loaded solver plugins lacking a
# .priority attribute, crashing QuestionSolversService.modules's sort —
# unrelated to PR #67 itself, just exposed by chasing a moving target.
# Our own patch_persona.py is gone too: both the pinned commit and
# current dev already include the official fix under upstream's own
# naming (_messages_to_agent, not ours) — keeping our patch alongside
# would make its own safety assertion fail the build.
# fastapi/uvicorn: our own thin HTTP bridge (api.py) that lets
# ha-ovos-integration read/edit persona.json's solver list and restarts
# ovos-persona-server for changes to take effect (it only reads its
# config at startup, no live-reload) -- see api.py's module docstring.
RUN apk add --no-cache python3 py3-pip jq git \
 && pip install --no-cache-dir --break-system-packages \
      "git+https://github.com/OpenVoiceOS/ovos-persona-server.git@5daafb675520398a888833443e4adecca7e97b58" \
      ovos-ddg-solver-plugin ovos-solver-failure-plugin \
      fastapi uvicorn

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
