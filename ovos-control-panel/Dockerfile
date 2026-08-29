FROM ghcr.io/home-assistant/base:latest

# OpenVoiceOS/ovos-control-panel, used entirely unmodified -- an
# official OVOS project (same author, TigreGotico, as ovos-busmon):
# a unified local web UI covering Dashboard, Settings, Skills,
# Plugins, Personas, Translate, and Backup. Its own README documents
# --host/--port/--token/--hostname CLI flags with no separate bind-
# vs-public-URL split needed (unlike ovos-tui-client's --web mode) --
# confirmed via its own --help: numeric IPs and loopback are always
# accepted as a Host header regardless of --hostname, so plain LAN-IP
# access (the way every add-on in this repo is normally reached)
# works without extra configuration.
RUN apk add --no-cache python3 py3-pip \
 && pip install --no-cache-dir --break-system-packages ovos-control-panel

COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
