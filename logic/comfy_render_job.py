"""
logic/comfy_render_job.py
--------------------------
Async wrapper around comfy_client's "3D scene capture -> Flux Kontext
render" call -- same reasoning as logic/pershing_blender.py's job-queue
wrapper around the headless-Blender build: a ComfyUI render can take up to
POLL_TIMEOUT (comfy_client.py, currently 300s) to come back, so it has no
business blocking a FastAPI request/response cycle. Runs in a background
thread and returns a job id immediately; the caller polls get_job().

This is the same body app.py's /api/comfy-render route used to run
synchronously (see git history) -- moved here unchanged apart from using
comfy_client's env-aware COMFY_INPUT instead of a hardcoded drive letter.
"""
import base64
import os
import shutil
import threading
import time
import uuid

from logic.comfy_client import (
    COMFY_INPUT, COMFY_OUTPUT, ping, load_workflow, patch_workflow, queue_workflow, poll_for_output,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_PATH = os.path.join(BASE_DIR, "data", "comfy", "flux1dev.json")

# Durable repo-side copy of finished renders -- ComfyUI's own output/ folder
# is the only place these lived before (2026-08-21), which means they don't
# survive a ComfyUI reinstall/reset and don't show up anywhere in this repo's
# own archive. Same sibling-folder pattern as the "Export Current View"
# PNG/SVG exports (PERSHING_EXPORT_PNG_DIR in app.py, REMIXED_SVG_DIR in
# pershing_blender.py) -- one more remixedGenerated* folder alongside them.
REMIXED_RENDER_DIR = os.path.join(BASE_DIR, "data", "PershingMetabolizer", "parkSVG", "remixedGeneratedRenders")
os.makedirs(REMIXED_RENDER_DIR, exist_ok=True)

# Same "plain dict, single background writer" reasoning as pershing_blender.py's _JOBS.
_JOBS = {}


def _run_render(job_id, image_b64, narrative):
    # Any uncaught exception here previously killed the thread silently,
    # leaving the job wedged at "running" forever with no way for the
    # polling client to ever learn it failed (found 2026-08-21: an
    # os.makedirs() WinError on a path resolution bug did exactly this).
    # Wrapping the whole body guarantees every exit path sets a terminal
    # status.
    try:
        _run_render_body(job_id, image_b64, narrative)
    except Exception as e:
        import traceback
        print(f"[COMFY] Render job {job_id} crashed: {traceback.format_exc()}")
        _JOBS[job_id].update(status="error", error=str(e))


def _run_render_body(job_id, image_b64, narrative):
    _JOBS[job_id]["status"] = "running"

    if not ping():
        _JOBS[job_id].update(status="error", error="ComfyUI not reachable at 127.0.0.1:8188")
        return

    if not os.path.exists(WORKFLOW_PATH):
        _JOBS[job_id].update(status="error", error=f"Workflow not found: {WORKFLOW_PATH}")
        return

    os.makedirs(COMFY_INPUT, exist_ok=True)
    temp_filename = f"mm_capture_{int(time.time() * 1000)}.png"
    temp_path = os.path.join(COMFY_INPUT, temp_filename)

    try:
        img_data = image_b64
        if "," in img_data:
            img_data = img_data.split(",", 1)[1]
        with open(temp_path, "wb") as f:
            f.write(base64.b64decode(img_data))
    except Exception as e:
        _JOBS[job_id].update(status="error", error=f"Bad image data: {e}")
        return

    workflow = load_workflow(WORKFLOW_PATH)

    full_prompt = (
        f"{narrative}. "
        "Architectural visualization, urban park, golden hour lighting, "
        "photorealistic render, high detail, cinematic composition."
    )

    patched = patch_workflow(workflow, {
        "6": {"text": full_prompt},  # Positive prompt
    })
    # Node 142 ships as LoadImageOutput (loads from ComfyUI's own output/
    # folder) -- swapped to LoadImage here since we're feeding it a fresh
    # capture written into input/, not a prior ComfyUI output.
    patched["142"]["class_type"] = "LoadImage"
    patched["142"]["inputs"] = {"image": temp_filename}

    prompt_id = queue_workflow(patched)
    if not prompt_id:
        _JOBS[job_id].update(status="error", error="Failed to queue render workflow")
        return

    img_path = poll_for_output(prompt_id, ".png")
    if not img_path:
        img_path = poll_for_output(prompt_id, ".jpg")

    if not img_path:
        _JOBS[job_id].update(status="error", error="Timed out waiting for render output")
        return

    rel_path = os.path.relpath(img_path, COMFY_OUTPUT)

    archived_path = os.path.join(REMIXED_RENDER_DIR, f"comfy_render_{job_id}_{os.path.basename(img_path)}")
    try:
        shutil.copy2(img_path, archived_path)
    except Exception as e:
        # Archiving is a nice-to-have, not the point of the job -- the
        # render already succeeded and image_url already works, so a copy
        # failure (disk full, permissions) shouldn't flip a finished job to
        # "error".
        print(f"[COMFY] Warning: failed to archive render to {archived_path}: {e}")
        archived_path = None

    _JOBS[job_id].update(
        status="done",
        image_url=f"/comfy-output/{rel_path.replace(os.sep, '/')}",
        archived_path=archived_path,
    )


def start_render_job(image_b64: str, narrative: str) -> str:
    """Kicks off a ComfyUI render in a background thread and returns
    immediately with a job id -- the caller (FastAPI route) polls get_job()
    for status instead of blocking the request on the ComfyUI poll loop.
    No lock like pershing_blender.py's _BUILD_LOCK: ComfyUI has its own
    server-side queue, so multiple in-flight render jobs here just queue up
    on ComfyUI's end rather than contending locally."""
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {"status": "queued", "image_url": None, "error": None, "archived_path": None}
    thread = threading.Thread(target=_run_render, args=(job_id, image_b64, narrative), daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str):
    return _JOBS.get(job_id)
