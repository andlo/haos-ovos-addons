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
  '{tts: ({module: $plugin} + {($plugin): $pconf})}' \
  > "${CONF_DIR}/mycroft.conf"

bashio::log.info "Starting wyoming-ovos-tts with plugin ${PLUGIN}"

exec wyoming-ovos-tts \
  --plugin-name "${PLUGIN}" \
  --uri 'tcp://0.0.0.0:10200' \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
