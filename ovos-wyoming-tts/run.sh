#!/usr/bin/with-contenv bashio
PLUGIN=$(bashio::config 'plugin')
PLUGIN_CONFIG=$(bashio::config 'plugin_config')
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
LOGLEVEL=$(bashio::config 'log_level')

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP}
fi

# Shared OVOS config lives on /share so all haos-ovos-addons add-ons (and
# eventually ha-ovos-integration) read/write the same mycroft.conf instead
# of each holding its own disconnected copy. ovos-config's Configuration()
# already respects XDG_CONFIG_HOME, so this is enough to make every OVOS
# tool in this container use the shared file automatically.
export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

# Merge, don't overwrite: other add-ons (stt, wakeword, persona) write their
# own top-level keys into this same file. jq's `+` does a shallow merge —
# our "tts" key replaces any previous value, everything else is preserved.
jq \
  --arg plugin "$PLUGIN" \
  --argjson pconf "$PLUGIN_CONFIG" \
  '. + {tts: ({module: $plugin} + {($plugin): $pconf})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

# Tell Home Assistant this is a Wyoming service once the port is up
# (same pattern as the official Piper add-on's discovery script).
(
  until (exec 3<>/dev/tcp/localhost/10200) 2>/dev/null; do sleep 0.5; done
  exec 3>&- 3<&- 2>/dev/null || true
  config=$(bashio::var.json uri "tcp://$(hostname):10200")
  if bashio::discovery "wyoming" "${config}" > /dev/null; then
    bashio::log.info "Successfully sent discovery information to Home Assistant."
  else
    bashio::log.error "Discovery message to Home Assistant failed!"
  fi
) &

bashio::log.info "Starting wyoming-ovos-tts with plugin ${PLUGIN}"

exec wyoming-ovos-tts \
  --plugin-name "${PLUGIN}" \
  --uri 'tcp://0.0.0.0:10200' \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
