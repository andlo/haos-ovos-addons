FROM ghcr.io/home-assistant/base:latest

# ovos-core: brings ovos_core.skill_installer (SkillsStore) — the real,
# current, first-party skill install/uninstall mechanism. Not
# ovos-skills-manager (OSM), which ovos-core's own README says stopped
# being supported after ovos-core 0.0.8.
# From PyPI, not git@dev: dev has a real uninstall implementation (PyPI's
# is a stub, see DOCS.md), but dev's own dependency requirements
# (ovos_bus_client>=2.7.1a1, ovos-config>=2.1.4a5, ...) aren't satisfied
# by ovos-messagebus's own dev branch either — confirmed via `pip check`
# after trying that combination, real conflicts remain. Two independently
# drifting dev branches, not a matched pair. Staying on PyPI: install is
# fully verified working end-to-end; uninstall is a known, documented
# upstream gap rather than something worth chasing a broken combination
# for.
# ovos-messagebus: the internal bus SkillsStore and our own API both
# connect to. Never exposed outside this container.
# fastapi/uvicorn: our own thin HTTP-to-messagebus bridge.
RUN apk add --no-cache python3 py3-pip jq git build-base python3-dev \
 && pip install --no-cache-dir --break-system-packages \
      "setuptools<=80.9.0" \
      ovos-core ovos-messagebus fastapi uvicorn ovos-bus-client

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
