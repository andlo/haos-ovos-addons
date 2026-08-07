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
# fann-dev is in Alpine's "community" repo, not "main" -- confirmed via
# pkgs.alpinelinux.org. Confirmed for real this time (not just reasoned):
# this exact recipe, on this exact base image, builds cleanly and
# ovos-core starts and answers correctly once padacioso is configured as
# the active matcher.
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

# padatious UNINSTALLED, not just left unused in intents.pipeline --
# confirmed on real hardware this was needed, not just cosmetic:
# ovos-core's own SkillManager runs "Requesting padatious intent
# training" for every skill regardless of whether padatious is actually
# in the active pipeline (it's unconditionally instantiated in
# IntentService.__init__ whenever the package is importable), and on
# this weak NUC that background training genuinely contends for CPU with
# padacioso's own matching -- confirmed via `docker stats` showing
# padacioso match times varying from ~8s to 22+s (sometimes past
# api.py's own timeout) depending on whether training happened to be
# running concurrently, plus real "dictionary changed size during
# iteration" training-race errors in the logs, from a package we never
# wanted matching anything in the first place. ovos-core's own
# IntentService gracefully handles this via a plain try/except
# ImportError around the padatious import (confirmed by reading
# __init__.py directly) -- uninstalling it is the supported way to opt
# out, not a workaround.

COPY api.py /api.py
COPY run.sh /
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
