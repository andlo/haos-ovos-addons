#!/usr/bin/with-contenv bashio

# Shared config, same convention as every other add-on in this repo --
# so Settings/Skills/Personas edits made here land in the SAME
# mycroft.conf/skills settings.json files the actual running services
# (ovos-core, ovos-skills, ovos-persona) read from, not a private copy.
export XDG_CONFIG_HOME=/share
mkdir -p /share/mycroft
[ -f /share/mycroft/mycroft.conf ] || echo '{}' > /share/mycroft/mycroft.conf

TOKEN=$(bashio::config 'token')

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections"
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/b8e040e3-ovos-core/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

# --host 0.0.0.0 -- unlike ovos-tui-client's --web mode, this tool's
# own --help confirms no separate bind-vs-public-URL split is needed:
# numeric IPs and loopback are always accepted as a Host header
# regardless of --hostname, so plain LAN-IP access (the only way any
# add-on in this repo is normally reached) works without further
# configuration. --token protects it, same reasoning as ovos-busmon's
# own username/password -- this tool changes the actual configuration
# of every OVOS service on this stack, so treat it like a real key
# (upstream's own README: "The page changes the configuration of your
# device, so treat it like a key").
bashio::log.info "Starting ovos-control-panel on :8500"
exec ovos-control-panel --host 0.0.0.0 --port 8500 --token "${TOKEN}"
