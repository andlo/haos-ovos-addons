#!/usr/bin/with-contenv bashio
HOTWORDS=$(bashio::config 'hotwords_config')
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
ZEROCONF=$(bashio::config 'zeroconf')
LOGLEVEL=$(bashio::config 'log_level')

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP}
fi

CONF_DIR="${HOME:-/root}/.config/mycroft"
mkdir -p "${CONF_DIR}"

# Unlike TTS/STT, all configured wake words are loaded on demand — there is
# no single "active plugin", so the whole hotwords dict is written as-is.
jq -n --argjson hw "$HOTWORDS" '{hotwords: $hw}' > "${CONF_DIR}/mycroft.conf"

bashio::log.info "Starting wyoming-ovos-wakeword"

exec wyoming-ovos-wakeword \
  --uri 'tcp://0.0.0.0:10400' \
  $( [ "${ZEROCONF}" = "true" ] && echo "--zeroconf" ) \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
