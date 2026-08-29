#!/usr/bin/with-contenv bashio

# OVOS_BUS_HOST/PORT -- the same shared ovos-messagebus ovos-core hosts
# for every other add-on in this repo (see ovos-core's own run.sh/
# DOCS.md's "Shared messagebus" section). Supervisor assigns one
# repo-hash-based hostname per REPOSITORY, not per add-on, so
# "b8e040e3-ovos-core" is the same hostname the skills/skills-extra/
# persona add-ons already connect to -- confirmed by their own run.sh
# scripts, not a guess specific to this add-on.
export OVOS_BUS_HOST="b8e040e3-ovos-core"
export OVOS_BUS_PORT="8181"

# 0.0.0.0, not busmon's own 127.0.0.1 default -- this add-on's whole
# purpose is to be opened from a browser on the LAN, same reasoning as
# every other add-on's own API port in this repo. Real credentials
# (below) are what actually protects it, matching upstream's own
# documented security model ("On any other address, set a token" --
# here, HTTP Basic auth via BUSMON_USERNAME/PASSWORD instead, since
# that's what this specific package actually supports, confirmed by
# reading its own README directly).
export BUSMON_HOST="0.0.0.0"
export BUSMON_PORT="8005"

export BUSMON_USERNAME=$(bashio::config 'username')
export BUSMON_PASSWORD=$(bashio::config 'password')
export BUFFER_SIZE=$(bashio::config 'buffer_size')

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections"
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/${OVOS_BUS_HOST}/${OVOS_BUS_PORT}) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

bashio::log.info "Starting ovos-busmon on :8005 -- confirmed real credentials are set, not left at their upstream defaults, is on you: change username/password in this add-on's own Configuration tab before exposing it beyond a trusted LAN"
exec ovos-busmon
