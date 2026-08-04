FROM ghcr.io/home-assistant/base:latest

# ovos-core: the actual skill runtime -- intent matching, skill manager,
# fallback-skill cascade. See DOCS.md for the full sandbox-spike writeup
# this recipe is copied from (OVOS's own official ovos-docker Dockerfile),
# including what's verified and what isn't.
#
# [lgpl,plugins] extras, not plain ovos-core: confirmed in the spike that
# [lgpl] is what pulls in Padatious (fann2-based intent matching) --
# ovos-skills' own Dockerfile installs plain ovos-core and never needed
# this, since it only installs/uninstalls skills, never runs them.
#
# Pinned via a build-time-frozen constraints file, not the live URL --
# fetched once here and baked into the image, so a future edit to OVOS's
# own constraints-alpha.txt upstream can't silently change what a rebuild
# installs. Still gives us OVOS's own coordinated version combination
# (confirmed clean via `pip check` in the sandbox spike), just frozen
# rather than floating -- same reasoning as pinning ovos-persona-server
# to an exact commit rather than chasing @dev (see ovos-persona/DOCS.md
# for what that cost us before we learned this lesson).
#
# fann-dev is in Alpine's "community" repo, not "main" -- confirmed via
# pkgs.alpinelinux.org, but NOT yet confirmed that a real `docker build`
# on this base image succeeds end-to-end (the sandbox spike ran on a
# Debian/Ubuntu sandbox, not Alpine -- see DOCS.md's "Not yet done" list).
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
