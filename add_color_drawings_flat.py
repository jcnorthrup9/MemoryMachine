"""
Renders a color-style categorized site plan for every existing
outputs/batchExport/iter{N:03d}/ folder, same as add_color_drawing.py, but
writes them flat into outputs/batchExport/colorDiagrams/ as
iter{N:03d}_color.png instead of into each iteration's own folder -- for
side-by-side browsing/comparison of the whole batch's diagrams without
opening 190 separate folders.

Runs each iteration in its own subprocess for the same reasons
batch_export_worker.py does (isolation, never touches outputs/cockpit/
web_paint_state.json -- see that file's own SAFETY note, identical here).

Usage: python add_color_drawings_flat.py [OUT_DIR]  (default outputs/batchExport)
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "outputs", "batchExport")
WORKER = os.path.join(REPO_ROOT, "add_color_drawing_worker.py")
TIMEOUT_S = 300
INTER_LAUNCH_DELAY_S = 1.0
MAX_ATTEMPTS = 3


def _run_once(iter_dir, out_file):
    cmd = [sys.executable, WORKER, "--iter-dir", iter_dir, "--out-file", out_file]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, timeout=TIMEOUT_S, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return False, None, f"TIMED OUT after {TIMEOUT_S}s"
    ok = result.returncode == 0 and os.path.exists(out_file)
    return ok, result, None if ok else f"exit {result.returncode}"


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR
    color_dir = os.path.join(out_dir, "colorDiagrams")
    os.makedirs(color_dir, exist_ok=True)

    iter_names = sorted(
        name for name in os.listdir(out_dir)
        if name.startswith("iter") and os.path.isfile(os.path.join(out_dir, name, "params.json"))
    )

    ok_count = 0
    fail_count = 0
    for name in iter_names:
        iter_dir = os.path.join(out_dir, name)
        out_file = os.path.join(color_dir, f"{name}_color.png")
        ok = False
        result = None
        fail_reason = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ok, result, fail_reason = _run_once(iter_dir, out_file)
            if ok:
                break
            print(f"{name}: attempt {attempt}/{MAX_ATTEMPTS} failed ({fail_reason})")
            time.sleep(INTER_LAUNCH_DELAY_S * 2)

        if ok:
            print(f"{name}: OK")
            ok_count += 1
        else:
            print(f"{name}: FAILED after {MAX_ATTEMPTS} attempts ({fail_reason})")
            if result is not None and result.stderr and result.stderr.strip():
                print(result.stderr.strip()[-2000:])
            fail_count += 1
        time.sleep(INTER_LAUNCH_DELAY_S)

    print(f"\n{ok_count}/{len(iter_names)} color drawings written to {color_dir}, {fail_count}/{len(iter_names)} failed.")


if __name__ == "__main__":
    main()
