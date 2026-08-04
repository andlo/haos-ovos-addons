FROM ghcr.io/home-assistant/base:latest

# ovos-core: brings ovos_core.skill_installer (SkillsStore) — the real,
# current, first-party skill install/uninstall mechanism. Not
# ovos-skills-manager (OSM), which ovos-core's own README says stopped
# being supported after ovos-core 0.0.8.
# Installed from git@dev, not PyPI: the latest PyPI release (2.1.1) has
# handle_uninstall_skill() as a stub ("pip uninstall not yet implemented"),
# confirmed on real hardware — install() works, uninstall() doesn't. The
# dev branch has the real implementation. Same "PyPI lags dev" pattern hit
# with ovos-persona-server earlier tonight. Revisit once a PyPI release
# catches up.
# ovos-messagebus: the internal bus SkillsStore and our own API both
# connect to. Never exposed outside this container.
# fastapi/uvicorn: our own thin HTTP-to-messagebus bridge.
RUN apk add --no-cache python3 py3-pip jq git build-base python3-dev \
 && pip install --no-cache-dir --break-system-packages \
      "setuptools<=80.9.0" \
      "git+https://github.com/OpenVoiceOS/ovos-core.git@dev" \
      ovos-messagebus fastapi uvicorn ovos-bus-client

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
