"""HTTP-to-messagebus bridge for OVOS skill install/uninstall.

Talks to ovos-core's own SkillsStore (ovos_core.skill_installer), running
standalone via `ovos-skill-installer` in this same container, connected to
a private `ovos-messagebus` instance that never leaves the container. See
DEVELOPER.md for why this replaced wrapping ovos_skill_manager (OSM),
which ovos-core's own README says is unsupported since ovos-core 0.0.8.
"""
from __future__ import annotations

import json
import subprocess
import threading
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
