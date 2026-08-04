"""Synchronous question/answer HTTP bridge to a running ovos-core instance.

Confirmed working end-to-end on real hardware -- see DOCS.md for the full
investigation and what's still open ("Not yet done"), including the exact
bus messages this mirrors and what wasn't tested (concurrent requests
specifically -- see the module-level lock below).
"""
from __future__ import annotations

import logging
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


def _ask_sync(utterance: str, lang: str) -> dict | None:
    """The exact emit/wait pattern confirmed on real hardware: send
    recognizer_loop:utterance (same message ovos-say-to itself emits --
    see ovos_bus_client.scripts.ovos_say_to), wait for ovos.utterance.speak
    back (SpecMessage.SPEAK in ovos_workshop/skills/ovos.py -- NOT the
    older classic "speak" message some tooling still expects). Confirmed
    for real: "what time is it" in, a correct spoken time back out,
    computed by a genuinely running ovos-skill-date-time.
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
            detail=f"No response within {ASK_TIMEOUT}s -- no skill and no fallback matched",
        )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
