"""Synchronous question/answer HTTP bridge to a running ovos-core instance.

Confirmed working end-to-end in a sandbox spike before this add-on existed
-- see DOCS.md for the full writeup, including the exact bus messages this
mirrors and what wasn't tested (concurrent requests specifically -- see
the module-level lock below).
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ovos_bus_client import MessageBusClient, Message

LOG = logging.getLogger("ovos-core-api")

ASK_TIMEOUT = 20  # generous -- a skill's own processing (e.g. an API call
                   # a skill itself makes) adds to the round trip; the
                   # sandbox spike's actual response came back in under a
                   # second for a simple skill, this is headroom not an
                   # expected wait.

bus: MessageBusClient | None = None

# Serializes requests -- confirmed working for one request at a time in
# the sandbox spike; concurrent requests were NOT tested. Matching
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


@app.get("/debug/skill-files")
def debug_skill_files():
    """TEMPORARY: confirm whether ovos-skill-date-time's locale/ resource
    directory actually made it into the installed package on this specific
    Alpine build -- the sandbox spike (Debian/Ubuntu) had it and worked;
    real hardware is logging 'Unable to find X.intent' and a much smaller
    m2v prototype count (76 vs 2333), suggesting it may not have. Remove
    once resolved -- see DOCS.md.
    """
    import ovos_skill_date_time
    pkg_dir = os.path.dirname(ovos_skill_date_time.__file__)
    tree = {}
    for root, dirs, files in os.walk(pkg_dir):
        rel = os.path.relpath(root, pkg_dir)
        tree[rel] = files
    return {"pkg_dir": pkg_dir, "tree": tree}


@app.get("/debug/mycroft-conf")
def debug_mycroft_conf():
    """TEMPORARY: resource files ARE present (confirmed via /debug/skill-files)
    and lang is correctly 'en-us' (confirmed via HA's own text.language
    entity) -- so something about the SHARED /share/mycroft/mycroft.conf
    itself (written to by five other add-ons: tts/stt/wakeword/persona/
    skills) may be affecting intent matching in a way the sandbox spike's
    clean, empty config never exercised. Remove once resolved.
    """
    path = "/share/mycroft/mycroft.conf"
    if not os.path.isfile(path):
        return {"exists": False, "path": path}
    with open(path) as f:
        content = f.read()
    return {"exists": True, "path": path, "content": content}


@app.get("/debug/network")
def debug_network():
    """TEMPORARY: test whether a DNS lookup or outbound connection HANGS
    (rather than failing fast) from inside this container -- unlike the
    already-ruled-out metrics-upload daemon thread, a synchronous
    blocking lookup somewhere earlier in handle_utterance (before the
    'match' log line) would explain the hang without ever logging an
    error. Each check has its own explicit, short timeout so a real hang
    here shows up as this endpoint itself timing out, not a graceful
    per-check failure.
    """
    import socket
    import time as _time
    results = {}

    try:
        with open("/etc/resolv.conf") as f:
            results["resolv_conf"] = f.read()
    except Exception as exc:
        results["resolv_conf"] = f"<error: {exc}>"

    for host in ["metrics.tigregotico.pt", "openvoiceos.github.io", "8.8.8.8"]:
        start = _time.monotonic()
        try:
            socket.setdefaulttimeout(5)
            addr = socket.gethostbyname(host)
            results[host] = {"resolved": addr, "seconds": round(_time.monotonic() - start, 2)}
        except Exception as exc:
            results[host] = {"error": str(exc), "seconds": round(_time.monotonic() - start, 2)}
    return results


@app.get("/debug/versions")
def debug_versions():
    """TEMPORARY: send_complete_intent_failure references OVOS-PIPELINE-1
    spec messages (ovos.intent.unmatched, ovos.utterance.handled) never
    seen in the sandbox spike -- suspect a NEWER ovos-core got installed
    on this real build than the sandbox's 2.6.0a1, since constraints-alpha.txt
    is a live file fetched at build time, hours after the sandbox test.
    """
    import importlib.metadata
    names = ["ovos-core", "ovos-workshop", "ovos-bus-client", "ovos-config",
              "ovos-plugin-manager"]
    return {n: importlib.metadata.version(n) for n in names}


@app.get("/debug/processes")
def debug_processes():
    """TEMPORARY: /debug/ask-verbose showed our own bus client sees
    NOTHING back after emitting an utterance, even though ovos-core's own
    log clearly shows it parsing the utterance -- suspect our client may
    be talking to a stale/duplicate messagebus process left over from an
    earlier restart, not the one ovos-core is actually using. Remove once
    resolved.
    """
    import subprocess
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    return {"ps_aux": result.stdout}


@app.post("/debug/ask-verbose")
def debug_ask_verbose(req: AskRequest):
    """TEMPORARY: neither resource files nor lang explain the missing
    response -- listen for EVERY bus message for a window after emitting
    the utterance, instead of only ovos.utterance.speak, to see what
    actually happens on real hardware that didn't happen in the sandbox.
    Note: the client's own 'message' event fires with the raw payload,
    not a parsed Message (confirmed by reading client.py directly) --
    parse it ourselves and skip anything that fails to decode.
    """
    import json as _json
    import time as _time
    seen: list[dict] = []

    def on_any(raw):
        try:
            parsed = _json.loads(raw) if isinstance(raw, str) else raw
            seen.append({"type": parsed.get("type"), "data": parsed.get("data")})
        except Exception as exc:
            seen.append({"type": "<unparsed>", "data": str(exc)})

    bus.on("message", on_any)
    bus.emit(Message("recognizer_loop:utterance",
                      {"utterances": [req.utterance], "lang": req.lang}))
    _time.sleep(180)
    bus.remove("message", on_any)
    return {"message_count": len(seen), "messages": seen}


def _ask_sync(utterance: str, lang: str) -> dict | None:
    """The exact emit/wait pattern confirmed in the sandbox spike: send
    recognizer_loop:utterance (same message ovos-say-to itself emits --
    see ovos_bus_client.scripts.ovos_say_to, read directly rather than
    guessed), wait for ovos.utterance.speak back (SpecMessage.SPEAK in
    ovos_workshop/skills/ovos.py -- NOT the older classic "speak" message
    some tooling still expects). Confirmed for real: "what time is it" in,
    "It is ten twenty two" back out, computed correctly by a genuinely
    running ovos-skill-date-time.
    """
    result: dict = {}
    done = threading.Event()

    def on_speak(message):
        result["utterance"] = message.data.get("utterance")
        result["skill"] = message.data.get("meta", {}).get("skill")
        done.set()

    bus.on("ovos.utterance.speak", on_speak)
    bus.emit(Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}))
    ok = done.wait(timeout=ASK_TIMEOUT)
    bus.remove("ovos.utterance.speak", on_speak)

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
            detail=f"No response within {ASK_TIMEOUT}s -- ovos-core may still be "
                   "starting up (first boot takes ~90s, see DOCS.md) or no skill "
                   "and no fallback matched",
        )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
