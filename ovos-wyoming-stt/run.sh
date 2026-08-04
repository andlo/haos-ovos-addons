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

jq \
  --arg plugin "$PLUGIN" \
  --argjson pconf "$PLUGIN_CONFIG" \
  '. + {stt: ({module: $plugin} + {($plugin): $pconf})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

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

bashio::log.info "Starting wyoming-ovos-stt with plugin ${PLUGIN}"

exec wyoming-ovos-stt \
  --plugin-name "${PLUGIN}" \
  --uri 'tcp://0.0.0.0:10300' \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
