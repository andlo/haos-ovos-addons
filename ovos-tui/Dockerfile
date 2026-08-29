FROM ghcr.io/home-assistant/base:latest

# andlo/ovos-tui-client, used unmodified, in --web mode -- a real,
# actively-maintained package (README's own claim confirmed by reading
# it directly: split-pane conversation/logs/activity-feed UI, a
# command palette, and a --web flag that serves the exact same
# interface over HTTP instead of drawing to a terminal). The [web]
# extra pulls in whatever serves that mode (a small ASGI app per its
# own docs), on top of the base package.
# >=0.1.25: the release that added --web-public-url, which this
# add-on's own run.sh now depends on (see run.sh's own comments) to
# bind 0.0.0.0 while advertising a separately-configurable, actually
# browser-reachable address.
RUN apk add --no-cache python3 py3-pip \
 && pip install --no-cache-dir --break-system-packages "ovos-tui-client[web]>=0.1.25"

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
