FROM ghcr.io/home-assistant/base:latest

# NOT pip install ovos-busmon (PyPI) -- confirmed by testing directly on
# real hardware: the published 0.1.0 wheel is missing its own static/
# directory entirely (index.html, vendored JS/CSS for the web UI),
# so GET / returns a plain 404 even though the FastAPI service itself
# starts fine and genuinely connects to the bus (confirmed via
# /api/status responding correctly with real buffered-message counts).
# A packaging bug (missing package-data declaration), not a config
# issue on this add-on's side -- reported upstream, see DOCS.md.
# Installing from the git repo directly (which DOES include static/)
# sidesteps it, same reasoning as ovos-persona's own Dockerfile pinning
# to a git commit rather than PyPI for a similarly stale/broken release.
RUN apk add --no-cache python3 py3-pip git \
 && pip install --no-cache-dir --break-system-packages \
      "git+https://github.com/OpenVoiceOS/ovos-busmon.git"

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
