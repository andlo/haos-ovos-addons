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
# --web-host: this tool's own --help is explicit that this is BOTH
# the bind address AND the address baked into every absolute URL its
# served HTML embeds (static asset <script>/<link> tags, the WebSocket
# endpoint the terminal actually connects through) -- "guessing wrong
# here breaks the page's styling/JS" per its own --help text, confirmed
# for real: with the previous hardcoded "0.0.0.0" here, the browser
# tried to load http://0.0.0.0:8000/static/js/textual.js and open
# ws://0.0.0.0:8000/ws literally, both meaningless as destinations.
# Auto-detection (no --web-host at all) isn't safe to rely on either --
# confirmed by testing directly on this same VM: it resolved to
# Supervisor's own internal Docker network IP (172.30.x.x), which is
# real and valid but NOT reachable from a browser on the actual LAN,
# same practical failure as 0.0.0.0. This add-on's own Docker hostname
# (matching every other add-on's own convention) is real too, but only
# resolves via mDNS (.local.hass.io) -- not guaranteed to work from
# every browser/OS/network the way plain LAN-IP access (the way this
# whole project's other add-ons get accessed in practice) does.
#
# No single value here is correct for every deployment -- unlike a
# plain bind address, this needs to be the address a PERSON'S OWN
# BROWSER can actually reach, which only they know for their own
# network. Exposed as a real, user-set option (web_host), but NOT
# left empty by default: confirmed by testing directly that a
# container can only bind to an address one of its OWN network
# interfaces actually has (its own hostname, its own internal IP, or
# 0.0.0.0) -- trying to bind directly to the HOST's own external LAN
# IP from inside this add-on's own isolated network namespace fails
# outright ("OSError: could not bind on any address out of [...]"),
# it doesn't just render wrong. This add-on deliberately does NOT run
# in host_network mode (a real, broader privilege tradeoff not taken
# here) to make that work, so defaulting to this add-on's own real
# Docker hostname -- reachable via HAOS's own mDNS advertisement
# (hassio_dns/hassio_multicast), same mechanism other add-ons rely on
# -- is the only default that's at least guaranteed not to crash. If
# your browser/OS can't resolve it (some Windows/network setups don't
# support mDNS), setting `web_host` to something your container CAN
# still bind to may not be possible without host networking; this
# add-on doesn't attempt to solve that case.
WEB_HOST=$(bashio::config 'web_host')
WEB_HOST_ARG="--web-host b8e040e3-ovos-tui"
if [ -n "${WEB_HOST}" ]; then
  WEB_HOST_ARG="--web-host ${WEB_HOST}"
fi

# Wait for THIS add-on's own hostname to actually resolve before
# binding to it -- confirmed needed for real: right after a fresh
# `docker start`, Supervisor's internal DNS hadn't yet registered this
# container's own hostname, so the very first launch attempt crashed
# outright ("socket.gaierror: [Errno -5] Name has no usable address")
# rather than just being slow to come up. Same shape as the bus-wait
# loop above, just for DNS instead of a TCP port.
SELF_HOST=$(echo "${WEB_HOST_ARG}" | awk '{print $2}')
for i in $(seq 1 30); do
  getent hosts "${SELF_HOST}" >/dev/null 2>&1 && break
  sleep 1
done

bashio::log.info "Starting ovos-tui-client in --web mode on :8000"
exec ovos-tui --host "${BUS_HOST}" --port "${BUS_PORT}" \
  --mycroft-conf /share/mycroft/mycroft.conf \
  --log-dir /share/mycroft/logs \
  ${LANG_ARG} \
  --web ${WEB_HOST_ARG} --web-port 8000
