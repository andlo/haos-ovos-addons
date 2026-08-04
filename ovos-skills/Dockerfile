FROM ghcr.io/home-assistant/base:latest

# ovos-core: brings ovos_core.skill_installer (SkillsStore) — the real,
# current, first-party skill install/uninstall mechanism. Not
# ovos-skills-manager (OSM), which ovos-core's own README says stopped
# being supported after ovos-core 0.0.8.
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
