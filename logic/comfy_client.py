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

COMFY_URL   = "http://127.0.0.1:8188"
COMFY_OUTPUT = r"C:\ComfyUI_windows_portable\ComfyUI\output"
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

            # Walk all node outputs to find a file matching expected_ext
            outputs = job.get("outputs", {})
            for node_id, node_out in outputs.items():
                # Images output: {"images": [{"filename": ..., "subfolder": ..., "type": "output"}]}
                for img in node_out.get("images", []):
                    fn = img.get("filename", "")
                    if fn.lower().endswith(expected_ext):
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
