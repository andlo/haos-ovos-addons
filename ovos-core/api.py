"""Synchronous question/answer HTTP bridge to a running ovos-core instance.

Confirmed working end-to-end on real hardware -- see DOCS.md for the full
investigation and what's still open ("Not yet done"), including the exact
bus messages this mirrors and what wasn't tested (concurrent requests
specifically -- see the module-level lock below).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ovos_bus_client import MessageBusClient, Message

LOG = logging.getLogger("ovos-core-api")

ASK_TIMEOUT = 20  # padacioso (the active matcher -- see run.sh) answers
                   # in under a second on real hardware; this is headroom
                   # for a skill's own processing (e.g. an API call a
                   # skill itself makes), not an expected wait.

bus: MessageBusClient | None = None

# Serializes requests -- concurrent requests were NOT tested. Matching
# multiple in-flight requests to their own responses needs OVOS's session
# system (context["session"]["session_id"], propagated via a skill's own
# message.forward() call in speak()) -- plausible based on reading the
# source, but unverified, so not relied on yet. A lock is the safe,
# simple v1 choice: requests queue instead of racing to claim the wrong
# answer. Revisit once genuinely needed (see DOCS.md's "Not yet done").
_ask_lock = threading.Lock()


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


class AskRequest(BaseModel):
    utterance: str
    lang: str = "en-us"


@app.get("/health")
def health():
    return {"bus_connected": bool(bus and bus.connected_event.is_set())}


SHARED_CONFIG_PATH = "/share/mycroft/mycroft.conf"


class AutoconfigureRequest(BaseModel):
    lang: str
    online: bool = False   # mutually exclusive with offline -- if
    offline: bool = False  # neither is set, ovos-config defaults to
                            # "hybrid" (offline TTS + online STT)
    male: bool = False     # mutually exclusive with female -- if
    female: bool = False   # neither is set, TTS voice config is skipped
                            # entirely (confirmed by reading autoconfigure's
                            # own source)


@app.post("/autoconfigure")
def autoconfigure(req: AutoconfigureRequest):
    """Runs OVOS's own `ovos-config autoconfigure` CLI against the real,
    shared mycroft.conf -- not an isolated temp file. This container
    already has ovos-config installed (a real dependency, not added just
    for this), so this gets its actual, maintained plugin-selection logic
    "for free" rather than re-implementing it. See DEVELOPER.md's
    "mycroft.conf-as-master" section for why writing to the real shared
    file directly, instead of an isolated copy, is the correct design
    here (Wyoming add-ons are meant to read this shared value as their
    own source of truth once that reversal is built).

    Called via subprocess, not by importing the click-decorated Python
    function directly -- runs exactly as the CLI is designed to, with
    click's own validation (e.g. rejecting --male + --female together)
    intact, rather than us needing to understand click's internals to
    call it safely.

    IMPORTANT, confirmed by testing directly: autoconfigure writes far
    more than just tts/stt -- also system_unit, lang, and several
    date/time-format keys, all derived from the chosen language. This
    endpoint reports back everything that changed, not just tts/stt, so
    a caller (ha-ovos-integration) can decide how to handle values it
    already manages from HA's own settings (see DEVELOPER.md -- explicit
    reconciliation with those fields is NOT built yet, deliberately left
    for that layer to decide, not silently overwritten here without the
    caller knowing).

    Also confirmed by reading OVOS's own documentation (ovos-docker's
    Wyoming plugin install docs, and the ovos-installer manual's own
    "the installer... might not always select the best defaults, run
    autoconfigure --help after" note): autoconfigure choosing a plugin
    and that plugin actually being installed are two separate steps in
    OVOS's own official workflow, not one automatic action -- confirmed
    for real on a genuine OVOS venv install, where the active tts/stt
    module in mycroft.conf wasn't installed at all. This endpoint
    doesn't try to install anything either, for the same reason: no
    reliable way exists to derive a real pip package name from an OVOS
    module name (confirmed for real -- "ovos-tts-plugin-phoonnx" is the
    module name, "phoonnx" is the actual PyPI package). Always reports
    tts_module/stt_module so the caller can tell the person what's
    active and let them add it to the right add-on's own extra pip
    packages if needed -- the same two-step process OVOS's own tooling
    expects.
    """
    cmd = ["ovos-config", "autoconfigure", "--lang", req.lang]
    if req.online:
        cmd.append("--online")
    if req.offline:
        cmd.append("--offline")
    if req.male:
        cmd.append("--male")
    if req.female:
        cmd.append("--female")

    try:
        before = _read_shared_config()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="ovos-config autoconfigure timed out")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.stderr or result.stdout or "autoconfigure failed").strip(),
        )

    # autoconfigure exits 0 even when it found nothing for the requested
    # lang/mode/voice combination -- confirmed by reading its source: a
    # missing recommends file for that combination just logs
    # "ERROR: {folder} not available for {lang}" to stdout and returns
    # early, leaving that section unchanged. Parsed here so the caller
    # can tell "ran fine, nothing to pick for this combination" apart
    # from "picked something new" instead of only seeing changed_keys
    # stay empty either way.
    not_available = re.findall(r"ERROR: (\w+) not available for (.+)", result.stdout)

    after = _read_shared_config()
    changed = {k: v for k, v in after.items() if before.get(k) != v}
    return {
        "changed_keys": changed,
        "not_available": [{"category": cat, "lang": lang} for cat, lang in not_available],
        "tts_module": after.get("tts", {}).get("module"),
        "stt_module": after.get("stt", {}).get("module"),
    }


def _read_shared_config() -> dict:
    try:
        with open(SHARED_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _ask_sync(utterance: str, lang: str) -> dict | None:
    """The exact emit/wait pattern confirmed on real hardware: send
    recognizer_loop:utterance (same message ovos-say-to itself emits --
    see ovos_bus_client.scripts.ovos_say_to), wait for "speak" back.

    Listens for the classic "speak" message, not "ovos.utterance.speak"
    -- confirmed by reading ovos_workshop/skills/ovos.py's own speak()
    directly, inside the actual running container: this stable-channel
    ovos-workshop (3.4.0) emits `message.forward("speak", data)`. The
    newer "ovos.utterance.speak"/SpecMessage.SPEAK convention this
    endpoint originally waited for belongs to a much newer ovos-workshop
    than what stable's coordinated version set installs -- real answers
    were being computed the whole time (confirmed via `docker stats`
    showing genuine CPU work, not a hang), just never delivered back
    here, because nothing was listening for the message actually sent.
    """
    result: dict = {}
    done = threading.Event()

    def on_speak(message):
        result["utterance"] = message.data.get("utterance")
        result["skill"] = message.data.get("meta", {}).get("skill")
        done.set()

    bus.on("speak", on_speak)
    bus.emit(Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}))
    ok = done.wait(timeout=ASK_TIMEOUT)
    bus.remove("speak", on_speak)

    return result if ok else None


@app.post("/ask")
def ask(req: AskRequest):
    if bus is None or not bus.connected_event.is_set():
        raise HTTPException(status_code=503, detail="Not connected to messagebus")

    with _ask_lock:
        result = _ask_sync(req.utterance, req.lang)

    if result is None:
        raise HTTPException(
            status_code=504,
            detail=f"No response within {ASK_TIMEOUT}s -- no skill and no fallback matched",
        )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
