# Handoff — 2026-07-25: cross-machine git sync — push needed, action required on THIS machine

This is a direct follow-up to item 3 ("Cross-machine sync bug report") in
`HANDOFF_07242026_CANOPY_GRID_SYNC_HIFI.md`. That doc's leading theory was a stale running process on
this machine. New information from the user demotes that theory: a real git commit was made **on this
machine** that the other machine (`C:\Users\jcnor\MemoryMachine` on the user's other PC, referred to
below as "Machine A") has never seen. This file exists so whoever/whatever is running on this machine
picks up the thread without re-deriving the diagnosis.

## 1. Root cause: `.git` is excluded from Syncthing — commits never auto-sync

Confirmed by reading `.stignore` (root of this repo), line 1 is literally `.git`. Syncthing mirrors
working-tree *files* between this machine and Machine A live, in real time — but it does **not**
touch `.git` at all. Branches, commits, and refs are 100% independent per machine and only ever move
via GitHub (`origin`).

Practical effect: **Syncthing being "Up to Date" tells you nothing about git state.** A commit made
here stays invisible to Machine A (and to `origin`) until explicitly pushed. This is almost certainly
why the two machines "look/operate differently" even when files appear synced — the running app code
on disk may match, but which git commit each machine's `HEAD` sits on can silently diverge forever
without a push/fetch.

Machine A's git state as of 2026-07-25 (for reference): branch `feature/blender-mcp-pipeline`, `HEAD`
at `65323a3`, last fetch from `origin` was **2026-07-17** (`.git/FETCH_HEAD` mtime + reflog's last
`pull: Fast-forward` entry). Anything committed on this machine since then is not there yet.

## 2. Action needed HERE, now

1. Sanity-check branch before doing anything: `git branch --show-current`. Machine A is on
   `feature/blender-mcp-pipeline` — if this machine shows something else, stop and flag it to the user
   rather than assuming.
2. `git status` — check whether there's *other* uncommitted work sitting here beyond the commit the
   user already made. If so, ask the user whether it should be committed and pushed too, or left
   local, before proceeding.
3. `git push origin feature/blender-mcp-pipeline` (adjust branch name if step 1 showed something
   different).
4. Tell the user directly once the push succeeds (or if it fails/rejects — e.g. if `origin` has
   commits this machine doesn't have, which would mean *both* machines have diverged commits and need
   an actual merge, not just a push. Report the exact error rather than forcing anything).

Do **not** attempt to `git pull`/fetch-and-merge from `origin` as a fix for the "looks different" bug
— Machine A is the one behind, not this machine. Pulling here first is unnecessary and risks an
unwanted merge commit; just push.

## 3. Context for reconciliation happening on Machine A (informational, no action needed here)

Machine A has ~60 files of uncommitted local WIP dated 2026-07-09 → 07-24 (SPATIALIZE tab, Drawings
export tab, canopy auto-coverage, network growth-on-rebuild, Juror Chat grounding) that will be
snapshotted into a safety commit there before it fetches this push and reconciles the two histories.
It is not lost, no risk to it from this push.

If useful for a quick sanity check on whether this machine's commit already has equivalent work, the
untracked-on-Machine-A source files were: `frontend/src/components/DrawingsPanel.jsx`,
`SpatializerPanel.jsx`, `Recent2DGenerationsPanel.jsx`, `frontend/src/diagramGridPreview.js`,
`siteZones.js`, `spatializerEngine.js`, `diagram_tool/static/js/remixChat.js`,
`logic/diagram_remix_chat.py`, `logic/site_grid.py`, `drawing_styles.py`. Also worth noting: Machine
A's uncommitted diff touches `.mcp.json`, repointing the `memory_machine` MCP server entry from a
hardcoded path to `${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe` for portability — if this machine's
`.mcp.json` still has a hardcoded absolute path (of either machine), that's expected to get reconciled
to the portable form from Machine A's side, not something to fix here.

## 4. Verification

- `git log --oneline -1` after push should match what `git ls-remote origin
  feature/blender-mcp-pipeline` reports, confirming the push actually landed.
- Nothing else on this machine needs to change as a result of this handoff — this is a push-only
  action item.
