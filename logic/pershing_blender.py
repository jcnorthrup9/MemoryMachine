"""
logic/pershing_blender.py
--------------------------
Async wrapper around blender/pershing_headless_build.py -- the "build a
full-fidelity, exportable mesh in Blender" tier of the hybrid pipeline.

Deliberately NOT part of the live rebuild loop: logic/pershing_api.py's
in-process TerracingEngine call (~0.04s, see PIPELINE_STATUS_AND_NEXT_STEPS.md)
stays the only thing driven by slider drags and paint bakes. Spawning a
Blender process has real, unavoidable startup cost (a fresh --background
launch is seconds, not milliseconds) -- routing every parameter tweak
through it would undo the whole reason the cockpit POC proved live rebuild
had to happen in-process. This module is only for an explicit, occasional
"build in Blender" action, and runs in a background thread so it can't
block the FastAPI event loop / other requests while Blender is running.

Reuses logic/blender_demo.py's already-proven executable lookup (BLENDER_PATH
env var -> common install-path candidates, including the exact Blender 5.0
install found on this machine -> bare "blender" relying on PATH) instead of
re-deriving it -- same reasoning as anywhere else in this project that
avoids re-solving an already-solved problem.
"""
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

from logic.blender_demo import BLENDER_BIN

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(BASE_DIR, "blender", "pershing_headless_build.py")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "blender_headless")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# "Export Current View" (Viewport.jsx) -- user asked (2026-07-17) for the
# Line Art SVG to land here automatically, no browser download/dialog.
# OUTPUT_DIR above stays the canonical write target (it's what
# /blender-headless-output serves for LineArtOverlay.jsx's preview <img>);
# this is a same-content copy alongside it, not a replacement.
REMIXED_SVG_DIR = os.path.join(BASE_DIR, "data", "PershingMetabolizer", "parkSVG", "remixedGeneratedSVGs")
os.makedirs(REMIXED_SVG_DIR, exist_ok=True)

# In-memory job store -- same "local single-user dev tool, no persistence
# needed yet" pattern logic/pershing_api.py already uses for its own grid
# state. Plain dict is fine: CPython's GIL makes single-key get/set atomic,
# and the only writer is this module's own background thread.
_JOBS = {}

DEFAULT_TIMEOUT_S = 180

# Two --background Blender processes launched at once contend for the same
# CPU/disk and both slow down -- confirmed empirically: a build that takes
# ~2s in isolation hit the full 180s timeout when a second one was kicked
# off seconds later. One Blender build at a time is plenty for a live
# design session (nobody needs two full-fidelity exports racing), so a
# non-blocking lock is enough: a second request while one's running fails
# immediately with a clear reason instead of silently contending.
_BUILD_LOCK = threading.Lock()


def _run_build(job_id, input_path, output_path, svg_path, timeout, view_dir=None, include_real_context=False):
    _JOBS[job_id]["status"] = "running"
    t0 = time.time()
    try:
        args = [BLENDER_BIN, "--background", "--factory-startup", "--python", SCRIPT_PATH, "--",
                "--input", input_path, "--output", output_path]
        if svg_path is not None:
            args += ["--lineart-output", svg_path]
            # view_dir/include_real_context only mean anything alongside a
            # Line Art export -- silently ignored (not an error) if lineart
            # wasn't requested, matching --lineart-output's own "optional
            # and additive" framing in pershing_headless_build.py's docstring.
            if view_dir is not None:
                # --view-dir=VALUE (single token), NOT ["--view-dir", VALUE]
                # (two tokens) -- a view direction with a negative
                # component (e.g. "-0.2,-0.98,0.09", a real camera angle
                # hit during browser testing) makes argparse misparse the
                # two-token form: it sees a token starting with "-"
                # immediately after --view-dir and concludes no value was
                # given at all ("expected one argument"), even though
                # subprocess.run's list form never touches a shell. The
                # single "--flag=value" token sidesteps that ambiguity
                # entirely, since argparse always treats an "="-joined
                # token as one unit regardless of what follows the "=".
                args += ["--view-dir=" + ",".join(str(v) for v in view_dir)]
            if include_real_context:
                args += ["--include-real-context"]
        try:
            result = subprocess.run(
                # --factory-startup: skip this machine's user addon profile
                # entirely. Confirmed empirically (2026-07-07) to be the
                # difference between a build finishing in ~2s and one
                # hanging the full timeout -- this profile has a broken
                # addon (meshgen, ModuleNotFoundError: smolagents) and the
                # BlenderMCP addon, which auto-registers/unregisters a
                # socket server on every launch (see its stdout lines);
                # neither is needed for a pure geometry-build-and-export
                # job, and loading them turned out to be an unreliable
                # source of multi-minute hangs, not just wasted time.
                args,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            _JOBS[job_id].update(status="error", error=f"Blender timed out after {timeout}s")
            return
        except FileNotFoundError:
            _JOBS[job_id].update(
                status="error",
                error=f"Blender not found at '{BLENDER_BIN}'. Set BLENDER_PATH in your .env file.",
            )
            return

        duration = round(time.time() - t0, 1)

        if result.returncode != 0:
            _JOBS[job_id].update(
                status="error",
                error=f"Blender exited {result.returncode}.\nstderr: {result.stderr[-2000:]}",
                duration_s=duration,
            )
            return

        if not os.path.exists(output_path):
            _JOBS[job_id].update(
                status="error",
                error=f"Blender ran OK but no OBJ was written.\nstdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-2000:]}",
                duration_s=duration,
            )
            return

        # svg_path is requested but missing -- report as an error rather
        # than silently returning "done" with svg_url=None, since the user
        # explicitly asked for Line Art and would otherwise not notice it
        # didn't happen.
        if svg_path is not None and not os.path.exists(svg_path):
            _JOBS[job_id].update(
                status="error",
                error=f"Blender ran OK and wrote the OBJ, but no Line Art SVG was written.\nstdout: {result.stdout[-1000:]}\nstderr: {result.stderr[-2000:]}",
                duration_s=duration,
            )
            return

        if svg_path is not None:
            shutil.copy2(svg_path, os.path.join(REMIXED_SVG_DIR, os.path.basename(svg_path)))

        filename = os.path.basename(output_path)
        svg_url = f"/blender-headless-output/{os.path.basename(svg_path)}" if svg_path is not None else None
        _JOBS[job_id].update(
            status="done",
            obj_url=f"/blender-headless-output/{filename}",
            svg_url=svg_url,
            duration_s=duration,
        )
        print(f"[pershing_blender] job {job_id} done in {duration}s -> {output_path}"
              + (f" (+ Line Art -> {svg_path})" if svg_path is not None else ""))
    finally:
        # Always release, even on an unexpected exception above -- an
        # unreleased lock would permanently wedge every future build
        # behind a job that already finished (in error or otherwise).
        _BUILD_LOCK.release()


def start_build_job(payload: dict, timeout: int = DEFAULT_TIMEOUT_S, lineart: bool = False,
                     view_dir=None, include_real_context: bool = False) -> str:
    """Kicks off a headless Blender build in a background thread and
    returns immediately with a job id -- the caller (FastAPI route) polls
    get_job() for status instead of blocking the request on the subprocess.

    lineart=True additionally passes --lineart-output to the same Blender
    subprocess (see pershing_headless_build.py's build_line_art()) -- one
    process, one build, not a second subprocess launch, since the mesh is
    already in memory there.

    view_dir (2026-07-11, vector-export use): an (x, y, z) sequence
    threaded through to --view-dir, letting a live browser camera angle
    drive the Line Art projection instead of always the one hardcoded
    isometric default. include_real_context threads through to
    --include-real-context, additionally line-arting the real columns/
    slabs (as lightweight primitives, not the heavy Rhino OBJ -- see
    build_real_context_meshes' docstring) -- never included in the OBJ
    export itself, only the Line Art SVG.

    Acquired here (main thread), released in _run_build (background
    thread) once that job actually finishes -- threading.Lock has no
    per-thread ownership requirement, so that split is safe."""
    job_id = uuid.uuid4().hex[:12]

    if not _BUILD_LOCK.acquire(blocking=False):
        _JOBS[job_id] = {
            "status": "error", "obj_url": None, "svg_url": None,
            "error": "a Blender build is already running -- wait for it to finish before starting another",
            "duration_s": None,
        }
        return job_id

    input_path = os.path.join(OUTPUT_DIR, f"input_{job_id}.json")
    output_path = os.path.join(OUTPUT_DIR, f"pershing_{job_id}.obj")
    svg_path = os.path.join(OUTPUT_DIR, f"pershing_{job_id}.svg") if lineart else None

    with open(input_path, "w") as f:
        json.dump(payload, f)

    _JOBS[job_id] = {"status": "queued", "obj_url": None, "svg_url": None, "error": None, "duration_s": None}
    thread = threading.Thread(
        target=_run_build,
        args=(job_id, input_path, output_path, svg_path, timeout),
        kwargs={"view_dir": view_dir, "include_real_context": include_real_context},
        daemon=True,
    )
    thread.start()
    return job_id


def get_job(job_id: str):
    return _JOBS.get(job_id)
