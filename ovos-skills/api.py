"""HTTP-to-messagebus bridge for OVOS skill install/uninstall.

Talks to ovos-core's own SkillsStore (ovos_core.skill_installer), running
standalone via `ovos-skill-installer` in this same container, connected to
a private `ovos-messagebus` instance that never leaves the container. See
DEVELOPER.md for why this replaced wrapping ovos_skill_manager (OSM),
which ovos-core's own README says is unsupported since ovos-core 0.0.8.
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import re
import shutil
import site
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

import requests
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel
from ovos_bus_client import MessageBusClient, Message

LOG = logging.getLogger("ovos-skills-api")

# pip installs land in the container's own filesystem layer, which does
# NOT survive an add-on rebuild/update — confirmed on real hardware: a
# skill installed, then wiped clean by the next version bump. After every
# successful install, newly-added package files get copied here (on the
# /share volume, which does persist); run.sh copies them back into
# site-packages on every container start, before anything else runs.
PERSIST_DIR = "/share/ovos-skills/persisted-packages"

CATALOG_URL = "https://openvoiceos.github.io/OVOS-skills-store/skills.json"
BUS_TIMEOUT = 300  # generous — this now runs in a background thread, not
                    # blocking any HTTP client, so a slow git clone + pip
                    # resolve is fine. A synchronous "block until pip
                    # finishes" design would be a poor fit for eventually
                    # being called from a HA config flow anyway — those
                    # expect quick responses, not multi-minute waits.

bus: MessageBusClient | None = None
jobs: dict[str, dict] = {}  # key: url (install) or skill_id (uninstall)


class SkillProcessManager:
    """Launches and supervises one `ovos-skill-launcher <skill_id>`
    subprocess per installed skill, each connecting independently to the
    shared bus. Confirmed for real: a skill launched this way, in this
    container, answers correctly through ovos-core's own /ask -- it
    never needs to be present in ovos-core's own site-packages (see
    DEVELOPER.md's "Skill runtime" section for the full proof). This is
    the permanent replacement for the manual /debug/launch-skill endpoint
    used to first confirm the mechanism.

    Discovers installed skills via importlib.metadata entry_points
    (group 'opm.skill', falling back to the deprecated 'ovos.plugin.skill'
    for older skill packages) rather than guessing from pip package names
    -- confirmed this gives the exact dotted skill_id ovos-skill-launcher
    needs, AND the real owning package name in the same call, so install/
    uninstall can look up the right running process without fuzzy
    matching.
    """

    MAX_RESTARTS = 5  # per skill_id, not reset -- a skill that crashes
                       # this many times has a real bug, not a transient
                       # hiccup; stop burning CPU on an infinite restart
                       # loop and leave it visibly dead in status() for a
                       # human to notice, rather than silently retrying
                       # forever.
    MONITOR_INTERVAL = 10

    def __init__(self):
        self._procs: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, int] = {}
        self._stopping: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _discover() -> dict[str, str]:
        """Returns {skill_id: package_name} for every currently-installed
        skill in this container.
        """
        result: dict[str, str] = {}
        for group in ("opm.skill", "ovos.plugin.skill"):
            for ep in importlib.metadata.entry_points(group=group):
                if ep.name not in result:
                    result[ep.name] = ep.dist.name if ep.dist else ep.name
        return result

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
            # No stdout=/stderr=PIPE: inherit this process's own stdout/
            # stderr instead, so each skill's own log output goes
            # straight to this add-on's normal HA log (visible via the
            # usual add-on log view) -- confirmed the hard way that PIPE
            # silently swallows a skill's own error output, since nothing
            # ever reads from that pipe unless the process has already
            # died. Prefixing each skill's log lines would need a real
            # log-forwarding thread; not done yet, see DEVELOPER.md.
            proc = subprocess.Popen(["ovos-skill-launcher", skill_id])
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
        startup, after both this container's persisted packages are
        restored (run.sh) and the shared bus is confirmed reachable.
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
    global bus
    bus = MessageBusClient()
    bus.run_in_thread()
    bus.connected_event.wait(timeout=10)
    skill_procs.discover_and_launch_all()
    skill_procs.start_monitor()
    yield
    if bus:
        bus.close()


app = FastAPI(lifespan=lifespan)


class InstallRequest(BaseModel):
    url: str


def emit_and_wait_either(msg_type: str, data: dict, ok_type: str, fail_type: str, timeout: float):
    """Emit exactly once, then wait for whichever of two reply types
    arrives first — unlike wait_for_response(reply_type=...), which only
    matches one type and would require a second emit() (a second pip
    install!) as a fallback if the actual reply was the other type.
    """
    result: dict = {}
    done = threading.Event()

    def _on_ok(message):
        result["ok"] = True
        result["data"] = message.data
        done.set()

    def _on_fail(message):
        result["ok"] = False
        result["data"] = message.data
        done.set()

    bus.once(ok_type, _on_ok)
    bus.once(fail_type, _on_fail)
    bus.emit(Message(msg_type, data))

    if not done.wait(timeout=timeout):
        bus.remove(ok_type, _on_ok)
        bus.remove(fail_type, _on_fail)
        return None
    return result


@app.get("/health")
def health():
    return {"bus_connected": bool(bus and bus.connected_event.is_set())}


@app.get("/debug/is-ready")
def debug_is_ready():
    """TEMPORARY: test whether ovos-core's own skill-manager actually
    replies "ready" to mycroft.skills.is_ready over the shared bus --
    every launched skill process is stuck logging "Skills service not
    ready yet", so testing this directly rather than guessing why.
    Remove once resolved.
    """
    from ovos_bus_client import Message
    response = bus.wait_for_response(
        Message("mycroft.skills.is_ready", context={"source": "debug", "destination": "skills"}),
        timeout=5,
    )
    if response is None:
        return {"got_response": False}
    return {"got_response": True, "data": response.data}


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
    """Proxy the official, curated skill catalog — 36 skills as of the
    check in DEVELOPER.md, small enough to drive a dropdown directly.
    """
    try:
        resp = requests.get(CATALOG_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach catalog: {exc}")


@app.get("/skills")
def list_installed_skills():
    """Heuristic, not a confirmed mechanism (see DEVELOPER.md): lists pip
    packages whose name matches the 'skill-' / 'ovos-skill-' naming
    convention seen in the official catalog's package_name fields. Revisit
    if this proves unreliable once tested against real installs.
    """
    try:
        raw = subprocess.check_output(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"pip list failed: {exc.output}")

    packages = json.loads(raw)
    skills = [
        p for p in packages
        if p["name"].startswith("ovos-skill-") or p["name"].startswith("skill-")
    ]
    return {"skills": skills}


def _run_job(job_key: str, msg_type: str, data: dict, ok_type: str, fail_type: str):
    before = _installed_names() if msg_type == "ovos.skills.install" else None

    result = emit_and_wait_either(msg_type, data, ok_type, fail_type, timeout=BUS_TIMEOUT)
    if result is None:
        jobs[job_key] = {"status": "failed", "error": "No reply from SkillsStore (timeout)"}
        return
    if not result["ok"]:
        jobs[job_key] = {"status": "failed", "error": result["data"].get("error", "unknown error")}
        return

    jobs[job_key] = {"status": "complete"}
    if before is not None:
        try:
            persisted = _persist_new_packages(before)
            LOG.info(f"Persisted {len(persisted)} newly-installed package(s) to {PERSIST_DIR}: {persisted}")
        except Exception as exc:
            # A persistence failure shouldn't make a successful install
            # look like it failed to the caller — the skill genuinely is
            # installed and usable right now, it just won't survive a
            # future add-on rebuild. Log loudly, don't flip the job status.
            LOG.error(f"Failed to persist newly-installed packages: {exc}")

        # Hot-launch: start the skill process immediately, no container
        # restart needed. entry_points() only sees packages actually on
        # disk, so this naturally picks up whatever was just installed --
        # confirmed the mechanism itself works end-to-end (see
        # DEVELOPER.md's "Skill runtime" section); this wires it into the
        # real install flow instead of a manual debug call.
        for skill_id in skill_procs._discover():
            skill_procs.launch(skill_id)


def _site_packages_dir() -> str:
    dirs = site.getsitepackages()
    return dirs[0] if dirs else site.getusersitepackages()


def _installed_names() -> set[str]:
    return {d.metadata["Name"] for d in importlib.metadata.distributions() if d.metadata["Name"]}


def _persist_new_packages(before: set[str]) -> list[str]:
    """Copy every file belonging to each newly-installed package (the
    skill itself, plus any new transitive dependencies it pulled in) into
    PERSIST_DIR, preserving their path relative to site-packages, so
    run.sh can copy them straight back on the next container start.
    """
    importlib.metadata = importlib.reload(importlib.metadata)  # pick up new dist-info
    new_names = _installed_names() - before
    sp_dir = _site_packages_dir()
    persisted = []
    for name in new_names:
        try:
            files = importlib.metadata.files(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for f in files:
            src = str(f.locate())
            if not os.path.isfile(src):
                continue
            rel = os.path.relpath(src, sp_dir)
            if rel.startswith(".."):
                continue  # not actually under site-packages, e.g. a script in bin/
            dst = os.path.join(PERSIST_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        persisted.append(name)
    return persisted


@app.post("/skills/install")
def install_skill(req: InstallRequest):
    if bus is None or not bus.connected_event.is_set():
        raise HTTPException(status_code=503, detail="Not connected to internal bus")

    jobs[req.url] = {"status": "pending"}
    threading.Thread(
        target=_run_job,
        args=(req.url, "ovos.skills.install", {"url": req.url},
              "ovos.skills.install.complete", "ovos.skills.install.failed"),
        daemon=True,
    ).start()
    return {"status": "pending", "poll": f"/skills/install/status?key={req.url}"}


@app.get("/skills/install/status")
def install_status(key: str):
    job = jobs.get(key)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job")
    return job


def _run_uninstall_job(job_key: str, package_name: str):
    ok, error = _direct_pip_uninstall(package_name)
    if ok:
        jobs[job_key] = {"status": "complete"}
    else:
        jobs[job_key] = {"status": "failed", "error": error}


@app.delete("/skills/{skill_id}")
def uninstall_skill(skill_id: str, package_name: str | None = None):
    """Bypasses SkillsStore's own (currently stubbed) uninstall — see
    _direct_pip_uninstall's docstring. package_name resolves the real
    installed name via the same fuzzy matcher settingsmeta uses (the
    catalog's package_name and the real installed name don't always
    match); falls back to a dot-to-dash guess from skill_id if omitted,
    same heuristic SkillsStore itself uses.
    """
    real_name = None
    if package_name:
        real_name = _find_installed_package(package_name)
    if real_name is None:
        real_name = skill_id.replace(".", "-") if "." in skill_id else skill_id

    jobs[skill_id] = {"status": "pending"}
    threading.Thread(
        target=_run_uninstall_job,
        args=(skill_id, real_name),
        daemon=True,
    ).start()
    return {"status": "pending", "poll": f"/skills/install/status?key={skill_id}"}


def _find_installed_package(hint: str) -> str | None:
    """The catalog's package_name doesn't always match what pip actually
    installed it as — confirmed for real (skill-ovos-fallback-chatgpt's
    catalog entry says ovos-skill-ovos-fallback-chatgpt, but it installs
    as skill-ovos-fallback-chatgpt). Normalized exact match first, then a
    unique-substring fallback, rather than trusting the hint literally.

    Uses `pip list` via a fresh subprocess, NOT importlib.metadata run
    inside this process — confirmed the hard way, with explicit logging,
    that importlib.metadata.distributions() genuinely doesn't see
    packages restored via run.sh's file-copy even after BOTH
    importlib.invalidate_caches() AND reload(importlib.metadata) (85
    packages seen, the target skill not among them), while a fresh `pip
    list` subprocess sees it correctly every time — same mechanism the
    /skills endpoint already relies on successfully. Whatever the exact
    Python internals are, a long-running process's own view of
    site-packages is not trustworthy here; a fresh subprocess's is.
    """
    def norm(s: str) -> str:
        return s.lower().replace("_", "-").replace(" ", "-")

    hint_norm = norm(hint)
    try:
        raw = subprocess.check_output(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            text=True, stderr=subprocess.STDOUT,
        )
        names = [p["name"] for p in json.loads(raw)]
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    for name in names:
        if norm(name) == hint_norm:
            return name
    candidates = [name for name in names if hint_norm in norm(name) or norm(name) in hint_norm]
    return candidates[0] if len(candidates) == 1 else None


# Mirrors SkillsStore's own hardcoded fallback protected-package list
# exactly. Deliberately NOT read from our own constraints file — that
# file is intentionally empty (see the stale-constraints-file fix
# above), and SkillsStore uses that same file for both version pins AND
# the protected-package list, so reusing it here would silently disable
# protection entirely. Kept independent on purpose.
PROTECTED_PACKAGES = {
    "ovos-core", "ovos-utils", "ovos-plugin-manager",
    "ovos-config", "ovos-bus-client", "ovos-workshop",
}


def _remove_package_dir_files(base_dir: str, package_name: str) -> bool:
    """Deletes a package's dist-info dir and its module(s) from base_dir,
    found via PEP 503 normalized-name matching against dist-info dir
    names (<normalized_name>-<version>.dist-info) and their
    top_level.txt — not importlib.metadata, which is unreliable in this
    long-running process for packages restored via file-copy rather than
    a pip install run inside it (confirmed for real: 85 packages seen,
    a genuinely-on-disk target package not among them, even after both
    importlib.invalidate_caches() and reload(importlib.metadata)).

    Works identically against site-packages and PERSIST_DIR — both need
    this, and having two different (and differently broken) mechanisms
    for what's conceptually the same operation was the actual bug that
    caused an uninstalled skill to reappear after a rebuild: the
    site-packages side got fixed, but PERSIST_DIR's own removal was
    still going through the old, unreliable importlib.metadata path and
    silently doing nothing.
    """
    if not os.path.isdir(base_dir):
        return False

    def norm(s: str) -> str:
        return s.lower().replace("-", "_")

    target_norm = norm(package_name)
    removed = False
    for entry in os.listdir(base_dir):
        if not entry.endswith(".dist-info"):
            continue
        m = re.match(r"^(.+?)-[^-]+\.dist-info$", entry)
        if not m or norm(m.group(1)) != target_norm:
            continue
        dist_info_path = os.path.join(base_dir, entry)
        top_level_file = os.path.join(dist_info_path, "top_level.txt")
        module_names = []
        if os.path.isfile(top_level_file):
            with open(top_level_file) as f:
                module_names = [line.strip() for line in f if line.strip()]
        shutil.rmtree(dist_info_path, ignore_errors=True)
        removed = True
        for mod in module_names:
            mod_path = os.path.join(base_dir, mod)
            if os.path.isdir(mod_path):
                shutil.rmtree(mod_path, ignore_errors=True)
            elif os.path.isfile(mod_path + ".py"):
                os.remove(mod_path + ".py")
    return removed


def _remove_persisted_package(package_name: str) -> None:
    """Remove a package's files from PERSIST_DIR too — must run BEFORE
    the actual pip uninstall, so a subsequent restart doesn't restore an
    uninstalled skill. See _remove_package_dir_files for why this uses
    dist-info scanning, not importlib.metadata.
    """
    _remove_package_dir_files(PERSIST_DIR, package_name)


def _manual_remove_package(package_name: str) -> tuple[bool, str]:
    """Fallback for when `pip uninstall` refuses with "no RECORD file was
    found" — confirmed for real that our persist/restore cycle doesn't
    reliably preserve a package's RECORD file intact (pip's own error
    message names the exact package and file it's missing).
    """
    if _remove_package_dir_files(_site_packages_dir(), package_name):
        return True, ""
    return False, f"Could not find a dist-info directory for '{package_name}' to manually remove"


def _direct_pip_uninstall(package_name: str) -> tuple[bool, str]:
    """Bypasses SkillsStore/the messagebus entirely. Its own uninstall is
    a stub on the current PyPI ovos-core — already fixed in ovos-core's
    dev branch, but not releasable to PyPI without also resolving a
    separate ovos-messagebus version conflict (see DOCS.md) — a
    release-coordination problem across two repos, not something a PR
    here could fix, unlike the missing --upgrade support (#843), which
    was a genuine local code gap.

    Deliberately a stand-in, not the destination: once a PyPI release
    resolves that conflict, prefer switching back to SkillsStore's own
    uninstall (same protected-package concept, better maintained) over
    keeping this running in parallel indefinitely.
    """
    def norm(s: str) -> str:
        return s.lower().replace("_", "-").replace(".", "-")

    if norm(package_name) in PROTECTED_PACKAGES:
        return False, f"refusing to uninstall protected package: {package_name}"

    skill_id = skill_procs.skill_id_for_package(package_name)
    if skill_id is not None:
        skill_procs.stop(skill_id)

    _remove_persisted_package(package_name)

    # sys.executable, not a bare "pip" — matches SkillsStore's own
    # approach. A bare "pip" can resolve to a different interpreter's
    # pip than the one actually running this process; confirmed the hard
    # way, reporting success while silently uninstalling from the wrong
    # place, before switching to this.
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "--break-system-packages", package_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "pip uninstall timed out"

    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or result.stdout or "").strip()
    if "no RECORD file was found" in stderr:
        # confirmed for real: our persist/restore cycle doesn't always
        # keep RECORD intact — fall back to direct removal instead of
        # failing outright.
        return _manual_remove_package(package_name)

    return False, stderr or "pip uninstall failed"


def _settings_path(skill_id: str) -> str:
    # Matches OVOS's own runtime convention, confirmed against real skill
    # READMEs: ${XDG_CONFIG_HOME}/mycroft/skills/<skill_id>/settings.json
    # — keyed by skill_id (the catalog's dotted id), not the pip package
    # name, unlike settingsmeta lookup below.
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "mycroft", "skills", skill_id, "settings.json")


@app.get("/skills/{skill_id}/settingsmeta")
def get_settingsmeta(skill_id: str, package_name: str):
    """Not every skill ships a settingsmeta.json — confirmed for real by
    installing two different skills: one had it, one didn't. Callers must
    handle has_settingsmeta: false and fall back to raw settings editing.
    """
    real_name = _find_installed_package(package_name)
    if real_name is None:
        raise HTTPException(status_code=404, detail=f"No installed package matching '{package_name}'")

    try:
        files = importlib.metadata.files(real_name) or []
    except importlib.metadata.PackageNotFoundError:
        raise HTTPException(status_code=404, detail=f"Package metadata not found for '{real_name}'")

    meta_file = next((f for f in files if f.name == "settingsmeta.json"), None)
    if meta_file is None:
        return {"has_settingsmeta": False, "fields": [], "package_name": real_name}

    try:
        content = json.loads(meta_file.read_text())
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
