#!/usr/bin/with-contenv bashio
ALLOW_PIP=$(bashio::config 'allow_pip')
LOGLEVEL=$(bashio::config 'log_level')

# Shared config, same convention as haos-ovos-addons. allow_pip lives
# under skills.installer.allow_pip — the exact path
# ovos_core.skill_installer.SkillsStore reads via
# Configuration().get("skills", {}).get("installer", {}).
export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

jq --argjson allow "$([ "${ALLOW_PIP}" = "true" ] && echo true || echo false)" \
  '. + {skills: ((.skills // {}) + {installer: (((.skills // {}).installer // {}) + {allow_pip: $allow, break_system_packages: true})})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

bashio::log.info "Starting internal ovos-messagebus"
ovos-messagebus &
MB_PID=$!

# Wait for the bus to actually accept connections before starting anything
# that depends on it.
for i in $(seq 1 20); do
  (exec 3<>/dev/tcp/localhost/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 0.5
done

bashio::log.info "Starting ovos-skill-installer (SkillsStore, standalone)"
ovos-skill-installer &
SI_PID=$!

bashio::log.info "Starting API on :8500"
exec python3 /api.py
