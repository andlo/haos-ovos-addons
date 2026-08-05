#!/usr/bin/with-contenv bashio
HOTWORDS=$(bashio::config 'hotwords_config')
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
ZEROCONF=$(bashio::config 'zeroconf')
LOGLEVEL=$(bashio::config 'log_level')

# Shared, content-addressed pip cache on /share -- safe across every
# add-on and every venv (keyed by package+version+hash, never a
# collision risk), unlike sharing an actual installation would be.
# Persists across rebuilds (unlike the add-on's own container
# filesystem), so a package already fetched by ANY add-on or any
# skill's own venv doesn't need re-downloading/re-building here again.
mkdir -p /share/ovos-pip-cache
if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --cache-dir=/share/ovos-pip-cache --break-system-packages ${EXTRA_PIP}
fi

export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

# mycroft.conf is master (see DEVELOPER.md's "mycroft.conf-as-master"
# section): confirmed by reading wyoming-ovos-wakeword's own source that,
# unlike tts/stt, it reads its ENTIRE hotwords definition straight from
# Configuration()["hotwords"] -- no --plugin-name CLI arg involved at
# all. So this add-on already gets the reversal "for free" at the
# consumer side; the only thing to fix here is not unconditionally
# overwriting an existing hotwords section (e.g. from a previous
# /autoconfigure run, or a manual edit) with this add-on's own
# hotwords_config option on every restart. jq's `//` picks the existing
# value if the key is already present (even if it's a non-empty object);
# only fills in this add-on's own option when the key is genuinely
# absent (first boot, or running standalone without ovos-core).
jq --argjson hw "$HOTWORDS" '. + {hotwords: (.hotwords // $hw)}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

(
  until (exec 3<>/dev/tcp/localhost/10400) 2>/dev/null; do sleep 0.5; done
  exec 3>&- 3<&- 2>/dev/null || true
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
