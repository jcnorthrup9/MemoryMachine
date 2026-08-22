"""
logic/comfy_render_job.py
--------------------------
Async wrapper around comfy_client's "3D scene capture -> ComfyUI render"
call -- same reasoning as logic/pershing_blender.py's job-queue wrapper
around the headless-Blender build: a ComfyUI render can take up to
POLL_TIMEOUT (comfy_client.py, currently 300s) to come back, so it has no
business blocking a FastAPI request/response cycle. Runs in a background
thread and returns a job id immediately; the caller polls get_job().

Three workflows live here:
  - _run_flux2_render_body (FLUX2_WORKFLOW_PATH, flux2_klein_depth.json) --
    the ACTIVE one (see _run_render_body's dispatch below), added
    2026-08-22 to replace Flux.1 as the default: Flux.1's outputs were
    reported "too loose" -- plausible-looking but not structurally
    grounded in the actual depth signal, uncanny in a way that isn't
    appropriate for this project. Uses FLUX.2 Klein 9B (kv/image-edit
    variant, fp8) + its Qwen3-8B text encoder, official Comfy-Org
    reference-latent pattern (single reference image = our depth capture,
    no external depth-ESTIMATION model needed since we already have a
    true depth render). Needs flux-2-klein-9b-kv-fp8.safetensors (~9.15GB)
    + qwen_3_8b_fp8mixed.safetensors (~8.07GB) -- both a real download,
    not bundled with a stock ComfyUI install.
  - _run_depth_render_body (DEPTH_WORKFLOW_PATH, flux1_depth_lora.json) --
    the Flux.1 depth-lora pipeline this feature launched the depth-capture
    approach with (2026-08-21/22). Kept working and unused rather than
    deleted -- swap _run_render_body's dispatch back to this one if
    Flux.2's extra VRAM/download cost isn't worth it for a given session;
    only needs flux1-dev.safetensors (23.8GB, already resident) +
    flux1-depth-dev-lora.safetensors.
  - _run_kontext_render_body (KONTEXT_WORKFLOW_PATH, flux1dev.json) -- the
    ORIGINAL workflow this feature launched with (2026-08-21), takes the
    plain color capture through Flux Kontext, no depth capture at all.
    Kept working and unused; only needs the lighter fp8 Kontext checkpoint.
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
KONTEXT_WORKFLOW_PATH = os.path.join(BASE_DIR, "data", "comfy", "flux1dev.json")
DEPTH_WORKFLOW_PATH = os.path.join(BASE_DIR, "data", "comfy", "flux1_depth_lora.json")
FLUX2_WORKFLOW_PATH = os.path.join(BASE_DIR, "data", "comfy", "flux2_klein_depth.json")

REALISM_SUFFIX = (
    "Architectural visualization, urban park, golden hour lighting, "
    "photorealistic render, high detail, cinematic composition."
)

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


def _decode_data_url(data_url: str) -> bytes:
    data = data_url
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


def _run_render(job_id, image_b64, depth_b64, narrative):
    # Any uncaught exception here previously killed the thread silently,
    # leaving the job wedged at "running" forever with no way for the
    # polling client to ever learn it failed (found 2026-08-21: an
    # os.makedirs() WinError on a path resolution bug did exactly this).
    # Wrapping the whole body guarantees every exit path sets a terminal
    # status.
    try:
        _run_render_body(job_id, image_b64, depth_b64, narrative)
    except Exception as e:
        import traceback
        print(f"[COMFY] Render job {job_id} crashed: {traceback.format_exc()}")
        _JOBS[job_id].update(status="error", error=str(e))


def _run_render_body(job_id, image_b64, depth_b64, narrative):
    # See this module's docstring -- swap this one line to
    # _run_depth_render_body(...) for the Flux.1 depth-lora pipeline, or
    # _run_kontext_render_body(job_id, image_b64, narrative) for the
    # original no-depth pipeline.
    _run_flux2_render_body(job_id, image_b64, depth_b64, narrative)


def _archive_source_capture(job_id, image_b64):
    """Best-effort archive of the raw color capture (not sent to ComfyUI in
    the depth pipeline, but wanted alongside the render for the deck's
    before/after crossfade and general record-keeping). Failure here is
    non-fatal -- same reasoning as the render archive copy below."""
    if not image_b64:
        return None
    try:
        source_path = os.path.join(REMIXED_RENDER_DIR, f"comfy_render_{job_id}_source.png")
        with open(source_path, "wb") as f:
            f.write(_decode_data_url(image_b64))
        return source_path
    except Exception as e:
        print(f"[COMFY] Warning: failed to archive source capture for job {job_id}: {e}")
        return None


def _run_flux2_render_body(job_id, image_b64, depth_b64, narrative):
    """FLUX.2 Klein 9B (kv/image-edit variant), conditioned on our own
    depth capture via ReferenceLatent -- see module docstring. Node "5" is
    CLIPTextEncode (the prompt), node "7" is the LoadImage the depth
    capture gets written into (same COMFY_INPUT write pattern as the
    Flux.1 depth pipeline below)."""
    _JOBS[job_id]["status"] = "running"

    if not ping():
        _JOBS[job_id].update(status="error", error="ComfyUI not reachable at 127.0.0.1:8188")
        return

    if not os.path.exists(FLUX2_WORKFLOW_PATH):
        _JOBS[job_id].update(status="error", error=f"Workflow not found: {FLUX2_WORKFLOW_PATH}")
        return

    if not depth_b64:
        _JOBS[job_id].update(status="error", error="No depth capture provided (depth_b64 missing)")
        return

    _archive_source_capture(job_id, image_b64)

    os.makedirs(COMFY_INPUT, exist_ok=True)
    depth_filename = f"mm_depth_{int(time.time() * 1000)}.png"
    depth_path = os.path.join(COMFY_INPUT, depth_filename)

    try:
        with open(depth_path, "wb") as f:
            f.write(_decode_data_url(depth_b64))
    except Exception as e:
        _JOBS[job_id].update(status="error", error=f"Bad depth image data: {e}")
        return

    workflow = load_workflow(FLUX2_WORKFLOW_PATH)
    full_prompt = f"{narrative}. {REALISM_SUFFIX}"

    patched = patch_workflow(workflow, {
        "5": {"text": full_prompt},        # CLIPTextEncode positive prompt
        "7": {"image": depth_filename},    # LoadImage -- the depth-pass capture
    })

    prompt_id = queue_workflow(patched)
    if not prompt_id:
        _JOBS[job_id].update(status="error", error="Failed to queue render workflow")
        return

    img_path = poll_for_output(prompt_id, ".png")
    if not img_path:
        _JOBS[job_id].update(status="error", error="Timed out waiting for render output")
        return

    _finish_job(job_id, img_path)


def _run_depth_render_body(job_id, image_b64, depth_b64, narrative):
    _JOBS[job_id]["status"] = "running"

    if not ping():
        _JOBS[job_id].update(status="error", error="ComfyUI not reachable at 127.0.0.1:8188")
        return

    if not os.path.exists(DEPTH_WORKFLOW_PATH):
        _JOBS[job_id].update(status="error", error=f"Workflow not found: {DEPTH_WORKFLOW_PATH}")
        return

    if not depth_b64:
        _JOBS[job_id].update(status="error", error="No depth capture provided (depth_b64 missing)")
        return

    _archive_source_capture(job_id, image_b64)

    os.makedirs(COMFY_INPUT, exist_ok=True)
    depth_filename = f"mm_depth_{int(time.time() * 1000)}.png"
    depth_path = os.path.join(COMFY_INPUT, depth_filename)

    try:
        with open(depth_path, "wb") as f:
            f.write(_decode_data_url(depth_b64))
    except Exception as e:
        _JOBS[job_id].update(status="error", error=f"Bad depth image data: {e}")
        return

    workflow = load_workflow(DEPTH_WORKFLOW_PATH)
    full_prompt = f"{narrative}. {REALISM_SUFFIX}"

    patched = patch_workflow(workflow, {
        "3": {"text": full_prompt},        # CLIPTextEncode positive prompt
        "6": {"image": depth_filename},    # LoadImage -- the depth-pass capture
    })

    prompt_id = queue_workflow(patched)
    if not prompt_id:
        _JOBS[job_id].update(status="error", error="Failed to queue render workflow")
        return

    img_path = poll_for_output(prompt_id, ".png")
    if not img_path:
        _JOBS[job_id].update(status="error", error="Timed out waiting for render output")
        return

    _finish_job(job_id, img_path)


def _run_kontext_render_body(job_id, image_b64, narrative):
    """Original Flux Kontext pipeline (2026-08-21) -- see module docstring.
    Not called by default; kept working as a fallback."""
    _JOBS[job_id]["status"] = "running"

    if not ping():
        _JOBS[job_id].update(status="error", error="ComfyUI not reachable at 127.0.0.1:8188")
        return

    if not os.path.exists(KONTEXT_WORKFLOW_PATH):
        _JOBS[job_id].update(status="error", error=f"Workflow not found: {KONTEXT_WORKFLOW_PATH}")
        return

    os.makedirs(COMFY_INPUT, exist_ok=True)
    temp_filename = f"mm_capture_{int(time.time() * 1000)}.png"
    temp_path = os.path.join(COMFY_INPUT, temp_filename)

    try:
        with open(temp_path, "wb") as f:
            f.write(_decode_data_url(image_b64))
    except Exception as e:
        _JOBS[job_id].update(status="error", error=f"Bad image data: {e}")
        return

    workflow = load_workflow(KONTEXT_WORKFLOW_PATH)
    full_prompt = f"{narrative}. {REALISM_SUFFIX}"

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

    _finish_job(job_id, img_path)


def _finish_job(job_id, img_path):
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


def start_render_job(image_b64: str, depth_b64: str, narrative: str) -> str:
    """Kicks off a ComfyUI render in a background thread and returns
    immediately with a job id -- the caller (FastAPI route) polls get_job()
    for status instead of blocking the request on the ComfyUI poll loop.
    No lock like pershing_blender.py's _BUILD_LOCK: ComfyUI has its own
    server-side queue, so multiple in-flight render jobs here just queue up
    on ComfyUI's end rather than contending locally."""
    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {"status": "queued", "image_url": None, "error": None, "archived_path": None}
    thread = threading.Thread(target=_run_render, args=(job_id, image_b64, depth_b64, narrative), daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str):
    return _JOBS.get(job_id)
