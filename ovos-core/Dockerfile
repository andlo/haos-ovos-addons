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
# own constraints-stable.txt upstream can't silently change what a rebuild
# installs. Still gives us OVOS's own coordinated version combination
# (confirmed clean via `pip check`), just frozen rather than floating --
# same reasoning as pinning ovos-persona-server to an exact commit rather
# than chasing @dev (see ovos-persona/DOCS.md for what that cost us
# before we learned this lesson).
#
# STABLE channel, not alpha -- deliberate switch. OVOS documents three
# channels (stable/testing/alpha); alpha is explicitly "bleeding edge,
# may break." Confirmed for real this session: a newer, still-alpha
# ovos-utils (>=0.11.0a1) pulls in ovos-spec-tools, whose session
# validator logs a warning on every session sync because
# ovos-bus-client's own Session.serialize() always includes
# "persona_id": null rather than omitting it when unset -- a genuine,
# reproducible incompatibility between two official OVOS packages that
# hasn't been reconciled yet. Real, if noisy, and a plausible contributor
# to slow/failed responses under this stack. Stable channel sidesteps it
# entirely for now, since that ovos-utils pairing isn't promoted there
# yet. --pre dropped too -- no reason to allow prereleases once pinned
# to the stable constraints file. Revisit alpha/testing as a deliberate,
# separate build once this is confirmed stable, not as the default.
#
# padatious RESOLVED, this time with a real, confirmed root cause --
# reinstalling padatious to test it as OVOS's own official default (see
# the previous commit's reasoning) reproduced a genuine
# `Fatal Python error: Segmentation fault` on real hardware, not just
# slowness. Confirmed the actual cause directly: `free -h` showed 344MB
# free / swap 92% full at the time, and `dmesg` showed a real OOM-kill
# already in progress (a different process, but confirming the host was
# genuinely memory-starved). padatious's dependency stack (numpy, scipy,
# sklearn, fann2, all loaded together) is memory-heavy; under real
# memory pressure a malloc deep in a C extension fails and segfaults
# instead of raising a clean Python MemoryError. This is NOT the same
# claim as before ("padatious is just slow on weak CPUs") -- confirmed
# AVX2 IS present on this CPU (`/proc/cpuinfo` checked directly), ruling
# out the instruction-set theory. The real difference from raspOVOS/
# Mark2 hardware isn't CPU strength, it's that THIS host is also running
# ~30 other add-on containers simultaneously, competing for the same
# limited RAM -- padatious being memory-heavy makes it the one that
# breaks first under that specific pressure, not evidence it's wrong on
# weaker-but-dedicated hardware. padacioso stays the right choice HERE,
# for a documented, verified reason instead of an assumed one.
RUN apk add --no-cache python3 py3-pip jq git curl \
      build-base python3-dev swig fann-dev pkgconf \
 && curl -fsSL "https://raw.githubusercontent.com/OpenVoiceOS/ovos-releases/refs/heads/main/constraints-stable.txt" \
      -o /etc/ovos-constraints-stable.txt \
 && pip install --no-cache-dir --break-system-packages \
      "setuptools<=80.9.0" \
      bitstruct "ovos-core[lgpl,plugins]" ovos-skill-boot-finished ovos-messagebus \
      fastapi uvicorn ovos-bus-client \
      -c /etc/ovos-constraints-stable.txt \
 && pip uninstall -y --break-system-packages ovos-padatious

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
