#!/usr/bin/with-contenv bashio

# OVOS_BUS_HOST/PORT equivalent -- this tool takes --host/--port
# directly as CLI flags rather than env vars (confirmed by reading its
# own README), pointed at the same shared ovos-messagebus every other
# add-on in this repo connects to (see ovos-core's own run.sh/DOCS.md).
BUS_HOST="b8e040e3-ovos-core"
BUS_PORT="8181"

export XDG_CONFIG_HOME=/share
mkdir -p /share/mycroft
[ -f /share/mycroft/mycroft.conf ] || echo '{}' > /share/mycroft/mycroft.conf

# --lang, read from the shared mycroft.conf if set -- same convention
# as every other add-on in this repo respecting a value another add-on
# or ha-ovos-integration may have already written there, rather than
# hardcoding a default this tool's own --lang flag would otherwise use.
LANG_ARG=""
CONFIGURED_LANG=$(jq -r '.lang // empty' /share/mycroft/mycroft.conf)
if [ -n "${CONFIGURED_LANG}" ]; then
  LANG_ARG="--lang ${CONFIGURED_LANG}"
fi

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections"
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/${BUS_HOST}/${BUS_PORT}) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

# --web-host 0.0.0.0, not this tool's own auto-detection -- same
# reasoning as every other add-on's own API port in this repo: the
# whole point is opening it from a browser on the LAN, and letting a
# containerized tool guess its own "real" address from inside a
# Docker network is a common source of picking an internal-only
# address a browser outside the container can't reach (confirmed by
# this tool's own README warning about exactly that failure mode).
#
# --mycroft-conf points at the SAME shared file every other add-on
# reads/writes, not a private copy -- so the command palette's own
# pipeline view reflects this project's real, current configuration.
#
# --log-dir /share/mycroft/logs -- ovos-core's own run.sh sets
# logs.path to this same directory in the shared mycroft.conf, which
# every OVOS service (confirmed via ovos_utils/log.py directly) reads
# and writes its own real log file into, in addition to stdout, not
# instead of it. Since /share is already read-write-mounted into this
# add-on too, this tool reads those REAL log files directly -- no
# Docker socket / log-bridging feature needed at all for the common
# case where every add-on in this repo is what's being debugged (see
# DOCS.md's "Known limitations" for what's still not covered this way).
# --web-host is ALWAYS 0.0.0.0 now, unconditionally -- binding always
# succeeds (unlike a specific external IP, which crashes: "OSError:
# could not bind on any address out of [...]"), and unlike this add-
# on's own hostname, needs no DNS-ready-yet wait loop either.
#
# What used to require --web-host to ALSO be a browser-reachable
# address is now handled by --web-public-url instead (added upstream
# in ovos-tui-client v0.1.25 specifically for this: see its README's
# "When --web-host can't be both the bind address and the reachable
# one"). That flag ONLY affects the URLs baked into the served page's
# own asset/WebSocket links -- completely independent of the bind
# address above. This add-on's own web_public_url option maps
# directly to it: leave blank and this add-on's own Docker hostname is
# used (works automatically wherever mDNS/.local.hass.io resolution
# works, same as before); set it to something like
# http://192.168.1.50:8000 (this add-on's actual LAN-reachable
# address) if that doesn't resolve for your browser/network -- see
# DOCS.md's "The web_host problem" for the full story of how this was
# figured out, including the two things that didn't work first.
WEB_PUBLIC_URL=$(bashio::config 'web_public_url')
if [ -z "${WEB_PUBLIC_URL}" ] || [ "${WEB_PUBLIC_URL}" = "null" ]; then
  # Try 1: Supervisor's own /network/interface/default/info -- the
  # host's real IP on whichever interface actually has the default
  # route, i.e. its normal LAN-facing address. Doesn't depend on the
  # user having configured anything -- confirmed real, documented
  # endpoint+response shape (.data.ipv4.address is a list of
  # "x.x.x.x/yy" CIDR strings; take the first, strip the prefix).
  # Requires this add-on's hassio_api: true permission.
  NET_IP=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    http://supervisor/network/interface/default/info 2>/dev/null \
    | jq -r '.data.ipv4.address[0] // empty' | cut -d/ -f1)

  # Try 2: Home Assistant Core's own /api/config internal_url --
  # kept as a second attempt for the rarer case where the default-
  # route interface isn't the one actually worth advertising (e.g. a
  # VPN/Tailscale interface holds the default route instead of the
  # real LAN one) and the user has internal_url genuinely configured.
  # Confirmed pattern from developers.home-assistant.io's own docs.
  # Requires this add-on's homeassistant_api: true permission.
  if [ -z "${NET_IP}" ]; then
    HA_INTERNAL_URL=$(curl -s -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      -H "Content-Type: application/json" \
      http://supervisor/core/api/config 2>/dev/null | jq -r '.internal_url // empty')
    if [ -n "${HA_INTERNAL_URL}" ]; then
      NET_IP=$(echo "${HA_INTERNAL_URL}" | sed -E 's#^https?://##; s#[:/].*##')
    fi
  fi

  if [ -n "${NET_IP}" ]; then
    WEB_PUBLIC_URL="http://${NET_IP}:8000"
    bashio::log.info "Auto-detected public URL: ${WEB_PUBLIC_URL}"
  else
    WEB_PUBLIC_URL="http://b8e040e3-ovos-tui:8000"
    bashio::log.info "Could not auto-detect a LAN address (neither Supervisor's own network info nor Home Assistant's internal_url gave anything usable) -- falling back to this add-on's own hostname. Set web_public_url manually if that doesn't resolve for your browser."
  fi
fi

bashio::log.info "Starting ovos-tui-client in --web mode on :8000 (public URL: ${WEB_PUBLIC_URL})"
exec ovos-tui --host "${BUS_HOST}" --port "${BUS_PORT}" \
  --mycroft-conf /share/mycroft/mycroft.conf \
  --log-dir /share/mycroft/logs \
  ${LANG_ARG} \
  --web --web-host 0.0.0.0 --web-public-url "${WEB_PUBLIC_URL}" --web-port 8000
