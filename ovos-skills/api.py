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
along with the messagebus dependency itself). This file no longer
connects to the messagebus at all.
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
# than not offering them at all. Every skill below was individually
# checked the same way before being added. Anything not vetted yet
# belongs in the separate ovos-skills-extra add-on instead (see its own
# DOCS.md), not here -- this list stays trustworthy by only ever
# growing through the same verification, never by convenience.
#
# "default" entries are installed automatically on this add-on's very
# first-ever boot (see _seed_default_skills_if_first_boot) -- a small,
# sensible baseline so there's something useful from the start, the
# same idea ovos-installer's own default skill set follows. Everything
# else here is opt-in via the catalog UI, same as before.
CURATED_CATALOG = [
    {
        "skill_id": "skill-ovos-date-time.openvoiceos",
        "name": "Date and Time",
        "description": "Answers questions about the current date and time.",
        "source": "https://github.com/OpenVoiceOS/skill-ovos-date-time",
        "package_name": "ovos-skill-date-time",
        "default": True,
    },
    {
        "skill_id": "ovos-skill-alerts.openvoiceos",
        "name": "Alerts",
        "description": "Alarms, timers, and reminders.",
        "source": "https://github.com/OpenVoiceOS/ovos-skill-alerts",
        "package_name": "ovos-skill-alerts",
        "default": True,
    },
    {
        "skill_id": "ovos-skill-fallback-unknown.openvoiceos",
        "name": "Fallback: Unknown",
        "description": "Gives a clear \"I don't understand\" response when nothing else "
                        "matches, instead of silence.",
        "source": "https://github.com/OpenVoiceOS/ovos-skill-fallback-unknown",
        "package_name": "ovos-skill-fallback-unknown",
        "default": True,
    },
    {
        "skill_id": "ovos-skill-weather.openvoiceos",
        "name": "Weather",
        "description": "Current conditions and forecasts.",
        "source": "https://github.com/OpenVoiceOS/ovos-skill-weather",
        "package_name": "ovos-skill-weather",
        "default": True,
    },
    {
        "skill_id": "ovos-skill-ip.openvoiceos",
        "name": "IP Address",
        "description": "Reads back this device's local IP address.",
        "source": "https://github.com/OpenVoiceOS/ovos-skill-ip",
        "package_name": "ovos-skill-ip",
        "default": True,
    },
    {
        # NOT installable as-is, kept out of "default" -- confirmed for
        # real, this session: ovos-skill-stop's own (and transitively
        # ovos-workshop's own) declared dependencies are missing
        # ovos-plugin-manager, even though ovos_workshop.skills.ovos
        # imports from it directly (ModuleNotFoundError at launch,
        # reproduced twice, once via git source and once via the
        # correct, confirmed PyPI package -- same failure either way,
        # ruling out a git-vs-PyPI cause). A genuine upstream packaging
        # gap that venv-per-skill isolation surfaces rather than causes
        # -- the old shared-site-packages design masked this exact
        # class of bug, since ovos-plugin-manager would just happen to
        # already be present from another skill or ovos-core itself.
        # Still listed (not deleted) so the gap is visible and easy to
        # revisit once fixed upstream, rather than silently forgotten.
        "skill_id": "skill-ovos-stop.openvoiceos",
        "name": "Stop",
        "description": "Handles \"stop\" -- lets other skills (e.g. a ringing alarm) "
                        "listen for it and cancel themselves. KNOWN BROKEN: fails to "
                        "launch (missing ovos-plugin-manager dependency, confirmed "
                        "upstream, not specific to this add-on) -- not usable yet.",
        "source": "https://github.com/OpenVoiceOS/skill-ovos-stop",
        "package_name": "ovos-skill-stop",
        "default": False,
    },
    {
        "skill_id": "skill-ovos-dictation.openvoiceos",
        "name": "Dictation",
        "description": "Free-form dictation mode.",
        "source": "https://github.com/OpenVoiceOS/skill-ovos-dictation",
        "package_name": "ovos-skill-dictation",
        "default": False,
    },
    {
        # NOT actually functional here -- confirmed for real, this
        # session: like ovos-skill-volume/-naptime (PHAL-dependent),
        # this skill has its own dependency this project's architecture
        # doesn't provide, just a different one. NewsSkill extends
        # OVOSCommonPlaybackSkill; play_media() emits
        # "ovos.common_play.play" (confirmed by reading
        # ovos_workshop.skills.common_play's own source), which needs a
        # separate, running ovos-media service (OCP's actual audio
        # backend) to pick up and stream real audio -- nothing in this
        # project's stack does. Ran for hours on real hardware this
        # session without ever actually confirmed to play audio -- it
        # loads and responds without error, which is exactly the kind
        # of silent, misleading non-functionality this catalog exists
        # to screen out. Any other OCP-based media skill (local-media,
        # somafm, pyradios, youtube-music, ...) would hit the identical
        # wall. Revisit once/if a real media-playback bridge add-on
        # exists (an ovos-media service that actually plays through, or
        # hands off to, something -- e.g. an HA media_player entity).
        "skill_id": "skill-ovos-news.openvoiceos",
        "name": "News Streams",
        "description": "Plays news audio streams. KNOWN BROKEN: needs a running "
                        "ovos-media service to actually play audio, which this "
                        "project's architecture doesn't provide -- not usable yet.",
        "source": "https://github.com/OpenVoiceOS/skill-ovos-news",
        "package_name": "ovos-skill-news",
        "default": False,
    },
]

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
BASELINE_PACKAGES = ["ovos-workshop", "ovos-plugin-manager"]


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
        ok, err = _venv_pip_install(venv_dir, entry["source"])
        if not ok:
            LOG.error(f"Failed to reinstall {skill_id} into its venv: {err}")
            shutil.rmtree(venv_dir, ignore_errors=True)


def _seed_default_skills_if_first_boot():
    """Install the small, curated default set (see CURATED_CATALOG) --
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
    for item in CURATED_CATALOG:
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
        """
        for skill_id in self._discover():
            self.launch(skill_id)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _rebuild_all_venvs_from_manifest()
    _seed_default_skills_if_first_boot()
    skill_procs.discover_and_launch_all()
    skill_procs.start_monitor()
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
    """This add-on's own small, curated catalog (see CURATED_CATALOG's
    docstring) -- NOT a proxy of the official OVOS skills-store feed
    anymore. Small enough to drive a dropdown directly, same response
    shape as before ({"items": [...]})  so ha-ovos-integration's own
    catalog-consuming code needs no changes.
    """
    return {"items": CURATED_CATALOG}


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
