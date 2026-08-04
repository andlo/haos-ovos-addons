FROM ghcr.io/home-assistant/base:latest

# One isolated Python venv per installed skill now (see api.py's module
# docstring) -- this add-on no longer talks to ovos-core's own
# SkillsStore/messagebus at all, confirmed unreliable for both install
# and uninstall. No ovos-core/ovos-messagebus dependency needed here
# anymore; each skill's own venv pulls in whatever OVOS packages IT
# needs directly, isolated from this container's own environment.
# virtualenv, not the stdlib venv module -- more reliably bootstraps
# pip inside a fresh venv on Alpine (ensurepip support in the base
# python3 apk package is not guaranteed the way it is on most other
# distros).
# fastapi/uvicorn: our own thin HTTP API. git: skills install from git
# URLs. build-base/python3-dev: some skills' own dependencies need to
# compile from source inside their own venv.
RUN apk add --no-cache python3 py3-pip jq git build-base python3-dev \
 && pip install --no-cache-dir --break-system-packages \
      "setuptools<=80.9.0" \
      virtualenv fastapi uvicorn requests

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
