"""
MEMORY MACHINE // COMFY CLIENT
Handles all communication with the local ComfyUI instance.
ComfyUI default: http://localhost:8188

Usage (test standalone):
    cd d:/MemoryMachine
    python -c "from logic.comfy_client import ping; print(ping())"
"""

import json
import time
import uuid
import urllib.request
import urllib.error
import os

COMFY_URL   = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")


def _resolve_comfy_output():
    """Locate ComfyUI's output directory instead of hardcoding one drive.

    This was pinned to C:\\ComfyUI_windows_portable, but the install on at
    least one of the Syncthing-synced machines is on D:, so poll_for_output()
    below was returning paths that do not exist -- silently breaking
    /api/comfy-render and /api/comfy-text-to-3d, which both depend on it.
    logic/bake_to_blender.py had already hit this and grown its own D:-then-C:
    fallback (lines 9-11); this is the same fix, applied where the rest of
    the codebase actually reads from, plus an env override for anyone whose
    install is somewhere else entirely.
    """
    env = os.environ.get("COMFY_OUTPUT_DIR")
    if env:
        return env
    candidates = [
        r"D:\ComfyUI_windows_portable\ComfyUI\output",
        r"C:\ComfyUI_windows_portable\ComfyUI\output",
        # NVIDIA's own portable build (comfyanonymous's Windows+CUDA bundle,
        # distinct from the plain ComfyUI_windows_portable dir above) nests
        # an extra ComfyUI_windows_portable level under this folder -- found
        # 2026-08-21 on a machine with no D: drive at all, where every
        # candidate above missed and the old code fell through to a
        # hardcoded D:\ path, crashing os.makedirs() with WinError 3 on a
        # drive that doesn't exist.
        r"C:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\output",
        os.path.expanduser(r"~\ComfyUI\output"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def _resolve_comfy_input():
    """Same fix as _resolve_comfy_output() above, for ComfyUI's input/
    folder (where /api/comfy-render writes the capture LoadImage reads
    back) -- was hardcoded to C:\\ComfyUI_windows_portable, breaking on
    any machine whose install lives elsewhere."""
    env = os.environ.get("COMFY_INPUT_DIR")
    if env:
        return env
    candidates = [
        r"D:\ComfyUI_windows_portable\ComfyUI\input",
        r"C:\ComfyUI_windows_portable\ComfyUI\input",
        # See the matching comment in _resolve_comfy_output() above.
        r"C:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI\input",
        os.path.expanduser(r"~\ComfyUI\input"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


COMFY_OUTPUT = _resolve_comfy_output()
COMFY_INPUT = _resolve_comfy_input()
POLL_INTERVAL = 2.0   # seconds between status checks
POLL_TIMEOUT  = 300   # seconds before giving up


def ping() -> bool:
    """Check if ComfyUI is reachable. Returns True/False."""
    try:
        req = urllib.request.Request(f"{COMFY_URL}/system_stats")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        print(f"[COMFY] Ping failed: {e}")
        return False


def queue_workflow(workflow: dict) -> str | None:
    """
    POST a workflow to ComfyUI's queue.
    Returns the prompt_id string, or None on failure.
    """
    client_id = str(uuid.uuid4())
    payload = json.dumps({
        "prompt": workflow,
        "client_id": client_id
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{COMFY_URL}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            prompt_id = data.get("prompt_id")
            print(f"[COMFY] Queued prompt_id: {prompt_id}")
            return prompt_id
    except Exception as e:
        print(f"[COMFY] Queue error: {e}")
        return None


def poll_for_output(prompt_id: str, expected_ext: str = ".glb") -> str | None:
    """
    Polls ComfyUI /history/{prompt_id} until the job completes.
    Returns the absolute path to the output file, or None on timeout/error.

    expected_ext: ".glb" for 3D, ".png"/".jpg" for images
    """
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            req = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
            with urllib.request.urlopen(req, timeout=10) as r:
                history = json.loads(r.read().decode("utf-8"))

            if prompt_id not in history:
                continue  # not done yet

            job = history[prompt_id]

            # Check for execution errors
            if job.get("status", {}).get("status_str") == "error":
                msgs = job.get("status", {}).get("messages", [])
                print(f"[COMFY] Execution error: {msgs}")
                return None

            # Walk all node outputs to find a file matching expected_ext.
            # A workflow can wire the same generation into both a SaveImage
            # node (type "output", lands under COMFY_OUTPUT, permanent) and
            # a PreviewImage node (type "temp", lands in ComfyUI's sibling
            # temp/ dir, cleared periodically, NOT under COMFY_OUTPUT) --
            # e.g. flux1dev.json does exactly this (nodes 136/173). dict
            # iteration order isn't guaranteed to put the real output first,
            # and the app's /comfy-output static mount only serves
            # COMFY_OUTPUT, so a "temp"-type match must never be returned --
            # doing so used to produce a URL that 404s (found 2026-08-21).
            # Only "output"-type images are eligible; a workflow with no
            # SaveImage node correctly times out below instead.
            outputs = job.get("outputs", {})
            for node_id, node_out in outputs.items():
                # Images output: {"images": [{"filename": ..., "subfolder": ..., "type": "output"}]}
                for img in node_out.get("images", []):
                    fn = img.get("filename", "")
                    if img.get("type") != "output" or not fn.lower().endswith(expected_ext):
                        continue
                    subfolder = img.get("subfolder", "")
                    full_path = os.path.join(COMFY_OUTPUT, subfolder, fn)
                    print(f"[COMFY] Output found: {full_path}")
                    return full_path

                # Mesh/GLB output — ComfyUI uses "3d" key for SaveGLB node output
                for key in ("mesh", "3d"):
                    for mesh in node_out.get(key, []):
                        fn = mesh.get("filename", "")
                        if fn.lower().endswith(expected_ext):
                            subfolder = mesh.get("subfolder", "mesh")
                            full_path = os.path.join(COMFY_OUTPUT, subfolder, fn)
                            print(f"[COMFY] {key} output found: {full_path}")
                            return full_path

        except Exception as e:
            print(f"[COMFY] Poll error: {e}")

    print(f"[COMFY] Timed out waiting for prompt_id: {prompt_id}")
    return None


def load_workflow(json_path: str) -> dict:
    """Load a workflow JSON from disk."""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def patch_workflow(workflow: dict, patches: dict) -> dict:
    """
    Apply patches to specific nodes in a workflow.
    patches format: { "node_id": { "input_key": new_value } }

    Example:
        patch_workflow(wf, {
            "9": {"text": "a serene water garden"},
            "11": {"width": 1024, "height": 1024}
        })
    """
    import copy
    wf = copy.deepcopy(workflow)
    for node_id, inputs in patches.items():
        if node_id in wf:
            for key, value in inputs.items():
                wf[node_id]["inputs"][key] = value
        else:
            print(f"[COMFY] Warning: node '{node_id}' not found in workflow")
    return wf
