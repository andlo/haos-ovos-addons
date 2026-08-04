#!/usr/bin/with-contenv bashio
EXTRA_PIP=$(bashio::config 'extra_pip_packages')

# Shared config, same convention as the other four add-ons.
export XDG_CONFIG_HOME=/share
CONF_DIR="/share/mycroft"
CONF_FILE="${CONF_DIR}/mycroft.conf"
mkdir -p "${CONF_DIR}"
[ -f "${CONF_FILE}" ] || echo '{}' > "${CONF_FILE}"

# CRITICAL, unlike ovos-skills' own private bus: this messagebus needs to
# be reachable from OTHER add-on containers (ovos-skills today, others
# later -- see DEVELOPER.md's shared-messagebus architecture). The
# messagebus library's own default host is 127.0.0.1 -- confirmed by
# ovos-skills never setting this (its bus is deliberately private, never
# needs to leave its own container). Explicitly bind 0.0.0.0 here, or no
# other container can ever reach this bus, no matter what ports.yaml says.
#
# NOT YET CONFIRMED ON REAL HARDWARE: the sandbox spike only tested the
# bus from within the same container/process, never a genuine
# container-to-container connection. First real test of that specifically
# is wiring ovos-skills to point at this shared bus instead of its own.
jq '. + {websocket: ((.websocket // {}) + {host: "0.0.0.0", port: 8181})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --no-cache-dir --break-system-packages ${EXTRA_PIP} \
    -c /etc/ovos-constraints-alpha.txt
fi

bashio::log.info "Starting shared ovos-messagebus on 0.0.0.0:8181"
ovos-messagebus &
MB_PID=$!

for i in $(seq 1 20); do
  (exec 3<>/dev/tcp/localhost/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
  sleep 0.5
done

# ovos-core's own first-boot startup takes ~90s in the sandbox spike --
# HuggingFace model downloads for the m2v/persona pipeline plugins, not a
# bug (see DOCS.md). Backgrounded here; api.py's own /health endpoint
# reports whether it's actually ready yet rather than blocking run.sh's
# own startup on it.
bashio::log.info "Starting ovos-core (first boot can take ~90s, see DOCS.md)"
ovos-core &

bashio::log.info "Starting synchronous Q&A API on :8500"
exec python3 /api.py
