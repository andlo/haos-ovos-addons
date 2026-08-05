"""HTTP bridge for configuring ovos-persona-server -- lets
ha-ovos-integration read and edit persona.json's own "solvers" list
(which question-solver plugins are active, in priority order), then
restarts the ovos-persona-server process for the change to take effect
(confirmed by reading run.sh: it only reads persona.json once, at its
own startup, via `--persona /persona.json` -- no live-reload).

Deliberately its own, independent add-on -- see DEVELOPER.md's note on
why persona and skills are NOT merged: a person can genuinely run
either without the other (or both), so this add-on's own API URL is a
separate field in ha-ovos-integration (CONF_PERSONA_API_URL), never
assumed to exist just because ovos-skills does, and vice versa.

Solver discovery: via importlib.metadata.entry_points(group=
"opm.solver.question") -- confirmed for real by reading
ovos-plugin-manager's own find_question_solver_plugins() source, which
resolves to exactly this group via PluginTypes.QUESTION_SOLVER.value.
Not a hardcoded/guessed list of plugin names -- this repo already
learned the hard way (see Dockerfile's own comment) that a solver
plugin's PyPI package name and its registered plugin id are often
different (ovos-ddg-solver-plugin registers "ovos-solver-plugin-ddg").

First-cut scope: only the "solvers" list (which plugins run, in what
order) is editable here. persona.json also carries per-solver
sub-objects (e.g. {"ovos-solver-bm25-freebase-plugin": {"enabled":
false}}) for solvers present but disabled, or requiring their own API
keys -- genuinely nested config, not the flat, primitive-valued shape
the skills settings UI's inference mechanism was built for. Left for a
follow-up rather than force-fit; documented as a known limitation.
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import subprocess
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException

LOG = logging.getLogger("ovos-persona-api")

PERSONA_JSON_PATH = "/persona.json"

_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()


def _launch_persona_server():
    """(Re)start ovos-persona-server against the current persona.json --
    also used after a settings write, since the process only reads its
    config at startup.
    """
    global _proc
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _proc.kill()
        _proc = subprocess.Popen(["ovos-persona-server", "--persona", PERSONA_JSON_PATH])
    LOG.info(f"Launched ovos-persona-server (pid {_proc.pid})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _launch_persona_server()
    yield
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    with _proc_lock:
        running = _proc is not None and _proc.poll() is None
    return {"bus_connected": running}


@app.get("/available-solvers")
def available_solvers():
    """Every question-solver plugin actually installed in this
    container, via entry_points -- not a hardcoded/guessed list. See
    module docstring for why this specific group name is confirmed
    correct, not assumed.
    """
    try:
        names = {ep.name for ep in importlib.metadata.entry_points(group="opm.solver.question")}
        return {"solvers": sorted(names)}
    except Exception as exc:
        LOG.error(f"Solver discovery failed: {exc}")
        return {"solvers": []}


@app.get("/settings")
def get_settings():
    if not os.path.isfile(PERSONA_JSON_PATH):
        return {}
    try:
        with open(PERSONA_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


@app.put("/settings")
def put_settings(settings: dict[str, Any] = Body(...)):
    try:
        with open(PERSONA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write persona.json: {exc}")
    _launch_persona_server()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8338)
