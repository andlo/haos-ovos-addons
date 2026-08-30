#!/usr/bin/with-contenv bashio
LOGLEVEL=$(bashio::config 'log_level')

# Same opt-in ovos-workshop version override as ovos-skills' own run.sh
# -- see that file's own comment for the full reasoning
# (OpenVoiceOS/ovos-workshop#559, fixed in alpha 9.2.10a1+, not yet in
# any stable release, deliberately not a default anyone gets silently).
export OVOS_WORKSHOP_VERSION=$(bashio::config 'ovos_workshop_version')

# Shared config, same convention as the other add-ons. This add-on
# never talks to ovos-core's own messagebus/SkillsStore either (same
# reasoning as ovos-skills) -- settings.json for every skill still
# lives on /share via XDG_CONFIG_HOME regardless.
export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections -- needed by each skill's own launched process"
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/b8e040e3-ovos-core/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

mkdir -p /opt/skill-venvs
mkdir -p /share/ovos-pip-cache

bashio::log.info "Starting API on :8502 -- rebuilding any previously-installed skills' venvs from the persisted manifest first"
exec python3 /api.py
