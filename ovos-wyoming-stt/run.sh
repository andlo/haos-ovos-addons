#!/usr/bin/with-contenv bashio
PLUGIN=$(bashio::config 'plugin')
PLUGIN_CONFIG=$(bashio::config 'plugin_config')
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
LOGLEVEL=$(bashio::config 'log_level')

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP}
fi

CONF_DIR="${HOME:-/root}/.config/mycroft"
mkdir -p "${CONF_DIR}"

jq -n \
  --arg plugin "$PLUGIN" \
  --argjson pconf "$PLUGIN_CONFIG" \
  '{stt: ({module: $plugin} + {($plugin): $pconf})}' \
  > "${CONF_DIR}/mycroft.conf"

(
  bash -c "until echo '{ \"type\": \"describe\" }' > /dev/tcp/localhost/10300; do sleep 0.5; done" > /dev/null 2>&1 || true
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
