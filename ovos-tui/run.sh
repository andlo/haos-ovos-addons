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
bashio::log.info "Starting ovos-tui-client in --web mode on :8000"
exec ovos-tui --host "${BUS_HOST}" --port "${BUS_PORT}" \
  --mycroft-conf /share/mycroft/mycroft.conf \
  --log-dir /share/mycroft/logs \
  ${LANG_ARG} \
  --web --web-host 0.0.0.0 --web-port 8000
