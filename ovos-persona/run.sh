#!/usr/bin/with-contenv bashio
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
SOLVER_CONFIG=$(bashio::config 'solver_config')

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

# persona.json (solver list) stays add-on-private, not shared with the
# other three add-ons — but sess.lang and other session defaults still
# come from ovos-config's Configuration(), so point that at the same
# shared mycroft.conf the others read/write, in case lang/location was
# set there (via a future ha-ovos-integration or another add-on).
export XDG_CONFIG_HOME=/share
mkdir -p /share/mycroft
[ -f /share/mycroft/mycroft.conf ] || echo '{}' > /share/mycroft/mycroft.conf

# bashio config arrays -> newline separated, turn into a JSON array
SOLVERS_JSON=$(bashio::config 'solvers' | jq -R . | jq -s .)

jq -n \
  --arg name "assist_persona" \
  --argjson solvers "$SOLVERS_JSON" \
  --argjson conf "$SOLVER_CONFIG" \
  '{name: $name, solvers: $solvers} * $conf' \
  > /persona.json

# api.py's own lifespan handler launches ovos-persona-server itself
# (subprocess.Popen, not exec) -- so it can also RESTART it whenever
# ha-ovos-integration writes a new persona.json via PUT /settings,
# something a plain `exec` here could never do (a replaced process
# can't be relaunched by anything downstream of it).
bashio::log.info "Starting ovos-persona-server on :8337, bridged via api.py on :8338"
exec python3 /api.py
