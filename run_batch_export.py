"""
Driver for a batch of randomized design iterations, each seeded from its
own random 2D remixed diagram, into outputs/batchExport/iter{N:03d}/. Each
iteration runs in its own subprocess (batch_export_worker.py) so one bad
iteration can never take down the rest of the batch or anyone else's
shared server -- no HTTP, no dependency on the live app being up at all.

Retries + inter-launch delay (2026-08-12): a real 50-iteration run hit a
wall of consecutive Windows-level crashes (exit 0xC0000135 /
STATUS_DLL_NOT_FOUND) starting partway through -- confirmed transient, not
a code bug: the exact same iteration that "failed" inside the batch
succeeded immediately when re-run alone moments later. Rapid back-to-back
python.exe launches (each loading matplotlib/trimesh/embreex fresh) appear
to occasionally lose a DLL-load race under Windows -- a small delay between
launches plus a retry-on-failure loop absorbs that instead of needing a
human to notice and manually re-run the tail of a batch.

Usage: python run_batch_export.py [N_ITERATIONS]  (default 50)
"""
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(REPO_ROOT, "outputs", "batchExport")
WORKER = os.path.join(REPO_ROOT, "batch_export_worker.py")
TIMEOUT_S = 300
INTER_LAUNCH_DELAY_S = 1.0
MAX_ATTEMPTS = 3
EXPECTED_FILES = ("source_diagram.png", "plan.png", "axo.png", "long_section.png", "params.json")


def _run_once(tag, i):
    iter_dir = os.path.join(OUT_DIR, tag)
    cmd = [sys.executable, WORKER, "--iter", str(i), "--out-dir", OUT_DIR, "--seed", str(i)]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, timeout=TIMEOUT_S, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return False, None, f"TIMED OUT after {TIMEOUT_S}s"

    present = {f: os.path.exists(os.path.join(iter_dir, f)) for f in EXPECTED_FILES}
    if result.returncode == 0 and all(present.values()):
        return True, result, None
    missing = [f for f, ok in present.items() if not ok]
    return False, result, f"exit {result.returncode} -- missing: {missing or 'none'}"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    os.makedirs(OUT_DIR, exist_ok=True)

    log_lines = []
    ok_count = 0
    fail_count = 0

    for i in range(1, n + 1):
        tag = f"iter{i:03d}"
        ok = False
        result = None
        fail_reason = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            ok, result, fail_reason = _run_once(tag, i)
            if ok:
                break
            print(f"{tag}: attempt {attempt}/{MAX_ATTEMPTS} failed ({fail_reason})")
            time.sleep(INTER_LAUNCH_DELAY_S * 2)  # extra backoff before a retry specifically

        if ok:
            line = f"{tag}: OK" + (f" (attempt {attempt})" if attempt > 1 else "")
            ok_count += 1
        else:
            line = f"{tag}: FAILED after {MAX_ATTEMPTS} attempts ({fail_reason})"
            fail_count += 1
        print(line)
        if result is not None:
            if result.stdout and result.stdout.strip():
                print(result.stdout.strip())
            if not ok and result.stderr and result.stderr.strip():
                print(result.stderr.strip()[-2000:])
        log_lines.append(line)

        time.sleep(INTER_LAUNCH_DELAY_S)

    summary = f"\n{ok_count}/{n} iterations fully OK, {fail_count}/{n} failed.\nOutput dir: {OUT_DIR}"
    print(summary)
    log_lines.append(summary)

    with open(os.path.join(OUT_DIR, "batch_log.txt"), "w") as f:
        f.write("\n".join(log_lines) + "\n")


if __name__ == "__main__":
    main()
