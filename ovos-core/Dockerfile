FROM ghcr.io/home-assistant/base:latest

# ovos-core: the actual skill runtime -- intent matching, skill manager,
# fallback-skill cascade. See DOCS.md for the full investigation this
# recipe is built from (OVOS's own official ovos-docker Dockerfile as the
# starting point), including a genuinely twisty debugging trail: what
# looked like an infinite hang on Alpine turned out to be padatious
# (the default, C++/SWIG-compiled intent matcher) genuinely taking 80-90+
# seconds per match on this weak NUC hardware -- not an Alpine/musl bug
# at all. Confirmed by switching to Debian and reproducing the identical
# symptom there too. Back on Alpine now that the real fix (padacioso, a
# lightweight pure-Python matcher, configured in run.sh) is in place --
# matches every other add-on in this project, and HA's own docs prefer
# Alpine as the idiomatic default. See DOCS.md's "The investigation"
# section before assuming Alpine is ever the problem here again.
#
# [lgpl,plugins] extras, not plain ovos-core: confirmed in the spike that
# [lgpl] is what pulls in Padatious (fann2-based intent matching) --
# ovos-skills' own Dockerfile installs plain ovos-core and never needed
# this, since it only installs/uninstalls skills, never runs them. Still
# needed even though padacioso is the active matcher now: padatious
# stays installed (unused, blacklisted only implicitly by not being in
# intents.pipeline), and other [plugins]-extra pipelines (m2v, ocp,
# adapt, etc.) are genuinely used.
#
# Pinned via a build-time-frozen constraints file, not the live URL --
# fetched once here and baked into the image, so a future edit to OVOS's
# own constraints-alpha.txt upstream can't silently change what a rebuild
# installs. Still gives us OVOS's own coordinated version combination
# (confirmed clean via `pip check`), just frozen rather than floating --
# same reasoning as pinning ovos-persona-server to an exact commit rather
# than chasing @dev (see ovos-persona/DOCS.md for what that cost us
# before we learned this lesson).
#
# fann-dev is in Alpine's "community" repo, not "main" -- confirmed via
# pkgs.alpinelinux.org. Confirmed for real this time (not just reasoned):
# this exact recipe, on this exact base image, builds cleanly and
# ovos-core starts and answers correctly once padacioso is configured as
# the active matcher.
RUN apk add --no-cache python3 py3-pip jq git curl \
      build-base python3-dev swig fann-dev pkgconf \
 && curl -fsSL "https://raw.githubusercontent.com/OpenVoiceOS/ovos-releases/refs/heads/main/constraints-alpha.txt" \
      -o /etc/ovos-constraints-alpha.txt \
 && pip install --no-cache-dir --break-system-packages --pre \
      bitstruct "ovos-core[lgpl,plugins]" ovos-skill-boot-finished ovos-messagebus \
      fastapi uvicorn ovos-bus-client \
      -c /etc/ovos-constraints-alpha.txt

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
