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

# SkillsStore's default constraints file (OVOS's own "stable" pin list) was
# found stale on real hardware: it pinned ovos-skill-date-time<0.5.0 while
# the skill's actual dev-branch HEAD is 1.1.14a2, so installing anything
# via the default constraints failed immediately with ResolutionImpossible.
# Point it at an empty local file instead — pip still requires a valid,
# existing constraints file (that's what validate_constraints() checks),
# an empty one just contains zero actual pins.
EMPTY_CONSTRAINTS="/etc/ovos-empty-constraints.txt"
: > "${EMPTY_CONSTRAINTS}"

jq --argjson allow "$([ "${ALLOW_PIP}" = "true" ] && echo true || echo false)" \
  --arg constraints "${EMPTY_CONSTRAINTS}" \
  '. + {skills: ((.skills // {}) + {installer: (((.skills // {}).installer // {}) + {allow_pip: $allow, break_system_packages: true, constraints: $constraints})})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

# Restore any skills persisted from a previous container before anything
# else starts — pip installs otherwise land in this container's own
# filesystem layer and are wiped on the next rebuild/update, confirmed on
# real hardware. api.py copies newly-installed package files into
# PERSIST_DIR after every successful install; this is the other half.
PERSIST_DIR="/share/ovos-skills/persisted-packages"
if [ -d "${PERSIST_DIR}" ] && [ -n "$(ls -A "${PERSIST_DIR}" 2>/dev/null)" ]; then
  SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")
  bashio::log.info "Restoring persisted skill packages from ${PERSIST_DIR} into ${SITE_PACKAGES}"
  cp -a "${PERSIST_DIR}/." "${SITE_PACKAGES}/"
fi

bashio::log.info "Waiting for the shared ovos-messagebus (hosted by ovos-core) to accept connections"
# No longer starting our own private ovos-messagebus here -- see
# DEVELOPER.md's "Skill runtime" section. This container now connects to
# the SHARED bus hosted by ovos-core (b8e040e3-ovos-core:8181) instead of
# running its own, isolated one. ovos-skill-installer and api.py both
# read websocket.host from the shared mycroft.conf via Configuration(),
# same as before -- the only change is what that shared value now points
# at.
for i in $(seq 1 60); do
  (exec 3<>/dev/tcp/b8e040e3-ovos-core/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 1
done

bashio::log.info "Starting ovos-skill-installer (SkillsStore, standalone)"
ovos-skill-installer &
SI_PID=$!

bashio::log.info "Starting API on :8500"
exec python3 /api.py
