"""
logic/version.py
-----------------
Code provenance for saved builds (2026-07-28).

WHY THIS EXISTS: outputs/pershing_archive/*.json snapshots record the
parameters a build was made with, but not the code that turned those
parameters into geometry -- and this pipeline's geometry semantics have
genuinely shifted under identical parameters before. The canopy panel grid
is the documented case: HANDOFF_07242026 notes that after the rotatable-grid
change, panel centers at rotation 0 are no longer bit-for-bit what the old
axis-aligned loop produced (build_site_grid() anchors cells on the site
center, the old loop anchored at x=0 -- same pitch, different phase). An
archived build from before that change cannot be reproduced by loading it
today, and nothing in the file says so.

Stamping the commit into each snapshot makes that recoverable: a snapshot
that won't reproduce can at least be traced to the commit that made it.

Resolution happens ONCE at import and is cached, deliberately. The value
describes the code that is actually *running* -- which was loaded at import
-- so re-reading git later would report a commit this process isn't
executing. (This matters in practice: this project's own handoffs document
repeatedly hitting stale-process bugs where files on disk had moved on but
the running server hadn't.)

Every failure mode degrades to a partial dict rather than raising -- git
may be missing, the checkout may be an export rather than a repo, and a
snapshot that saves without provenance is far better than one that fails
to save.
"""
import os
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args):
    """Run a git command in the repo root, or return None if that's not
    possible for any reason (git absent, not a repo, timeout, non-zero
    exit). Never raises."""
    try:
        result = subprocess.run(
            ("git",) + args,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            # Windows: keep a console window from flashing when the app is
            # launched from a GUI/pythonw context rather than a terminal.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _resolve():
    commit = _git("rev-parse", "HEAD")
    if commit is None:
        # Not a git checkout (or no git). Report honestly rather than
        # inventing a placeholder commit that would look real in a snapshot.
        return {
            "commit": None,
            "commit_short": None,
            "branch": None,
            "dirty": None,
            "available": False,
        }
    # --porcelain is empty exactly when the working tree is clean. A dirty
    # tree means the snapshot's provenance is only approximate: the commit
    # identifies the baseline, not the uncommitted deltas on top of it.
    # Worth recording precisely because this branch has historically carried
    # large amounts of uncommitted work.
    status = _git("status", "--porcelain")
    return {
        "commit": commit,
        "commit_short": commit[:12],
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status),
        "available": True,
    }


# Resolved once at import -- see module docstring.
VERSION = _resolve()


def get_version():
    """Provenance for the code currently running. Returns a copy so a
    caller mutating the result (e.g. merging it into a snapshot dict)
    can't corrupt the cached value."""
    return dict(VERSION)
