#!/usr/bin/with-contenv bashio
PLUGIN=$(bashio::config 'plugin')
PLUGIN_CONFIG=$(bashio::config 'plugin_config')
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
LOGLEVEL=$(bashio::config 'log_level')

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP}
fi

export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

# mycroft.conf is master (see DEVELOPER.md's "mycroft.conf-as-master"
# section): confirmed by reading wyoming-ovos-stt's own source that
# --plugin-name is a REQUIRED CLI arg, not something it reads from
# Configuration() itself -- only the plugin's OWN settings
# (Configuration()["stt"][plugin_name]) come from the shared file. So
# this add-on has to make the "which value wins" decision itself: if
# the shared file already has stt.module (from a previous
# /autoconfigure run on ovos-core, or a manual edit -- the natural move
# for anyone who already knows OVOS), that wins over this add-on's own
# 'plugin' option. Only fall back to options.plugin/plugin_config, and
# only THEN write it into the shared file, when the shared file has
# nothing yet (first boot, or running this add-on standalone without
# ovos-core).
EXISTING_MODULE=$(jq -r '.stt.module // empty' "${CONF_FILE}")

if [ -n "${EXISTING_MODULE}" ]; then
  bashio::log.info "Using stt.module already set in shared mycroft.conf: ${EXISTING_MODULE}"
  ACTIVE_PLUGIN="${EXISTING_MODULE}"
else
  bashio::log.info "No stt.module in shared mycroft.conf yet -- using this add-on's own 'plugin' option: ${PLUGIN}"
  ACTIVE_PLUGIN="${PLUGIN}"
  jq \
    --arg plugin "$PLUGIN" \
    --argjson pconf "$PLUGIN_CONFIG" \
    '. + {stt: ({module: $plugin} + {($plugin): $pconf})}' \
    "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"
fi

(
  until (exec 3<>/dev/tcp/localhost/10300) 2>/dev/null; do sleep 0.5; done
  exec 3>&- 3<&- 2>/dev/null || true
  config=$(bashio::var.json uri "tcp://$(hostname):10300")
  if bashio::discovery "wyoming" "${config}" > /dev/null; then
    bashio::log.info "Successfully sent discovery information to Home Assistant."
  else
    bashio::log.error "Discovery message to Home Assistant failed!"
  fi
) &

bashio::log.info "Starting wyoming-ovos-stt with plugin ${ACTIVE_PLUGIN}"

exec wyoming-ovos-stt \
  --plugin-name "${ACTIVE_PLUGIN}" \
  --uri 'tcp://0.0.0.0:10300' \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
