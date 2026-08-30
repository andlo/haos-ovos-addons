"""Synchronous question/answer HTTP bridge to a running ovos-core instance.

Confirmed working end-to-end on real hardware -- see DOCS.md for the full
investigation and what's still open ("Not yet done"), including the exact
bus messages this mirrors and what wasn't tested (concurrent requests
specifically -- see the module-level lock below).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ovos_bus_client import MessageBusClient, Message

LOG = logging.getLogger("ovos-core-api")

ASK_TIMEOUT = 35  # padacioso (the active matcher -- see run.sh) confirmed
                   # on real hardware to take anywhere from ~8s to 22+s,
                   # not the "under a second" originally assumed -- CPU
                   # contention from padatious's own background training
                   # was the real cause (now uninstalled entirely, see
                   # Dockerfile), but keeping real headroom here too
                   # rather than assuming that fully eliminates the
                   # variance on this specific weak hardware.

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


def _write_shared_config(config: dict) -> None:
    tmp = SHARED_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.replace(tmp, SHARED_CONFIG_PATH)  # atomic, same pattern as ovos-skills' own manifest/active-state writes


def _get_by_path(config: dict, path: str):
    """path like "/tts/module" or "tts/module" -- same slash-delimited
    convention `ovos-config get -k /tts/module` itself uses (confirmed
    via its own --help), not dot-notation, so a caller who already knows
    that CLI's own path syntax can use the exact same string here.
    """
    node = config
    for part in path.strip("/").split("/"):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def _set_by_path(config: dict, path: str, value) -> None:
    """Same slash-delimited path convention as _get_by_path. Creates
    intermediate dicts as needed (e.g. setting "/tts/module" on a config
    with no "tts" key yet creates it) -- matches how ovos-config's own
    `set` command behaves for a path that doesn't fully exist yet
    (confirmed by reading its source: it uses dpath's own merge, which
    does the same). Raises if an intermediate part exists but ISN'T a
    dict (e.g. trying to set "/tts/module/foo" when "tts.module" is
    already a plain string) -- a real conflict, not something to
    silently paper over by overwriting a sibling value's own type.
    """
    parts = path.strip("/").split("/")
    node = config
    for part in parts[:-1]:
        if part not in node:
            node[part] = {}
        elif not isinstance(node[part], dict):
            raise TypeError(f"'{part}' in '{path}' is not a section (it's a {type(node[part]).__name__})")
        node = node[part]
    node[parts[-1]] = value


class ConfigSetRequest(BaseModel):
    key: str
    value: object


def _read_joined_config() -> dict:
    """The FULL EFFECTIVE config (user overrides merged over ovos-config's
    own baked-in defaults), not just whatever's explicitly written to the
    shared mycroft.conf -- confirmed by testing directly: date_format,
    time_format, temperature_unit etc. were never once written to our
    own shared file (nothing in this project ever set them), yet
    Configuration() correctly reports their real, in-effect default
    values ("MDY", "half", "celsius"), while a raw read of the shared
    file alone would show nothing for these keys at all. GET /config
    below is meant to answer "what is this actually set to right now",
    which requires this distinction -- ovos-config itself makes the same
    one, joining "user > system > remote > default" (its own `show`
    --help says so directly).
    """
    from ovos_config import Configuration
    return dict(Configuration())


@app.get("/config")
def get_config(key: str | None = None):
    """Generic escape hatch alongside /autoconfigure's own curated,
    language-driven flow -- for the individual settings autoconfigure
    doesn't cover (or covers as a side effect you want to override by
    hand). Mirrors `ovos-config get -k <path>` (see that CLI's own
    --help), but with a STRICT path only, not that command's own fuzzy
    "search for keys containing this text" mode -- fine for a human at
    a terminal picking from a prompted list, wrong for a programmatic
    caller (ha-ovos-integration) that needs one deterministic answer,
    not a list to disambiguate.

    Reads the full JOINED config (see _read_joined_config's own
    docstring) -- shows real in-effect values, including ones never
    explicitly written to the shared file, not just explicit overrides.

    No key at all returns the full joined config, same as `ovos-config
    show`'s own default (this project's closest equivalent to a full
    schema dump, since ovos-config itself has no --json output mode --
    confirmed via its own --help).
    """
    config = _read_joined_config()
    if key is None:
        return config
    try:
        return {"key": key, "value": _get_by_path(config, key)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No such config key: '{key}'")


@app.put("/config")
def set_config(req: ConfigSetRequest):
    """The write-side counterpart to GET /config above. Writes directly
    to the shared mycroft.conf rather than shelling out to `ovos-config
    set` -- that command's own fuzzy key matching and interactive
    value-type prompting are built for a human at a terminal, not a
    predictable API a caller can rely on; a direct, atomic JSON write
    with a value the caller already gave as a real JSON type (bool/
    number/string/list/object, no string-parsing ambiguity) is more
    reliable here, same reasoning _set_by_path's own docstring covers.

    Does NOT restart anything -- most OVOS services read Configuration()
    once at startup and don't hot-reload it (confirmed already for
    logs.path elsewhere in this project: a restart was needed for that
    to take effect). This endpoint can't know which add-on(s), if any,
    need restarting for an arbitrary key, so it always says so rather
    than guessing right for some keys and silently wrong for others.
    """
    config = _read_shared_config()
    try:
        _set_by_path(config, req.key, req.value)
    except TypeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _write_shared_config(config)
    return {
        "status": "ok",
        "key": req.key,
        "value": req.value,
        "note": "Restart the relevant add-on(s) for this to take effect -- most OVOS services read this once at startup.",
    }


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

    ALSO listens for "mycroft.mic.listen" -- confirmed by reading
    ovos_workshop's own get_response() directly: when a skill needs a
    follow-up reply (e.g. "what time should the alarm be?"), it speaks
    the dialog (the same "speak" event above) and then emits this
    message to signal it's now waiting for the user's next utterance --
    then BLOCKS ITS OWN THREAD waiting for that reply to arrive on the
    bus, rather than returning like a normal one-shot answer. Nothing
    else in this synchronous-bridge architecture (no real mic/wake-word
    loop feeding the bus) would emit this message under normal use, so
    seeing it here is a reliable signal specifically that a skill wants
    a follow-up, not a false positive from unrelated bus activity.

    Grace-period design, not a second full-length wait: "speak" and
    "mycroft.mic.listen" are two back-to-back emissions from the SAME
    skill thread handling this SAME utterance (get_response() speaks,
    then immediately emits the listen signal before blocking) -- so if
    the second one is coming at all, it arrives within a couple hundred
    ms of the first, not after any meaningful additional wait.
    """
    result: dict = {}
    done = threading.Event()
    listening = threading.Event()

    def on_speak(message):
        result["utterance"] = message.data.get("utterance")
        result["skill"] = message.data.get("meta", {}).get("skill")
        done.set()

    def on_listen(message):
        listening.set()

    bus.on("speak", on_speak)
    bus.on("mycroft.mic.listen", on_listen)
    bus.emit(Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}))
    ok = done.wait(timeout=ASK_TIMEOUT)
    if ok:
        # Short grace period only, not ASK_TIMEOUT again -- see
        # docstring above for why this is safe to keep brief.
        listening.wait(timeout=1.5)
        result["expect_response"] = listening.is_set()
    bus.remove("speak", on_speak)
    bus.remove("mycroft.mic.listen", on_listen)

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
