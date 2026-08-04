ARG BUILD_ARCH
FROM ghcr.io/home-assistant/${BUILD_ARCH}-base-debian:latest

# ovos-core: the actual skill runtime -- intent matching, skill manager,
# fallback-skill cascade. See DOCS.md for the full sandbox-spike writeup
# this recipe is copied from (OVOS's own official ovos-docker Dockerfile),
# including what's verified and what isn't.
#
# Debian base, NOT the Alpine base every other add-on in this project
# uses -- a deliberate, documented exception, not an oversight. Confirmed
# on real hardware: this exact ovos-core version, installed via this
# exact recipe, ran fine in an Ubuntu/Debian sandbox but hung
# indefinitely (never erroring, never responding) when built on Alpine
# for real Supervisor deployment. Compared directly against a known-good,
# 10-day-uptime production OVOS install (SSH-accessible, itself
# Debian-based) that answered correctly -- and OVOS's own official
# smartgic/ovos-core image is Debian-based too, never Alpine. See
# DOCS.md's "Alpine hang" section for the full investigation and why
# each other hypothesis (stale process, resource files, language,
# version drift, a hanging network-dependent pipeline matcher) was ruled
# out before landing on the base-OS/libc difference as the most likely
# cause. The other five add-ons stay on Alpine deliberately -- none of
# them carry ovos-core[lgpl]'s heavy C++/SWIG-compiled dependency
# (Padatious/fann2), the one specific piece of this puzzle with concrete
# evidence of musl-specific misbehavior.

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
# Package names here match Debian/Ubuntu exactly, confirmed working in
# the sandbox spike (which ran on the same base OS family) -- this is
# the one part of the whole recipe genuinely re-verified end-to-end, not
# adapted blind the way the Alpine names were.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv jq git curl \
      build-essential python3-dev swig libfann-dev pkg-config \
 && rm -rf /var/lib/apt/lists/* \
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
