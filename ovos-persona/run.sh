#!/usr/bin/with-contenv bashio
EXTRA_PIP=$(bashio::config 'extra_pip_packages')
SOLVER_CONFIG=$(bashio::config 'solver_config')

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP}
fi

# bashio config arrays -> newline separated, turn into a JSON array
SOLVERS_JSON=$(bashio::config 'solvers' | jq -R . | jq -s .)

jq -n \
  --arg name "assist_persona" \
  --argjson solvers "$SOLVERS_JSON" \
  --argjson conf "$SOLVER_CONFIG" \
  '{name: $name, solvers: $solvers} * $conf' \
  > /persona.json

bashio::log.info "Starting ovos-persona-server on :8337"
exec ovos-persona-server --persona /persona.json
