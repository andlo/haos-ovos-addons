#!/usr/bin/with-contenv bashio
EXTRA_PIP=$(bashio::config 'extra_pip_packages')

# OVOS_DEFAULT_LOG_LEVEL -- confirmed by reading ovos_utils/log.py directly:
# this env var (not the add-on's own log_level option by itself) is what
# ovos-core/ovos-messagebus's own Python logger respects. The `log_level`
# option was declared in config.yaml and shown in the UI but never actually
# wired anywhere in this script -- a real, silent no-op bug until now.
export OVOS_DEFAULT_LOG_LEVEL=$(bashio::config 'log_level' | tr '[:lower:]' '[:upper:]')

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

# Intent matcher choice, user-configurable -- see DOCS.md's "padatious
# vs padacioso" for the full investigation this option is built from.
# padatious is unconditionally instantiated (and trained in the
# background) by ovos-core's own IntentService whenever the package is
# merely importable, regardless of whether it's actually used in
# intents.pipeline (confirmed by reading __init__.py directly) -- so
# this has to control the actual INSTALL, not just which pipeline keys
# are active, or picking padacioso here wouldn't actually avoid
# padatious's memory cost.
INTENT_MATCHER=$(bashio::config 'intent_matcher')
mkdir -p /share/ovos-pip-cache
if [ "${INTENT_MATCHER}" = "padatious" ]; then
  bashio::log.info "Intent matcher: padatious (installing -- first restart after switching takes longer than normal)"
  pip install --cache-dir=/share/ovos-pip-cache --break-system-packages ovos-padatious \
    -c /etc/ovos-constraints-stable.txt
  PIPELINE='["stop_high","converse","ocp_high","padatious_high","adapt_high","ocp_medium","fallback_high","stop_medium","adapt_medium","padatious_medium","adapt_low","common_qa","fallback_medium","fallback_low"]'
else
  bashio::log.info "Intent matcher: padacioso (uninstalling padatious if present)"
  pip uninstall -y --break-system-packages ovos-padatious 2>/dev/null || true
  PIPELINE='["stop_high","converse","padacioso_high","adapt_high","common_qa","fallback_high","ocp_high","stop_medium","padacioso_medium","adapt_medium","fallback_medium","ocp_medium","padacioso_low","fallback_low"]'
fi

# disable_padacioso forced to false always -- confirmed by reading
# IntentService.__init__ directly: it defaults to True whenever
# padatious is importable "to save memory". Harmless when padatious is
# the active choice (padacioso just won't be in the pipeline list
# above, so it never gets exercised even though it's technically
# constructed), but required for padacioso to work at all when it's the
# active choice -- so simplest to always set it explicitly rather than
# branch on that too.
jq --argjson pipeline "${PIPELINE}" \
  '. + {intents: ((.intents // {}) + {disable_padacioso: false, pipeline: $pipeline})}' \
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

# Shared, content-addressed pip cache on /share -- safe across every
# add-on and every venv (keyed by package+version+hash, never a
# collision risk), unlike sharing an actual installation would be.
# Persists across rebuilds (unlike the add-on's own container
# filesystem), so a package already fetched by ANY add-on or any
# skill's own venv doesn't need re-downloading/re-building here again.
if [ -n "${EXTRA_PIP}" ]; then
  bashio::log.info "Installing extra pip packages: ${EXTRA_PIP}"
  pip install --cache-dir=/share/ovos-pip-cache --break-system-packages ${EXTRA_PIP} \
    -c /etc/ovos-constraints-stable.txt
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
