"""HTTP-to-messagebus bridge for OVOS skill install/uninstall -- one
isolated Python venv per skill.

This is the FREE, UNVERIFIED counterpart to the ovos-skills add-on. See
that add-on's own DOCS.md/module docstring for the full architecture
reasoning (why one venv per skill, why nothing here is persisted except
a small manifest, etc.) -- the underlying mechanism is deliberately
identical; only the source of what gets installed differs.

ovos-skills serves a small, CURATED catalog: only skills this project
has actually verified make sense in its specific architecture (a
synchronous /ask bridge into ovos-core, no ovos-audio, no continuous
microphone listener -- several "obviously core" OVOS skills, like
volume and naptime, were confirmed to rely on PHAL plugins this setup
doesn't have and were deliberately excluded, not merely unlisted).

This add-on (ovos-skills-extra) has NO catalog and NO verification at
all -- it exists specifically for anything NOT vetted yet, or that
never will be (a person's own skill, an experimental one, one this
project hasn't gotten around to checking). Install takes a raw
PyPI-name-or-git-URL text field instead of a dropdown; the underlying
_resolve_install_target/_pip_installable logic already handles either
form correctly, so no separate install code path is needed -- ANY
OVOS-compatible skill, installable and configurable exactly like
ovos-skills' own, just without a safety net. What works, and whether it
makes sense in this bridge architecture, is on the person adding it.

Deliberately its own, independent add-on/API/manifest -- not merged
into ovos-skills. Keeps the curated catalog trustworthy (nothing
unverified can leak into it) while still giving power users an
unrestricted escape hatch, the same separation Debian draws between
main and contrib, or HA itself between built-in integrations and HACS.
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

LOG = logging.getLogger("ovos-skills-extra-api")

# Inside the container's OWN filesystem, deliberately NOT on /share --
# see module docstring.
VENV_ROOT = "/opt/skill-venvs"

# The ONLY thing persisted for reinstall purposes: skill_id -> {source,
# package_name}. Own directory, deliberately separate from ovos-skills'
# own manifest -- these are two independent add-ons.
MANIFEST_PATH = "/share/ovos-skills-extra/manifest.json"

INSTALL_TIMEOUT = 300  # venv create + pip install -- a slow git clone +
                        # dependency resolve is realistic, not a hang

jobs: dict[str, dict] = {}  # key: source (install) or skill_id (uninstall)


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
    """Uses `virtualenv`, not the stdlib venv module -- more reliable
    ensurepip bootstrapping on Alpine (see Dockerfile).
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
    """A bare repo URL is NOT directly pip-installable -- pip treats a
    plain https:// URL as a direct archive download, and a GitHub repo
    *page* URL returns HTML, not an archive ("Cannot determine archive
    format", confirmed for real in ovos-skills). Needs the "git+" scheme
    prefix so pip clones it as a VCS source instead. Left alone if
    already prefixed, an archive URL, or a plain PyPI package name (no
    scheme at all) -- covers both input shapes this add-on's own text
    field accepts (a PyPI name, or a git URL).
    """
    if source.startswith(("git+", "git@")) or "://" not in source:
        return source
    if source.endswith(_ARCHIVE_EXTENSIONS):
        return source
    return f"git+{source}"


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
BASELINE_PACKAGES = ["ovos-workshop", "ovos-plugin-manager", "setuptools<=80.9.0"]
# setuptools added after a third, same-class failure confirmed for
# real: ovos_plugin_manager's own code does "import pkg_resources"
# internally, which newer setuptools versions no longer bundle by
# default in a fresh venv -- same "assumes a full, shared OVOS
# environment already has this" pattern as the ovos-plugin-manager gap
# itself. PINNED, not just added unpinned -- confirmed directly (wheel
# inspection): setuptools 83.0.0 (latest) ships zero pkg_resources
# files, 80.9.0 ships 19. An earlier, unpinned attempt installed
# whatever was newest and still failed with the exact same error --
# same version ceiling this project's own Dockerfiles already use for
# the same reason.


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
    console_scripts have hardcoded, absolute shebang lines pointing at
    the now-gone old path -- confirmed for real in ovos-skills;
    re-running `virtualenv <path>` does NOT reliably fix third-party
    scripts, only virtualenv's own core files. Rewriting the path
    directly in each bin/ script's own text is simpler and reliable.
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
    skill_id it registers. Returns {"skill_id", "package_name",
    "source"} on success, None on failure. No PyPI-preference logic
    here (unlike ovos-skills) -- the person typed exactly what they
    want installed, a PyPI name or a git URL; that's respected as-is,
    not second-guessed.
    """
    tmp_dir = os.path.join(VENV_ROOT, f".tmp-{os.getpid()}-{int(time.time() * 1000)}")
    ok, err = _create_venv(tmp_dir)
    if not ok:
        LOG.error(f"venv creation failed for {source}: {err}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    _venv_pip_install_baseline(tmp_dir)

    ok, err = _venv_pip_install(tmp_dir, source)
    if not ok:
        LOG.error(f"pip install failed for {source}: {err}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    entries = _venv_discover_skill(tmp_dir)
    if not entries:
        LOG.error(f"No skill entry_point found after installing {source}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    chosen = entries[0]
    if len(entries) > 1:
        LOG.warning(
            f"{source} registered {len(entries)} skill entry_points, "
            f"using {chosen['skill_id']} (first)"
        )

    skill_id = chosen["skill_id"]
    final_dir = _venv_dir(skill_id)
    if os.path.isdir(final_dir):
        shutil.rmtree(final_dir)  # reinstall/upgrade case
    shutil.move(tmp_dir, final_dir)
    _rewrite_venv_shebangs(final_dir, tmp_dir, final_dir)

    return {"skill_id": skill_id, "package_name": chosen["package_name"], "source": source}


def _rebuild_all_venvs_from_manifest():
    """On every container start, every skill's venv must be rebuilt from
    scratch -- venvs are NOT persisted. Runs synchronously, before
    discover_and_launch_all().
    """
    manifest = _read_manifest()
    for skill_id, entry in manifest.items():
        venv_dir = _venv_dir(skill_id)
        if os.path.isfile(os.path.join(venv_dir, "bin", "ovos-skill-launcher")):
            continue  # already present
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


class SkillProcessManager:
    """One isolated venv per skill -- launches
    <venv>/bin/ovos-skill-launcher <skill_id> per entry. The manifest
    file is the sole source of truth for what's installed.
    """

    MAX_RESTARTS = 5
    MONITOR_INTERVAL = 10

    def __init__(self):
        self._procs: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, int] = {}
        self._stopping: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _discover() -> dict[str, str]:
        manifest = _read_manifest()
        return {skill_id: entry["package_name"] for skill_id, entry in manifest.items()}

    def launch(self, skill_id: str):
        with self._lock:
            existing = self._procs.get(skill_id)
            if existing is not None and existing.poll() is None:
                return
            self._stopping.discard(skill_id)
            launcher = os.path.join(_venv_dir(skill_id), "bin", "ovos-skill-launcher")
            if not os.path.isfile(launcher):
                LOG.error(
                    f"No launcher found for {skill_id} at {launcher} -- "
                    f"venv missing or install incomplete"
                )
                return
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
        for skill_id in self._discover():
            self.launch(skill_id)

    def _monitor_loop(self):
        while True:
            time.sleep(self.MONITOR_INTERVAL)
            with self._lock:
                items = list(self._procs.items())
            for skill_id, proc in items:
                if proc.poll() is None or skill_id in self._stopping:
                    continue
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
    skill_procs.discover_and_launch_all()
    skill_procs.start_monitor()
    yield


app = FastAPI(lifespan=lifespan)


class InstallRequest(BaseModel):
    url: str  # a PyPI package name OR a git URL -- see _pip_installable


@app.get("/health")
def health():
    return {"bus_connected": True}


@app.get("/skills/running")
def running_skills():
    return skill_procs.status()


@app.get("/skills")
def list_installed_skills():
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
    manifest[result["skill_id"]] = {"source": result["source"], "package_name": result["package_name"]}
    _write_manifest(manifest)

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
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "mycroft", "skills", skill_id, "settings.json")


@app.get("/skills/{skill_id}/settingsmeta")
def get_settingsmeta(skill_id: str, package_name: str | None = None):
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
    uvicorn.run(app, host="0.0.0.0", port=8502)
