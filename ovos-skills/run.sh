#!/usr/bin/with-contenv bashio
LOGLEVEL=$(bashio::config 'log_level')

# Optional opt-in override for the ovos-workshop version installed into
# EVERY skill's own venv (see BASELINE_PACKAGES in api.py) -- empty by
# default, meaning "whatever pip resolves normally" (the latest stable
# release, never a pre-release unless explicitly named). Exists because
# a real, confirmed upstream bug (OpenVoiceOS/ovos-workshop#559 -- Adapt
# vocab from .voc files never matching .require()'d intents) is fixed
# only in an alpha release (9.2.10a1+) as of this writing, with no
# stable release carrying the fix yet. Raised and agreed directly: this
# project stays on stable by default, deliberately -- switching the
# whole stack to alpha isn't the answer for one library's one fix, so
# this is an explicit, single-add-on, opt-in choice instead (e.g. set
# to ">=9.2.10a1" to pick it up), not a default anyone gets silently.
export OVOS_WORKSHOP_VERSION=$(bashio::config 'ovos_workshop_version')

# Shared config, same convention as haos-ovos-addons. This add-on no
# longer talks to ovos-core's own SkillsStore/messagebus at all (see
# api.py's module docstring -- confirmed unreliable for both install
# and uninstall, replaced with a direct, per-skill-venv pip flow), so
# the allow_pip/constraints keys SkillsStore itself used to read are no
# longer relevant here (allow_pip option itself removed from
# config.yaml/schema in 0.0.30, having been dead since this rewrite).
# XDG_CONFIG_HOME=/share is kept regardless -- settings.json for every
# skill still lives there, unaffected by any of this.
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
mkdir -p /share/ovos-pip-cache

# api.py's own lifespan handler rebuilds every skill's venv from the
# persisted manifest.json (see its module docstring's "PERSISTENCE
# MODEL" -- venvs themselves are NOT persisted, only a small manifest of
# skill_id -> source URL), then launches each one. This can take a
# while on a container with several skills installed (a fresh git
# clone + pip install per skill), which is why this happens inside the
# API's own async startup rather than blocking run.sh further.
bashio::log.info "Starting API on :8500 -- rebuilding any previously-installed skills' venvs from the persisted manifest first"
exec python3 /api.py
