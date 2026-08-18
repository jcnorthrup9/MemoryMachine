"""
Adds a color-style categorized site plan (color.png) to each existing
outputs/batchExport/iter{N:03d}/ folder, reproducing that iteration's exact
design from its already-saved params.json (rebuild_params + spatial_seed)
rather than regenerating a fresh random one -- guarantees color.png matches
the plan/axo/long_section already sitting in that same folder, and skips
re-writing those (no need, they're untouched by this).

Runs each iteration in its own subprocess for the same reasons
batch_export_worker.py does (isolation, never touches outputs/cockpit/
web_paint_state.json -- see that file's own SAFETY note, identical here).

Usage: python add_color_drawing.py [OUT_DIR]  (default outputs/batchExport)
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


def _run_once(iter_dir):
    cmd = [sys.executable, WORKER, "--iter-dir", iter_dir]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, timeout=TIMEOUT_S, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return False, None, f"TIMED OUT after {TIMEOUT_S}s"
    ok = result.returncode == 0 and os.path.exists(os.path.join(iter_dir, "color.png"))
    return ok, result, None if ok else f"exit {result.returncode}"


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_DIR
    iter_dirs = sorted(
        os.path.join(out_dir, name) for name in os.listdir(out_dir)
        if name.startswith("iter") and os.path.isfile(os.path.join(out_dir, name, "params.json"))
    )

    ok_count = 0
    fail_count = 0
    for iter_dir in iter_dirs:
        tag = os.path.basename(iter_dir)
        ok = False
        result = None
        fail_reason = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ok, result, fail_reason = _run_once(iter_dir)
            if ok:
                break
            print(f"{tag}: attempt {attempt}/{MAX_ATTEMPTS} failed ({fail_reason})")
            time.sleep(INTER_LAUNCH_DELAY_S * 2)

        if ok:
            print(f"{tag}: OK")
            ok_count += 1
        else:
            print(f"{tag}: FAILED after {MAX_ATTEMPTS} attempts ({fail_reason})")
            if result is not None and result.stderr and result.stderr.strip():
                print(result.stderr.strip()[-2000:])
            fail_count += 1
        time.sleep(INTER_LAUNCH_DELAY_S)

    print(f"\n{ok_count}/{len(iter_dirs)} color drawings added, {fail_count}/{len(iter_dirs)} failed.")


if __name__ == "__main__":
    main()
