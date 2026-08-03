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

jq -n --argjson hw "$HOTWORDS" '{hotwords: $hw}' > "${CONF_DIR}/mycroft.conf"

(
  bash -c "until echo '{ \"type\": \"describe\" }' > /dev/tcp/localhost/10400; do sleep 0.5; done" > /dev/null 2>&1 || true
  config=$(bashio::var.json uri "tcp://$(hostname):10400")
  if bashio::discovery "wyoming" "${config}" > /dev/null; then
    bashio::log.info "Successfully sent discovery information to Home Assistant."
  else
    bashio::log.error "Discovery message to Home Assistant failed!"
  fi
) &

bashio::log.info "Starting wyoming-ovos-wakeword"

exec wyoming-ovos-wakeword \
  --uri 'tcp://0.0.0.0:10400' \
  $( [ "${ZEROCONF}" = "true" ] && echo "--zeroconf" ) \
  $( [ "${LOGLEVEL}" = "debug" ] && echo "--debug" )
