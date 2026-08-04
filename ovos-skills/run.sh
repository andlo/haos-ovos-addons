#!/usr/bin/with-contenv bashio
ALLOW_PIP=$(bashio::config 'allow_pip')
LOGLEVEL=$(bashio::config 'log_level')

# Shared config, same convention as haos-ovos-addons. This add-on no
# longer talks to ovos-core's own SkillsStore/messagebus at all (see
# api.py's module docstring -- confirmed unreliable for both install
# and uninstall, replaced with a direct, per-skill-venv pip flow), so
# the allow_pip/constraints keys SkillsStore itself used to read are no
# longer relevant here. XDG_CONFIG_HOME=/share is kept regardless --
# settings.json for every skill still lives there, unaffected by any
# of this.
export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections -- needed by each skill's own launched process, even though this add-on's own API no longer connects to it directly"
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/b8e040e3-ovos-core/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

mkdir -p /opt/skill-venvs

# api.py's own lifespan handler rebuilds every skill's venv from the
# persisted manifest.json (see its module docstring's "PERSISTENCE
# MODEL" -- venvs themselves are NOT persisted, only a small manifest of
# skill_id -> source URL), then launches each one. This can take a
# while on a container with several skills installed (a fresh git
# clone + pip install per skill), which is why this happens inside the
# API's own async startup rather than blocking run.sh further.
bashio::log.info "Starting API on :8500 -- rebuilding any previously-installed skills' venvs from the persisted manifest first"
exec python3 /api.py
