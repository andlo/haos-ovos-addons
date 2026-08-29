"""HTTP-to-messagebus bridge for OVOS skill install/uninstall -- one
isolated Python venv per skill.

WHY: a single, shared site-packages for every skill meant one skill's
own dependency requirements could silently break another skill, or
ovos-core itself -- confirmed for real, same night this was built:
installing skill-ovos-wolfie pulled in a newer ovos-workshop that
ovos-core and ovos-skill-dictation are NOT compatible with, corrupting
the shared environment for everything, not just wolfie. A per-skill
venv makes this structurally impossible: each skill's own dependency
tree lives in total isolation from every other skill and from
ovos-core itself.

This also sidesteps, for free, the importlib.metadata-in-a-long-running-
process unreliability the previous version of this file spent a long
investigation chasing (see git history around that same night) -- there
is no shared site-packages left to scan; the manifest file below IS the
source of truth for what's installed, always read fresh off disk.

PERSISTENCE MODEL: venvs themselves are NOT persisted to /share -- they
live in this container's own filesystem layer, which does NOT survive
an add-on rebuild/update (same fact this file has always documented).
Only a small manifest.json (skill_id -> source URL + real package name)
is persisted; on every container start, every venv is rebuilt from
scratch by re-running the same install logic for each manifest entry.
A fresh git clone + pip install per skill at every restart is a
deliberate, accepted cost -- far simpler and more robust than the old
file-copy persistence mechanism (a PERSIST_DIR of copied package
files), which had its own reliability problems (RECORD file loss,
importlib.metadata blind spots). settings.json is unaffected by any of
this -- it already lived on /share via XDG_CONFIG_HOME, keyed by
skill_id, independent of where the skill's own code lives.

Talks to ovos-core's own SkillsStore (ovos_core.skill_installer) for
NOTHING anymore -- confirmed unreliable for install (the "error in pip
subprocess" job-status false negatives) same as it already was for
uninstall (see the old _direct_pip_uninstall's docstring, now removed
along with the messagebus dependency itself).

Bus connectivity was fully removed at that point -- reversed, deliberately
and narrowly, for ONE feature: enabling/disabling a skill without
uninstalling it (skillmanager.activate/deactivate -- see
_set_skill_active's own docstring for why this needs the bus at all,
and why the old, entirely bus-free design couldn't offer it). Every
other endpoint in this file is unaffected and stays exactly as
bus-free as before; this is a short-lived, throwaway connection per
call (the same connect/send/close shape _broadcast_ready_signal
already used successfully elsewhere in this file), not a persistent
connection reintroducing whatever reliability concerns the original
removal was about.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel

LOG = logging.getLogger("ovos-skills-api")

# Inside the container's OWN filesystem, deliberately NOT on /share --
# see module docstring's "PERSISTENCE MODEL".
VENV_ROOT = "/opt/skill-venvs"

# The ONLY thing persisted for reinstall purposes: skill_id -> {source,
# package_name}. Small, human-readable, and enough to fully reconstruct
# every venv from scratch.
MANIFEST_PATH = "/share/ovos-skills/manifest.json"

# Persists the DESIRED active/inactive state per skill_id across
# restarts -- confirmed necessary by reading ovos_workshop's own
# skill_launcher.py directly: each skill's own SkillLoader instance
# (one per subprocess, launched fresh by SkillProcessManager.launch()
# below on every container start) initializes self.active = True
# unconditionally in its own __init__, with no persistence of its own.
# Without this file, a skill someone deactivated would silently come
# back active on the next restart/rebuild.
ACTIVE_STATE_PATH = "/share/ovos-skills/active_state.json"

INSTALL_TIMEOUT = 300  # venv create + pip install -- a slow git clone +
                        # dependency resolve is realistic, not a hang

# A small, CURATED catalog -- not the official OVOS skills-store feed
# anymore. Confirmed for real, this session: several "obviously core"
# OVOS skills assume a full, standalone OVOS install with its own audio
# subsystem and continuous wake-word listener, neither of which exists
# in this project's architecture (a synchronous /ask bridge into
# ovos-core). ovos-skill-volume and ovos-skill-naptime were both
# confirmed, by reading their own source, to rely on PHAL plugins
# ("mycroft.volume.set" etc.) this setup has nothing listening for --
# they'd load without error but silently do nothing, which is worse
# than not offering them at all. Every skill in catalog.json was
# individually checked the same way before being added. Anything not
# vetted yet belongs in the separate ovos-skills-extra add-on instead
# (see its own DOCS.md), not here -- this list stays trustworthy by
# only ever growing through the same verification, never by
# convenience.
#
# Lives in its own catalog.json file, not hardcoded here -- deliberate:
# keeps this add-on's own PURE DATA (which skills, in/out of the
# default set) separate from its code, editable without touching
# Python, and matches the "the store" framing directly (a JSON file
# really is just a small store listing).
#
# "default" entries are installed automatically on this add-on's very
# first-ever boot (see _seed_default_skills_if_first_boot) -- a small,
# sensible baseline so there's something useful from the start, the
# same idea ovos-installer's own default skill set follows. Everything
# else here is opt-in via the catalog UI, same as before.
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")


def _read_catalog() -> list[dict]:
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        LOG.error(f"Could not read catalog.json: {exc}")
        return []

# Marker file, NOT "is the manifest empty" -- deliberately survives a
# person later uninstalling a default skill on purpose. Seeding only
# ever happens once, on this add-on's genuinely first-ever boot.
DEFAULTS_SEEDED_MARKER = "/share/ovos-skills/.defaults-seeded"

jobs: dict[str, dict] = {}  # key: url (install) or skill_id (uninstall)


def _read_manifest() -> dict:
    if not os.path.isfile(MANIFEST_PATH):
        return {}
    try:
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_manifest(manifest: dict) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp, MANIFEST_PATH)  # atomic


def _read_active_state() -> dict:
    """{skill_id: bool}. A skill_id absent here means active (the
    default) -- only ever written when someone explicitly deactivates
    a skill, so the file stays empty/small on a normal system where
    nothing's been turned off.
    """
    if not os.path.isfile(ACTIVE_STATE_PATH):
        return {}
    try:
        with open(ACTIVE_STATE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_active_state(state: dict) -> None:
    os.makedirs(os.path.dirname(ACTIVE_STATE_PATH), exist_ok=True)
    tmp = ACTIVE_STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, ACTIVE_STATE_PATH)


def _is_skill_active(skill_id: str) -> bool:
    return _read_active_state().get(skill_id, True)


def _send_activate_message(skill_id: str, active: bool) -> None:
    """skillmanager.activate/deactivate, sent directly on the shared
    bus -- confirmed by reading ovos_workshop's own skill_launcher.py
    directly: EACH skill's own SkillLoader instance (one per
    subprocess, since this project launches one isolated venv/process
    per skill -- see SkillProcessManager below) registers its OWN bus
    listener for these exact message types, filtered by
    message.data['skill'] == self.skill_id, entirely independent of
    ovos-core's own SkillManager (which has no visibility into these
    subprocess-launched skills at all -- see _broadcast_ready_signal's
    own docstring for the same, already-established limitation). This
    is what makes it safe to send this directly rather than needing
    ovos-core to be involved: the RIGHT skill's own process reacts to
    it, and no other skill's process does (confirmed: do_load/do_unload
    both check the skill id before doing anything).

    Short-lived connect/send/close, same shape as
    _broadcast_ready_signal -- not a persistent bus connection.
    """
    try:
        from ovos_bus_client import MessageBusClient
        from ovos_bus_client.message import Message
        bus = MessageBusClient()
        bus.run_in_thread()
        bus.connected_event.wait(timeout=10)
        msg_type = "skillmanager.activate" if active else "skillmanager.deactivate"
        bus.emit(Message(msg_type, data={"skill": skill_id}))
    except Exception as exc:
        LOG.warning(f"Could not send {('activate' if active else 'deactivate')} for {skill_id}: {exc}")
        return
    # Separate try/except: confirmed for real that bus.close() itself
    # can raise ('NoneType' object has no attribute 'close_frame',
    # from ovos_bus_client's own underlying websocket-client library)
    # AFTER the emit above already succeeded and the target skill's
    # own process already reacted correctly (confirmed via its own
    # log: "reloading skill" / "loaded successfully") -- a cleanup-
    # only failure, not a sign the message itself didn't go through.
    # Logging it under the same "Could not send" message as an actual
    # send failure would be actively misleading.
    try:
        bus.close()
    except Exception as exc:
        LOG.debug(f"Non-fatal: bus.close() raised after a successful {msg_type} for {skill_id}: {exc}")


def _set_skill_active(skill_id: str, active: bool) -> None:
    state = _read_active_state()
    if active:
        state.pop(skill_id, None)  # absent == active, keep the file minimal
    else:
        state[skill_id] = False
    _write_active_state(state)
    _send_activate_message(skill_id, active)


def _reapply_active_state_after_delay(skill_id: str, delay: float = 5.0) -> None:
    """Runs in a background thread right after a skill is launched --
    a freshly launched skill's own SkillLoader always starts with
    self.active = True (see ACTIVE_STATE_PATH's own comment for why),
    so a previously-deactivated skill needs deactivating again after
    each restart. The delay gives the skill's own _connect_to_core()
    time to actually register its skillmanager.deactivate listener
    before this fires -- same reasoning and same delay as
    _broadcast_ready_after_delay elsewhere in this file. A no-op for
    any skill that was never deactivated (the common case).
    """
    if _is_skill_active(skill_id):
        return
    time.sleep(delay)
    LOG.info(f"Re-applying deactivated state for {skill_id} after (re)launch")
    _send_activate_message(skill_id, False)


def _venv_dir(skill_id: str) -> str:
    # skill_id is already a safe dotted string (e.g.
    # "skill-ovos-alerts.openvoiceos"), but normalize defensively --
    # this becomes a real directory name.
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", skill_id)
    return os.path.join(VENV_ROOT, safe)


_ENTRY_POINTS_SCRIPT = """
import importlib.metadata, json
result = []
for group in ("opm.skill", "ovos.plugin.skill"):
    for ep in importlib.metadata.entry_points(group=group):
        result.append({"skill_id": ep.name, "package_name": ep.dist.name if ep.dist else ep.name})
print(json.dumps(result))
"""


def _create_venv(venv_dir: str) -> tuple[bool, str]:
    """Uses `virtualenv`, not the stdlib venv module -- see Dockerfile's
    comment for why (more reliable ensurepip bootstrapping on Alpine).
    """
    if os.path.isdir(venv_dir):
        shutil.rmtree(venv_dir)  # stale/partial venv from a failed attempt
    try:
        subprocess.run(
            ["virtualenv", venv_dir],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return True, ""
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or "venv creation failed").strip()
    except subprocess.TimeoutExpired:
        return False, "venv creation timed out"


_ARCHIVE_EXTENSIONS = (".whl", ".tar.gz", ".zip", ".tar.bz2")


def _pip_installable(source: str) -> str:
    """A bare repo URL (e.g. "https://github.com/OpenVoiceOS/skill-x",
    the catalog's own "source" field convention) is NOT directly
    pip-installable -- pip treats a plain https:// URL as a direct
    archive download, and a GitHub repo *page* URL returns HTML, not an
    archive ("Cannot determine archive format", confirmed for real).
    Needs the "git+" scheme prefix so pip clones it as a VCS source
    instead. Left alone if it's already prefixed, already a recognized
    archive URL, or looks like a plain PyPI package name (no scheme at
    all).
    """
    if source.startswith(("git+", "git@")) or "://" not in source:
        return source
    if source.endswith(_ARCHIVE_EXTENSIONS):
        return source
    return f"git+{source}"


def _repo_name_from_git_url(source: str) -> str | None:
    """Derive a likely PyPI package name from a repo URL -- e.g.
    "https://github.com/OpenVoiceOS/ovos-skill-alerts" ->
    "ovos-skill-alerts". Only ever used as a CANDIDATE to check against
    PyPI directly (_pypi_package_exists) -- never assumed correct on
    its own, since a repo name matching a PyPI name isn't guaranteed
    (confirmed elsewhere in this project: module names and real package
    names, or catalog skill_ids and real runtime skill_ids, have both
    been found to mismatch before).
    """
    if not source.startswith(("http://", "https://")):
        return None
    name = source.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or None


def _pypi_package_exists(pip_bin: str, name: str) -> bool:
    """Confirms `name` is a real, installable PyPI package via `pip
    index versions` -- not assumed from the repo name alone. `pip
    index` is marked experimental by pip itself but has been reliable
    in practice throughout this project; only the return code is
    trusted here, not its (occasionally noisy) output.
    """
    try:
        result = subprocess.run(
            [pip_bin, "index", "versions", name],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _resolve_install_target(pip_bin: str, source: str) -> str:
    """Prefer a real, published PyPI package over a git URL when one
    exists under the repo's own name.

    Confirmed for real, this session: git-installing a skill pulls
    whatever's on its default branch, which is often a pre-release --
    e.g. ovos-skill-alerts installed as 0.2.2a2 via git, while PyPI's
    latest stable release was 0.1.28; ovos-skill-date-time similarly
    (1.1.14a2 vs PyPI's 1.1.5). The official skills catalog's own
    "source" field is git-URL-only by convention -- not something we
    chose -- so without this check every skill installed through it
    would default to an alpha/dev version even when a tested, versioned
    release is available. Falls back to the git source unchanged when
    no matching PyPI package is confirmed to exist -- never assumes a
    derived name is correct without checking (see
    _repo_name_from_git_url's own docstring for why).
    """
    candidate = _repo_name_from_git_url(source)
    if candidate and _pypi_package_exists(pip_bin, candidate):
        LOG.info(f"Preferring PyPI package '{candidate}' over git source {source}")
        return candidate
    return source


# Pre-installed into every fresh venv, before the skill's own package --
# confirmed for real, this session: many OVOS skills (and even
# ovos-workshop itself, in some versions) don't declare their own real
# runtime dependencies correctly, silently relying on a full, shared
# OVOS environment already being present the classic way (the same
# model venv-per-skill deliberately moved away from). Confirmed
# directly: ovos-workshop 7.0.6's own declared Requires list omits
# ovos-plugin-manager entirely, even though ovos_workshop.skills.ovos
# imports from it directly -- the exact cause of skill-ovos-stop's
# ModuleNotFoundError (see DEVELOPER.md / issue #1). Installing these
# unpinned (latest) first, then the skill's own package, does NOT
# reintroduce the version-conflict risk venv-per-skill was built to
# eliminate: each skill still gets its own, fully isolated venv, and
# pip's own dependency resolver correctly upgrades/downgrades this
# baseline afterward if the skill's own package declares a real,
# stricter requirement -- this is just a better default starting point
# within that same isolated venv, not a shared, forced version.
BASELINE_PACKAGES = ["ovos-workshop", "ovos-plugin-manager", "setuptools<=80.9.0",
                      "ovos-rake-keyword-extractor"]
# setuptools added after a third, same-class failure confirmed for
# real: ovos_plugin_manager's own code does "import pkg_resources"
# internally, which newer setuptools versions no longer bundle by
# default in a fresh venv -- same "assumes a full, shared OVOS
# environment already has this" pattern as the ovos-plugin-manager gap
# itself. PINNED, not just added unpinned -- confirmed directly (wheel
# inspection): setuptools 83.0.0 (latest) ships zero pkg_resources
# files, 80.9.0 ships 19. An earlier, unpinned attempt installed
# whatever was newest and still failed with the exact same error --
# same version ceiling this project's own Dockerfiles already use for
# the same reason.
#
# Root cause reported upstream, not just worked around here:
# ovos-plugin-manager's own pkg_resources fallback (used when the
# external importlib_metadata backport isn't installed) is what
# actually raises ModuleNotFoundError -- PR filed proposing stdlib
# importlib.metadata instead (no fallback needed, their own
# python_requires>=3.10 already covers it):
# https://github.com/OpenVoiceOS/ovos-plugin-manager/pull/426
# This pin stays regardless of that PR's outcome -- still needed for
# any already-published ovos-plugin-manager release in the meantime.
#
# ovos-rake-keyword-extractor added after a fourth, same-class failure
# confirmed for real during 0.1.0 integration testing: ovos-skill-ddg
# and ovos-skill-wikihow both silently answer nothing to every query,
# each logging "Could not find the plugin
# PluginTypes.KEYWORD_EXTRACTION.ovos-rake-keyword-extractor" -- both
# assume this plugin is already present in a full, shared OVOS
# environment (same pattern as the ovos-plugin-manager gap above), and
# neither declares it as a real dependency of their own. Same fix
# shape: added here once, benefits every skill's venv, not just these
# two. See haos-ovos-addons issue #9.


def _venv_pip_install_baseline(venv_dir: str) -> None:
    pip_bin = os.path.join(venv_dir, "bin", "pip")
    try:
        subprocess.run(
            [pip_bin, "install", "--no-input", "--cache-dir=/share/ovos-pip-cache", *BASELINE_PACKAGES],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        LOG.warning(f"Baseline package install timed out for {venv_dir} -- continuing anyway")
    # Failure here is deliberately non-fatal: worst case, a skill falls
    # back to needing its own complete, correct dependency declaration,
    # exactly like before this existed -- not a new way to fail.


def _extra_deps_for_source(source: str) -> list[str]:
    """Per-skill extra dependencies, from catalog.json's own optional
    "extra_deps" field -- for the rarer case where only ONE skill needs
    an extra package, unlike BASELINE_PACKAGES (installed into every
    venv regardless). Matched against catalog entries by package_name
    OR source, since `source` here can be either depending on caller
    (a bare package_name during default-seeding/reinstall, or a raw git
    URL for a manually-installed skill not in the catalog at all --
    that case simply matches nothing and returns []).

    Added for ovos-skill-wikipedia: its own __init__ unconditionally
    constructs a WikipediaSolver(translator=self.translator, ...), and
    accessing self.translator raises when no translate plugin is
    installed -- confirmed for real, this session: the raise happens
    INSIDE __init__ before `self.wiki = ...` completes, so every query
    afterward hits AttributeError: 'WikipediaSkill' object has no
    attribute 'wiki'. Same "assumes a full, shared OVOS environment"
    pattern as the BASELINE_PACKAGES gaps, but skill-specific enough
    (only wikipedia needs a translator) that adding it to every venv
    via BASELINE_PACKAGES would be unnecessary weight for the other
    eight. See haos-ovos-addons issue #10.
    """
    for item in _read_catalog():
        if source in (item.get("package_name"), item.get("source")):
            return item.get("extra_deps", [])
    return []


def _venv_pip_install_extra_deps(venv_dir: str, source: str) -> None:
    extra = _extra_deps_for_source(source)
    if not extra:
        return
    pip_bin = os.path.join(venv_dir, "bin", "pip")
    try:
        subprocess.run(
            [pip_bin, "install", "--no-input", "--cache-dir=/share/ovos-pip-cache", *extra],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        LOG.warning(f"Extra deps install timed out for {venv_dir} ({extra}) -- continuing anyway")
    # Same deliberately-non-fatal reasoning as the baseline install.


def _venv_pip_install(venv_dir: str, source: str) -> tuple[bool, str]:
    pip_bin = os.path.join(venv_dir, "bin", "pip")
    target = _pip_installable(source)
    try:
        result = subprocess.run(
            [pip_bin, "install", "--no-input", "--cache-dir=/share/ovos-pip-cache", target],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "pip install timed out"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "pip install failed").strip()
    return True, result.stdout


def _rewrite_venv_shebangs(venv_dir: str, old_prefix: str, new_prefix: str) -> None:
    """After moving a venv from old_prefix to new_prefix, its own
    console_scripts (e.g. ovos-skill-launcher, generated by pip AT
    INSTALL TIME with a hardcoded, absolute shebang line pointing at
    wherever pip was run from) still reference the now-gone old path --
    confirmed for real: re-running `virtualenv <path>` on the moved venv
    does NOT reliably fix this, since that only repairs virtualenv's own
    core files (pip, activate, the python symlink), not arbitrary
    third-party scripts pip generated afterward. Rewriting the path
    directly in each bin/ script's own text is simpler and actually
    reliable -- these are small, plain-text files, not binaries.
    """
    bin_dir = os.path.join(venv_dir, "bin")
    if not os.path.isdir(bin_dir):
        return
    old_bytes = old_prefix.encode()
    new_bytes = new_prefix.encode()
    for name in os.listdir(bin_dir):
        path = os.path.join(bin_dir, name)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if old_bytes not in data:
            continue
        try:
            data.decode("utf-8")  # binaries fail here -- skip them
        except UnicodeDecodeError:
            continue
        with open(path, "wb") as f:
            f.write(data.replace(old_bytes, new_bytes))


def _venv_discover_skill(venv_dir: str) -> list[dict]:
    """Every skill entry_point visible in THIS venv -- normally just the
    one skill just installed, since each venv is fresh and isolated.
    A fresh subprocess against this specific venv's own interpreter,
    same reasoning the rest of this project already established for
    avoiding importlib.metadata staleness in a long-running process --
    except here there's no long-running-process risk at all, since this
    runs once, immediately after install.
    """
    python_bin = os.path.join(venv_dir, "bin", "python")
    try:
        raw = subprocess.check_output(
            [python_bin, "-c", _ENTRY_POINTS_SCRIPT],
            text=True, stderr=subprocess.STDOUT, timeout=30,
        )
        return json.loads(raw)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        LOG.error(f"entry_points discovery failed in {venv_dir}: {exc}")
        return []


def _pip_show_files(venv_dir: str, package_name: str) -> tuple[str, list[str]] | None:
    """(site-packages location, [file paths relative to it]) for a
    package installed in a SPECIFIC skill's own venv, via that venv's
    own `pip show -f` -- not importlib.metadata, and not the main
    container's own pip (which has no visibility into a venv it didn't
    create the process from).
    """
    pip_bin = os.path.join(venv_dir, "bin", "pip")
    try:
        raw = subprocess.check_output(
            [pip_bin, "show", "-f", package_name],
            text=True, stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return None

    location = None
    files: list[str] = []
    in_files = False
    for line in raw.splitlines():
        if line.startswith("Location:"):
            location = line.split(":", 1)[1].strip()
        elif line.startswith("Files:"):
            in_files = True
        elif in_files and line.startswith("  "):
            files.append(line.strip())
        elif in_files:
            in_files = False

    return (location, files) if location is not None else None


def _venv_pip_show_version(venv_dir: str, package_name: str) -> str | None:
    pip_bin = os.path.join(venv_dir, "bin", "pip")
    try:
        raw = subprocess.check_output(
            [pip_bin, "show", package_name], text=True, stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return None
    for line in raw.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


def _install_skill_into_venv(source: str) -> dict | None:
    """Full install flow: fresh venv, pip install, discover the actual
    skill_id it registers. Returns {"skill_id", "package_name"} on
    success, None on failure.

    Uses a temp dir first, discovers the real skill_id, THEN moves into
    its final, name-keyed location -- the skill_id isn't known until
    after install completes (the catalog's own skill_id is trusted for
    display purposes only; this is the confirmed-real one).
    """
    tmp_dir = os.path.join(VENV_ROOT, f".tmp-{os.getpid()}-{int(time.time() * 1000)}")
    ok, err = _create_venv(tmp_dir)
    if not ok:
        LOG.error(f"venv creation failed for {source}: {err}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    _venv_pip_install_baseline(tmp_dir)
    _venv_pip_install_extra_deps(tmp_dir, source)

    install_target = _resolve_install_target(os.path.join(tmp_dir, "bin", "pip"), source)

    ok, err = _venv_pip_install(tmp_dir, install_target)
    if not ok:
        LOG.error(f"pip install failed for {install_target}: {err}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    entries = _venv_discover_skill(tmp_dir)
    if not entries:
        LOG.error(f"No skill entry_point found after installing {install_target}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    chosen = entries[0]
    if len(entries) > 1:
        LOG.warning(
            f"{install_target} registered {len(entries)} skill entry_points, "
            f"using {chosen['skill_id']} (first)"
        )

    skill_id = chosen["skill_id"]
    final_dir = _venv_dir(skill_id)
    if os.path.isdir(final_dir):
        shutil.rmtree(final_dir)  # reinstall/upgrade case
    shutil.move(tmp_dir, final_dir)
    _rewrite_venv_shebangs(final_dir, tmp_dir, final_dir)

    # install_target, not the original source -- so the manifest (and
    # therefore every future rebuild-on-restart) remembers the
    # PyPI-preferred choice made here, rather than re-resolving it every
    # time or silently reverting to the git source.
    return {"skill_id": skill_id, "package_name": chosen["package_name"], "source": install_target}


def _rebuild_all_venvs_from_manifest():
    """On every container start, every skill's venv must be rebuilt from
    scratch -- venvs are NOT persisted (see module docstring). Runs
    synchronously, before discover_and_launch_all(), since launch()
    needs each venv's own ovos-skill-launcher to already exist on disk.
    """
    manifest = _read_manifest()
    for skill_id, entry in manifest.items():
        venv_dir = _venv_dir(skill_id)
        if os.path.isfile(os.path.join(venv_dir, "bin", "ovos-skill-launcher")):
            continue  # already present -- shouldn't normally happen on
                       # a genuinely fresh container, but cheap to check
        LOG.info(f"Rebuilding venv for {skill_id} from {entry['source']}")
        ok, err = _create_venv(venv_dir)
        if not ok:
            LOG.error(f"Failed to rebuild venv for {skill_id}: {err}")
            continue
        _venv_pip_install_baseline(venv_dir)
        _venv_pip_install_extra_deps(venv_dir, entry.get("package_name", entry["source"]))
        ok, err = _venv_pip_install(venv_dir, entry["source"])
        if not ok:
            LOG.error(f"Failed to reinstall {skill_id} into its venv: {err}")
            shutil.rmtree(venv_dir, ignore_errors=True)


def _seed_default_skills_if_first_boot():
    """Install the small, curated default set (see catalog.json) --
    but only once, ever, on this add-on's genuinely first boot. Checks
    a dedicated marker file, NOT whether the manifest happens to be
    empty right now -- someone who deliberately uninstalled every
    default skill later should not have them silently reappear on the
    next restart. Runs before discover_and_launch_all() so newly-seeded
    skills get launched in the same pass as everything else.
    """
    if os.path.isfile(DEFAULTS_SEEDED_MARKER):
        return
    manifest = _read_manifest()
    for item in _read_catalog():
        if not item.get("default"):
            continue
        # item["package_name"], not item["source"] -- confirmed for
        # real, this session: skill-ovos-stop's own git URL doesn't
        # yield a matching PyPI name via URL-derivation
        # (_repo_name_from_git_url gives "skill-ovos-stop", the real
        # PyPI package is "ovos-skill-stop"), so it silently fell back
        # to the git source and installed a dev-branch version missing
        # a transitive dependency (ModuleNotFoundError:
        # ovos_plugin_manager). This project's own curated catalog
        # already has the CONFIRMED-correct PyPI name for every entry
        # (verified via `pip show`/`pip index versions` while building
        # this list) -- using it directly here is more reliable than
        # re-deriving and re-checking a candidate from the URL.
        LOG.info(f"First boot: installing default skill {item['name']} ({item['package_name']})")
        result = _install_skill_into_venv(item["package_name"])
        if result is None:
            LOG.error(f"Failed to install default skill {item['name']} -- see errors above")
            continue
        manifest[result["skill_id"]] = {
            "source": result["source"], "package_name": result["package_name"],
        }
    _write_manifest(manifest)
    os.makedirs(os.path.dirname(DEFAULTS_SEEDED_MARKER), exist_ok=True)
    with open(DEFAULTS_SEEDED_MARKER, "w") as f:
        f.write("seeded\n")


class SkillProcessManager:
    """One isolated venv per skill (see module docstring) -- launches
    <venv>/bin/ovos-skill-launcher <skill_id> per entry, not a shared,
    container-wide binary. The manifest file is the sole source of
    truth for what's installed; no site-packages scanning of any kind.
    """

    MAX_RESTARTS = 5  # per skill_id, not reset -- a skill that crashes
                       # this many times has a real bug, not a transient
                       # hiccup.
    MONITOR_INTERVAL = 10

    def __init__(self):
        self._procs: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, int] = {}
        self._stopping: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _discover() -> dict[str, str]:
        """{skill_id: package_name}, straight from the manifest."""
        manifest = _read_manifest()
        return {skill_id: entry["package_name"] for skill_id, entry in manifest.items()}

    def package_name_for(self, skill_id: str) -> str | None:
        return self._discover().get(skill_id)

    def skill_id_for_package(self, package_name: str) -> str | None:
        for skill_id, pkg in self._discover().items():
            if pkg == package_name:
                return skill_id
        return None

    def launch(self, skill_id: str):
        with self._lock:
            existing = self._procs.get(skill_id)
            if existing is not None and existing.poll() is None:
                return  # already running
            self._stopping.discard(skill_id)
            launcher = os.path.join(_venv_dir(skill_id), "bin", "ovos-skill-launcher")
            if not os.path.isfile(launcher):
                LOG.error(
                    f"No launcher found for {skill_id} at {launcher} -- "
                    f"venv missing or install incomplete"
                )
                return
            # No stdout=/stderr=PIPE: inherit this process's own stdout/
            # stderr, so each skill's own log output goes straight to
            # this add-on's normal HA log.
            proc = subprocess.Popen([launcher, skill_id])
            self._procs[skill_id] = proc
        LOG.info(f"Launched skill process for {skill_id} (pid {proc.pid})")
        # Re-apply a previously-deactivated state -- see
        # _reapply_active_state_after_delay's own docstring for why a
        # freshly launched skill needs this every single time, not
        # just once. No-op (returns immediately) for the common case
        # of a skill that's never been deactivated.
        threading.Thread(
            target=_reapply_active_state_after_delay, args=(skill_id,), daemon=True,
        ).start()

    def stop(self, skill_id: str):
        with self._lock:
            self._stopping.add(skill_id)
            proc = self._procs.pop(skill_id, None)
            self._restart_counts.pop(skill_id, None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        LOG.info(f"Stopped skill process for {skill_id}")

    def discover_and_launch_all(self):
        """Launch every currently-installed skill. Called once at
        startup, after _rebuild_all_venvs_from_manifest() has finished.

        Staggered, not a tight back-to-back loop -- confirmed via
        haos-ovos-dev (2026-08-29) that launching all skills at once
        (subprocess.Popen, non-blocking, zero delay between calls)
        clusters every skill's own "padatious:register_intent" bus
        emission into a very tight window right after each one
        connects. ovos-padatious's own training_manager has a real,
        reproducible concurrency bug under that load -- "dictionary
        changed size during iteration" / bare-string KeyErrors during
        training, and the intents that fail training then fail to load
        from cache too (never written), so they silently never match.
        Confirmed NOT fixed by padatious's own "workers" config (that
        controls FANN training-math parallelism, not this registration-
        bookkeeping race). This stagger is the working hypothesis, not
        yet independently reproduced on a from-scratch boot -- see
        DOCS.md for confirmed/pending status before trusting this
        comment alone. 0.5s is empirical, not derived from anything in
        padatious's own source; revisit if it's ever insufficient with
        a much larger skill catalog.
        """
        for skill_id in self._discover():
            self.launch(skill_id)
            time.sleep(0.5)

    def _monitor_loop(self):
        while True:
            time.sleep(self.MONITOR_INTERVAL)
            with self._lock:
                items = list(self._procs.items())
            for skill_id, proc in items:
                if proc.poll() is None or skill_id in self._stopping:
                    continue  # still running, or deliberately stopped
                count = self._restart_counts.get(skill_id, 0) + 1
                self._restart_counts[skill_id] = count
                if count > self.MAX_RESTARTS:
                    LOG.error(
                        f"Skill process for {skill_id} died (rc={proc.returncode}) "
                        f"{count} times, giving up -- see its own stdout/stderr in logs"
                    )
                    continue
                LOG.warning(
                    f"Skill process for {skill_id} died (rc={proc.returncode}), "
                    f"restarting (attempt {count}/{self.MAX_RESTARTS})"
                )
                self.launch(skill_id)

    def start_monitor(self):
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def status(self) -> dict:
        with self._lock:
            return {
                skill_id: {
                    "running": proc.poll() is None,
                    "pid": proc.pid,
                    "restart_count": self._restart_counts.get(skill_id, 0),
                }
                for skill_id, proc in self._procs.items()
            }


skill_procs = SkillProcessManager()


def _broadcast_ready_signal() -> None:
    """A just-launched skill's own _connect_to_core() (ovos_workshop)
    asks ovos-core "are you ready?" once, right after connecting -- if
    the answer is "no", it falls back to waiting passively for a
    "mycroft.ready" bus event that may never come again, since it's a
    one-time signal from ovos-core's own startup sequence. Confirmed
    for real, this session: ovos-core's own SkillManager (the component
    that answers that question) only ever tracks skills installed in
    ITS OWN Python environment -- it has no way to know this add-on's
    separate container/venv skills exist at all, so the answer can stay
    "no" indefinitely for anything launched here, regardless of how
    long ovos-core itself has been running.

    Rather than trying to fix ovos-core's own internal readiness
    tracking (a separate, more invasive change to a different add-on,
    and the underlying reason it never learns about these skills is
    architectural, not a simple bug), this add-on emits that same
    "mycroft.ready" event itself, right after every launch. Harmless
    even for skills that already loaded correctly -- ovos_workshop's
    own load_skill() just reloads in that case -- and reliably unblocks
    any skill sitting in the "waiting for ready event" state, regardless
    of why ovos-core's own answer was "no".
    """
    try:
        from ovos_bus_client import MessageBusClient
        from ovos_bus_client.message import Message
        bus = MessageBusClient()
        bus.run_in_thread()
        bus.connected_event.wait(timeout=10)
        bus.emit(Message("mycroft.ready"))
        bus.close()
    except Exception as exc:
        LOG.warning(f"Could not broadcast mycroft.ready: {exc}")


def _broadcast_ready_after_delay(delay: float = 5.0) -> None:
    """Runs in a background thread -- see _broadcast_ready_signal's own
    docstring for why this exists.

    REPEATS several times, not a single shot -- confirmed for real,
    this session: with several skills launching at once on real (weak)
    hardware, a single broadcast only reached whichever skill happened
    to finish connecting and register its own "mycroft.ready" listener
    first (one skill out of nine loaded; the rest were still mid-
    connect when the one-shot signal fired and simply missed it,
    exactly the same race the original problem was, just narrowed).
    Repeating catches stragglers without needing to know in advance how
    long any given skill takes to connect on whatever hardware this
    runs on. Each broadcast is a harmless no-op for any skill that
    already loaded.
    """
    # TEMPORARY: reduced to a single shot to test a hypothesis --
    # repeated reload() calls (triggered by each broadcast) may be
    # corrupting padacioso's own intent registration state, since /ask
    # still times out even after skills report themselves ready.
    time.sleep(delay)
    _broadcast_ready_signal()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _rebuild_all_venvs_from_manifest()
    _seed_default_skills_if_first_boot()
    skill_procs.discover_and_launch_all()
    skill_procs.start_monitor()
    threading.Thread(target=_broadcast_ready_after_delay, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


class InstallRequest(BaseModel):
    url: str


@app.get("/health")
def health():
    # No messagebus connection to report on anymore -- this add-on no
    # longer talks to it at all (see module docstring). "true" here
    # just means the API itself is up.
    return {"bus_connected": True}


@app.get("/skills/running")
def running_skills():
    """Status of every skill process this container is currently
    supervising -- running/dead, PID, and how many times it's been
    restarted. See SkillProcessManager's own docstring for the full
    mechanism this reports on.
    """
    return skill_procs.status()


@app.get("/catalog")
def get_catalog():
    """This add-on's own small, curated catalog, read fresh from
    catalog.json every call (not cached -- this file is small, and a
    live re-read means the store can be edited without restarting the
    add-on). NOT a proxy of the official OVOS skills-store feed
    anymore. Small enough to drive a dropdown directly, same response
    shape as before ({"items": [...]}) so ha-ovos-integration's own
    catalog-consuming code needs no changes.
    """
    return {"items": _read_catalog()}


@app.get("/skills")
def list_installed_skills():
    """Straight from the manifest -- the source of truth for what's
    installed now that there's no shared site-packages to scan. Each
    skill's version is looked up live from its own venv's pip, since
    the manifest itself doesn't track version (a skill can be upgraded
    independently of the manifest entry changing).
    """
    manifest = _read_manifest()
    skills = []
    for skill_id, entry in manifest.items():
        version = _venv_pip_show_version(_venv_dir(skill_id), entry["package_name"])
        skills.append({
            "skill_id": skill_id,
            "package_name": entry["package_name"],
            "source": entry["source"],
            "version": version,
            "active": _is_skill_active(skill_id),
        })
    return {"skills": skills}


def _run_install_job(job_key: str, source: str):
    result = _install_skill_into_venv(source)
    if result is None:
        jobs[job_key] = {"status": "failed", "error": "install failed -- see add-on logs for details"}
        return

    manifest = _read_manifest()
    # result["source"] is what was actually installed from -- may be a
    # PyPI package name if _resolve_install_target found one, not
    # necessarily the original git URL passed in. Storing that (not the
    # raw `source` argument) means a future rebuild-on-restart reuses
    # the same, already-resolved choice.
    manifest[result["skill_id"]] = {"source": result["source"], "package_name": result["package_name"]}
    _write_manifest(manifest)

    # Gives the skill its first chance to write its own settings.json --
    # OVOS creates this automatically the moment a skill loads, even
    # with no settings at all, so a settings UI built on that file's
    # actual shape (see ha-ovos-integration's skill_subentry.py) has
    # something real to read right after a fresh install.
    skill_procs.launch(result["skill_id"])
    threading.Thread(target=_broadcast_ready_after_delay, daemon=True).start()

    jobs[job_key] = {"status": "complete", "skill_id": result["skill_id"]}


@app.post("/skills/install")
def install_skill(req: InstallRequest):
    jobs[req.url] = {"status": "pending"}
    threading.Thread(
        target=_run_install_job, args=(req.url, req.url), daemon=True,
    ).start()
    return {"status": "pending", "poll": f"/skills/install/status?key={req.url}"}


@app.get("/skills/install/status")
def install_status(key: str):
    job = jobs.get(key)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job")
    return job


@app.delete("/skills/{skill_id}")
def uninstall_skill(skill_id: str, package_name: str | None = None):
    """rm -rf of the skill's own venv, plus removing it from the
    manifest -- no protected-package list needed anymore (unlike the
    old shared-site-packages design): a skill's venv can never touch
    ovos-core's own packages or another skill's, so there's nothing
    critical it could accidentally take down.
    """
    manifest = _read_manifest()
    if skill_id not in manifest:
        raise HTTPException(status_code=404, detail=f"No installed skill '{skill_id}'")

    skill_procs.stop(skill_id)
    shutil.rmtree(_venv_dir(skill_id), ignore_errors=True)
    manifest.pop(skill_id, None)
    _write_manifest(manifest)

    jobs[skill_id] = {"status": "complete"}
    return {"status": "pending", "poll": f"/skills/install/status?key={skill_id}"}


def _settings_path(skill_id: str) -> str:
    # Unaffected by the venv rework -- matches OVOS's own runtime
    # convention: ${XDG_CONFIG_HOME}/mycroft/skills/<skill_id>/settings.json,
    # keyed by skill_id (the dotted id), independent of where the
    # skill's own code/venv lives. Already on /share via XDG_CONFIG_HOME.
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "mycroft", "skills", skill_id, "settings.json")


@app.get("/skills/{skill_id}/active")
def get_skill_active(skill_id: str):
    """Whether this skill is currently active (the default) or has
    been deactivated via PUT below -- from the persisted state file,
    not a live bus query (see ACTIVE_STATE_PATH's own comment: no bus
    message exists to ask a running skill process its own state, so
    this file IS the source of truth, kept in sync by always going
    through _set_skill_active for every change).
    """
    manifest = _read_manifest()
    if skill_id not in manifest:
        raise HTTPException(status_code=404, detail=f"No installed skill '{skill_id}'")
    return {"active": _is_skill_active(skill_id)}


class ActiveRequest(BaseModel):
    active: bool


@app.put("/skills/{skill_id}/active")
def put_skill_active(skill_id: str, req: ActiveRequest):
    manifest = _read_manifest()
    if skill_id not in manifest:
        raise HTTPException(status_code=404, detail=f"No installed skill '{skill_id}'")
    _set_skill_active(skill_id, req.active)
    return {"status": "ok", "active": req.active}


@app.get("/skills/{skill_id}/settingsmeta")
def get_settingsmeta(skill_id: str, package_name: str | None = None):
    """Not every skill ships a settingsmeta.json -- callers must handle
    has_settingsmeta: false and fall back to settings.json-shape-based
    editing (see ha-ovos-integration's skill_subentry.py).

    package_name query param is now accepted but ignored -- the
    manifest already has the confirmed-real package name from the
    actual install, no fuzzy matching against a possibly-wrong catalog
    guess needed anymore.
    """
    manifest = _read_manifest()
    entry = manifest.get(skill_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No installed skill '{skill_id}'")

    real_name = entry["package_name"]
    result = _pip_show_files(_venv_dir(skill_id), real_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Package metadata not found for '{real_name}'")
    location, files = result

    meta_rel = next((f for f in files if os.path.basename(f) == "settingsmeta.json"), None)
    if meta_rel is None:
        return {"has_settingsmeta": False, "fields": [], "package_name": real_name}

    try:
        with open(os.path.join(location, meta_rel), encoding="utf-8") as f:
            content = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse settingsmeta.json: {exc}")

    fields = [
        field
        for section in content.get("skillMetadata", {}).get("sections", [])
        for field in section.get("fields", [])
    ]
    return {"has_settingsmeta": True, "fields": fields, "package_name": real_name}


@app.get("/skills/{skill_id}/settings")
def get_settings(skill_id: str):
    path = _settings_path(skill_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not read settings.json: {exc}")


@app.put("/skills/{skill_id}/settings")
def put_settings(skill_id: str, settings: dict[str, Any] = Body(...)):
    path = _settings_path(skill_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write settings.json: {exc}")
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
