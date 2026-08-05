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
# later -- see DEVELOPER.md's shared-messagebus architecture).
#
# NOT "0.0.0.0": confirmed by reading ovos-messagebus/ovos-skill-installer/
# ovos-skill-launcher source directly, all three read this SAME shared
# key via Configuration() with no override mechanism -- there is no way
# to give ovos-core's own bind address a different value from what every
# other container reads as the CONNECT address, since it's the same file.
# "0.0.0.0" is a valid bind address but a meaningless connect target for
# a remote container. Using this add-on's own real hostname instead --
# testing the hypothesis that binding to your own resolvable hostname
# (not just 0.0.0.0) still works and IS externally reachable, since it's
# the only value that can be simultaneously correct for both purposes.
# NOT YET CONFIRMED — this is the first real test of it.
jq '. + {websocket: ((.websocket // {}) + {host: "b8e040e3-ovos-core", port: 8181})}' \
  "${CONF_FILE}" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "${CONF_FILE}"

# ovos-common-query-pipeline-plugin RE-ENABLED -- the original
# blacklist reasoning ("needs external services this add-on doesn't set
# up") turned out to be wrong for this one: confirmed by reading
# ovos_commonqa/opm.py's own source, it uses its own bus messages
# (ovos.common_query.ping, common_query.question/response), answered
# via ordinary speak_dialog by any installed "CommonQuerySkill" (e.g.
# Wikipedia) -- the exact same mechanism already confirmed working for
# weather/date-time via /ask. No external audio service needed, unlike
# OCP-based media skills (see ovos-skills' own CURATED_CATALOG entry for
# skill-ovos-news, which DOES need one and stays excluded). Likely just
# blacklisted broadly, alongside persona, during the original "is it
# hanging" investigation to cut noise, not for a real technical reason.
#
# ovos-persona-pipeline-plugin STAYS blacklisted -- this project already
# has its own, separate persona bridge (see ovos-persona's own add-on
# and DEVELOPER.md); this in-core pipeline plugin is a different,
# redundant mechanism, not evaluated, left off deliberately.
jq '. + {intents: ((.intents // {}) + {blacklisted_pipelines: ["ovos-persona-pipeline-plugin"]})}' \
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
  "ovos-common-query-pipeline-plugin",
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

bashio::log.info "Starting shared ovos-messagebus on b8e040e3-ovos-core:8181"
ovos-messagebus &
MB_PID=$!

# Checking the own hostname, not localhost -- if binding to the specific
# hostname (not 0.0.0.0) means it no longer also listens on loopback,
# checking localhost here would give a false negative even if the bus
# started fine on its real bind address.
for i in $(seq 1 20); do
  (exec 3<>/dev/tcp/b8e040e3-ovos-core/8181) 2>/dev/null && { exec 3>&- 3<&-; break; }
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
