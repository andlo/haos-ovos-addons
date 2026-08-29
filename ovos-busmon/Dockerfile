FROM ghcr.io/home-assistant/base:latest

# ovos-busmon's own static/ directory (the web UI: index.html + assets)
# is NOT included in ITS OWN Python package at all -- confirmed by
# reading its service.py directly: STATIC_DIR = Path(__file__).parent.parent
# / "static" expects static/ to sit as a SIBLING of the installed
# ovos_busmon/ package directory (i.e. directly under site-packages/),
# not inside it and not relative to whatever directory the command is
# run from. Neither the PyPI wheel nor a plain `pip install git+...`
# puts anything there -- confirmed by testing both directly: the
# service itself starts fine and genuinely connects to the bus
# (GET /api/status responds correctly), but GET / 404s either way.
# Reported upstream: https://github.com/OpenVoiceOS/ovos-busmon/issues/65
#
# Fix: install the real PyPI release (stable, no need to track a
# branch just to get static/), then copy static/ from a throwaway
# shallow git clone into the exact sibling location Path(__file__).
# parent.parent resolves to for the INSTALLED package -- computed at
# build time via Python itself, not a hardcoded site-packages path, so
# this doesn't silently break on a future base-image Python version bump.
RUN apk add --no-cache python3 py3-pip git \
 && pip install --no-cache-dir --break-system-packages ovos-busmon \
 && git clone --depth 1 https://github.com/OpenVoiceOS/ovos-busmon.git /tmp/busmon-src \
 && STATIC_DEST="$(python3 -c 'import ovos_busmon, os; print(os.path.dirname(os.path.dirname(ovos_busmon.__file__)))')/static" \
 && cp -r /tmp/busmon-src/static "${STATIC_DEST}" \
 && rm -rf /tmp/busmon-src \
 && apk del git

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
