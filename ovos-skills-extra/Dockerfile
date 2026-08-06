FROM ghcr.io/home-assistant/base:latest

# The free, unverified counterpart to ovos-skills -- same one-venv-per-
# skill mechanism (see api.py's module docstring for the full
# reasoning), just installing from a raw PyPI-name-or-git-URL text
# field instead of a curated catalog. No ovos-core/ovos-messagebus
# dependency, same as ovos-skills. virtualenv, not the stdlib venv
# module -- more reliably bootstraps pip on Alpine.
RUN apk add --no-cache python3 py3-pip jq git build-base python3-dev \
 && pip install --no-cache-dir --break-system-packages \
      "setuptools<=80.9.0" \
      virtualenv fastapi uvicorn requests ovos-bus-client

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
