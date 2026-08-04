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

# TEMPORARY DIAGNOSTIC, kept harmless: blacklisted these two during the
# "is it hanging on a network call" investigation (see DOCS.md's "The
# slow NUC" section -- it wasn't network, it was genuinely slow CPU-bound
# matching). Left blacklisted since neither is needed for this add-on's
# current scope (common-query and persona both need external services
# this add-on doesn't set up); revisit once that scope grows.
jq '. + {intents: ((.intents // {}) + {blacklisted_pipelines: ["ovos-common-query-pipeline-plugin", "ovos-persona-pipeline-plugin"]})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

# THE ACTUAL FIX for the real root cause (see DOCS.md's "The slow NUC"):
# padatious (ovos-core's default intent matcher) is a C++/SWIG-compiled,
# neural-network-trained matcher -- confirmed on this real NUC hardware
# to take 80-90+ seconds for a single simple utterance match, vs.
# near-instant on stronger hardware (sandbox, known-good VM). Nothing
# was ever hanging; it was genuinely, unusably slow on this specific
# weak hardware.
#
# padacioso is a lightweight, pure-Python drop-in replacement -- same
# .intent file format, same registration bus messages
# (padatious:register_intent etc., confirmed by reading its source
# directly), simple fuzzy-matching instead of a trained model. Already
# installed (a padacioso dependency of ovos-core[plugins] itself), but
# NOT in ovos-config's own default `intents.pipeline` list -- only
# padatious is there by default, so padacioso was never actually being
# used despite being present. Explicitly override the pipeline list here
# to use padacioso instead of padatious at every confidence tier.
jq '. + {intents: ((.intents // {}) + {pipeline: [
  "ovos-stop-pipeline-plugin-high",
  "ovos-converse-pipeline-plugin",
  "ovos-ocp-pipeline-plugin-high",
  "ovos-padacioso-pipeline-plugin",
  "ovos-adapt-pipeline-plugin-high",
  "ovos-m2v-pipeline-high",
  "ovos-ocp-pipeline-plugin-medium",
  "ovos-fallback-pipeline-plugin-high",
  "ovos-stop-pipeline-plugin-medium",
  "ovos-adapt-pipeline-plugin-medium",
  "ovos-fallback-pipeline-plugin-medium",
  "ovos-fallback-pipeline-plugin-low"
]})}' \
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
