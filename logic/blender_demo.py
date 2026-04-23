"""
logic/blender_demo.py
─────────────────────
Headless Blender runner for Demo Mode.
Replaces the ComfyUI text-to-3D pipeline with a fast deterministic Blender call.

Called by POST /api/demo-generate in app.py.

Env vars (all optional — sensible defaults set below):
  BLENDER_PATH           path to blender.exe  (default: searches PATH then common installs)
  GENERATOR_SCRIPT_PATH  path to pershing_square_generator.py
  BLENDER_OUTPUT_DIR     where to write the STL  (default: <project>/output/blender)
"""

import os
import sys
import subprocess
import tempfile
import time
import textwrap
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent   # D:\MemoryMachine\

# ── Locate blender.exe ────────────────────────────────────────────────
def _find_blender() -> str:
    if (p := os.environ.get("BLENDER_PATH")):
        return p
    candidates = [
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
        r"D:\Blender\blender.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "blender"   # fallback — relies on PATH


BLENDER_BIN    = _find_blender()
GENERATOR_PATH = os.environ.get(
    "GENERATOR_SCRIPT_PATH",
    str(BASE_DIR / "pershing_square_generator.py")
)
OUTPUT_DIR = os.environ.get(
    "BLENDER_OUTPUT_DIR",
    str(BASE_DIR / "output" / "blender")
)


def run_blender_demo(
    svg_path: str = "",
    dense_hills: bool = True,
    height_scale: float = 1.0,
    trunk_r: float = 0.65,
    option_name: str = "Demo",
    timeout: int = 120,
) -> dict:
    """
    Runs pershing_square_generator.py in Blender headless mode.

    Returns:
        {
          "status": "success",
          "stl_path": "D:/MemoryMachine/output/blender/Demo.stl",
          "stl_url":  "/blender-output/Demo.stl",   ← served by FastAPI static mount
          "duration_s": 14.2
        }
    or raises RuntimeError on failure.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = int(time.time() * 1000)
    stl_filename = f"{option_name}_{timestamp}.stl"
    stl_path = os.path.join(OUTPUT_DIR, stl_filename)

    # Build a thin wrapper that injects parameters then calls build_park()
    # Uses double-quoted strings throughout to avoid backslash collisions in the f-string.
    gen_dir = os.path.dirname(GENERATOR_PATH).replace("\\", "/")
    gen_path = GENERATOR_PATH.replace("\\", "/")
    stl_path_fwd = stl_path.replace("\\", "/")
    wrapper = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, r"{gen_dir}")

        import importlib.util
        spec = importlib.util.spec_from_file_location("generator", r"{gen_path}")
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mod.build_park(
            option_name  = {repr(option_name)},
            svg_path     = r"{svg_path}",
            dense_hills  = {dense_hills},
            height_scale = {height_scale},
            trunk_r      = {trunk_r},
        )

        # Export STL directly from mesh data — works in --background, any Blender version
        import bpy, struct
        out = r"{stl_path_fwd}"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            triangles = []
            for obj in bpy.data.objects:
                if obj.type != "MESH":
                    continue
                obj_eval = obj.evaluated_get(depsgraph)
                me = obj_eval.to_mesh()
                me.calc_loop_triangles()
                mat = obj.matrix_world
                mat3 = mat.to_3x3().normalized()
                for tri in me.loop_triangles:
                    verts = [mat @ me.vertices[vi].co for vi in tri.vertices]
                    normal = mat3 @ tri.normal
                    triangles.append((normal, verts))
                obj_eval.to_mesh_clear()
            with open(out, "wb") as f:
                header = b"MemoryMachine STL export"
                f.write(header + bytes(80 - len(header)))
                f.write(struct.pack("<I", len(triangles)))
                for normal, verts in triangles:
                    f.write(struct.pack("<fff", normal.x, normal.y, normal.z))
                    for v in verts:
                        f.write(struct.pack("<fff", v.x, v.y, v.z))
                    f.write(struct.pack("<H", 0))
            print("BLENDER_DONE:" + out)
        except Exception as e:
            import traceback
            print("STL_EXPORT_FAILED:", traceback.format_exc())
    """)

    # Write wrapper to system temp dir (not the project tree) so uvicorn --reload
    # doesn't detect the file and restart the server mid-execution.
    import tempfile
    fd, wrapper_path = tempfile.mkstemp(suffix="_blender_wrapper.py", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(wrapper)

    t0 = time.time()
    try:
        result = subprocess.run(
            [BLENDER_BIN, "--background", "--python", wrapper_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Blender timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(
            f"Blender not found at '{BLENDER_BIN}'. "
            "Set BLENDER_PATH in your .env file."
        )
    finally:
        if os.path.exists(wrapper_path):
            os.remove(wrapper_path)

    duration = round(time.time() - t0, 1)

    if result.returncode != 0:
        raise RuntimeError(
            f"Blender exited {result.returncode}.\n"
            f"stderr: {result.stderr[-2000:]}"
        )

    if not os.path.exists(stl_path):
        raise RuntimeError(
            f"Blender ran OK but STL not found at {stl_path}.\n"
            f"stdout: {result.stdout[-1000:]}\n"
            f"stderr: {result.stderr[-2000:]}"
        )

    print(f"[BlenderDemo] Done in {duration}s → {stl_path}")

    return {
        "status":    "success",
        "stl_path":  stl_path,
        "stl_url":   f"/blender-output/{stl_filename}",
        "duration_s": duration,
    }
