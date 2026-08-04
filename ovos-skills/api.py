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
import os
import subprocess
import threading
from contextlib import asynccontextmanager
from typing import Any

import requests
from fastapi import Body, FastAPI, HTTPException
from pydantic import BaseModel
from ovos_bus_client import MessageBusClient, Message

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
            ["pip", "list", "--format=json"],
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
    result = emit_and_wait_either(msg_type, data, ok_type, fail_type, timeout=BUS_TIMEOUT)
    if result is None:
        jobs[job_key] = {"status": "failed", "error": "No reply from SkillsStore (timeout)"}
    elif result["ok"]:
        jobs[job_key] = {"status": "complete"}
    else:
        jobs[job_key] = {"status": "failed", "error": result["data"].get("error", "unknown error")}


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


@app.delete("/skills/{skill_id}")
def uninstall_skill(skill_id: str):
    if bus is None or not bus.connected_event.is_set():
        raise HTTPException(status_code=503, detail="Not connected to internal bus")

    jobs[skill_id] = {"status": "pending"}
    threading.Thread(
        target=_run_job,
        args=(skill_id, "ovos.skills.uninstall", {"skill": skill_id},
              "ovos.skills.uninstall.complete", "ovos.skills.uninstall.failed"),
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
