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
import shutil
import site
import subprocess
import sys
import threading
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bus
    bus = MessageBusClient()
    bus.run_in_thread()
    bus.connected_event.wait(timeout=10)
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


@app.get("/debug/persist-dir")
def debug_persist_dir():
    """Temporary diagnostic — a skill reappeared after an uninstall +
    rebuild on real hardware despite _remove_persisted_package running
    (confirmed in logs) and working correctly in an isolated sandbox
    test. Need to see what's actually in PERSIST_DIR on the real
    container to find the real cause instead of guessing further.
    Remove once the actual bug is found and fixed.
    """
    if not os.path.isdir(PERSIST_DIR):
        return {"exists": False}
    entries = []
    for root, dirs, files in os.walk(PERSIST_DIR):
        for f in files:
            entries.append(os.path.relpath(os.path.join(root, f), PERSIST_DIR))
    return {"exists": True, "file_count": len(entries), "date_time_related": [
        e for e in entries if "date" in e.lower() or "date_time" in e.lower()
    ]}


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
    """
    def norm(s: str) -> str:
        return s.lower().replace("_", "-").replace(" ", "-")

    hint_norm = norm(hint)
    names = [d.metadata["Name"] for d in importlib.metadata.distributions() if d.metadata["Name"]]
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


def _remove_persisted_package(package_name: str) -> None:
    """Remove a package's files from PERSIST_DIR too — must run BEFORE
    the actual pip uninstall, since importlib.metadata.files() only
    works while the package is still installed. Otherwise an uninstalled
    skill would silently reappear on the next container restart via
    run.sh's restore step.
    """
    try:
        files = importlib.metadata.files(package_name) or []
    except importlib.metadata.PackageNotFoundError:
        return
    sp_dir = _site_packages_dir()
    for f in files:
        src = str(f.locate())
        try:
            rel = os.path.relpath(src, sp_dir)
        except ValueError:
            continue
        if rel.startswith(".."):
            continue
        target = os.path.join(PERSIST_DIR, rel)
        if os.path.isfile(target):
            os.remove(target)


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

    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "pip uninstall failed").strip()
    return True, ""


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
