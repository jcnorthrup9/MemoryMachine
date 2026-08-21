# Handoff: live-demo tunnel infra, GENERATE speed fix, presentation ran successfully

**Date:** 2026-08-21 · **For:** a fresh chat (context-credit handoff) · **Branch:** `feature/blender-mcp-pipeline`

## Summary — what this thread of work did

Two mostly-independent pieces of work, both committed and verified working:

1. **Fixed `/api/generate` being unusably slow (60-100s+ per call, sometimes worse).**
2. **Built infrastructure to make the live app work as a link anyone can open** (for a real presentation, not just local use), plus a recorded-demo fallback for when a venue firewall blocks it. **The presentation happened on 2026-08-19 and everything worked** — live link, live GENERATE, the works.

## Milestone 1: GENERATE performance fix (commit `aba9b77`)

Root-caused via direct profiling (not guessing): the bottleneck was never the AI/Ollama call (~5s) — it was `remix_layers()` → `_solve_zonal_scales()`'s scale-sweep, which re-parsed and re-rasterized the same static precedent-SVG geometry from scratch on every one of its ~140 internal measurement passes per request. That code was fine when the precedent library had 5 sites; nobody updated it when the library grew to 51.

Three targeted, correctness-verified caches:
- `logic/urban_engine.py`: `_rasterized_area()` — memoizes per-(layer, site) rasterized area (`_best_area_anchor`'s inner loop was recomputing this on every single request).
- `ingest_diagram_svg.py`: `_boundary_bbox_center_and_size()` — memoized by `id(root)`; was re-deriving PershingSquare's own static boundary geometry on every sweep step.
- `sketch_weight_mapper.py`: `_points_in_polygon()` — added a bounding-box pre-filter so a small zone-tile polygon only gets tested against grid points near it, not the entire ~2700-point site grid. Verified bit-for-bit identical output to the unfiltered version before keeping it.

**One dead end, reverted before committing:** first tried excluding SVG `<g id="*::hatch">` sub-groups from `_group_polygons()` assuming they were decorative texture overlays. Wrong — for layers like HARDSCAPE the *real* fill geometry lives inside those groups (a mosaic of many small tiles, not one big shape). That change silently zeroed out real area. Caught it, reverted, moved on to the three fixes above instead.

**Net result** (controlled, seeded before/after): ~95-100s → a reproducible ~18.6s standalone; 14-34s observed on the live server depending on which random site/category picks a given prompt resolves to. Still not instant — the scale-sweep itself does ~140 measurement passes by design (documented reason: categories can spatially overlap, e.g. the hardscape/water "canyon rupture" effect, so it can't just measure one category in isolation). Further speedup would mean reducing `SWEEP_STEPS`/`OUTER_PASSES` in `_solve_zonal_scales()`, which trades accuracy against the zonal-mix guidelines — a product call, not made here.

## Milestone 2: live-demo link infrastructure

**The ask:** deck slide "05 // THE APP" (`html/final_deck.html`) embeds the live app via `<iframe src="http://127.0.0.1:5174/">`. That only ever resolves on the machine running it — sharing the deck link doesn't make it work for anyone else. User needed it to actually work for one real presentation.

**What got built** (all still live and working as of this handoff):

- **Cloudflare Tunnel**, not a real cloud deployment. Reasoning: the GENERATE feature depends on a local ~5GB Ollama model; hosting that publicly would mean recurring cost and a real deploy pipeline for a single presentation. `cloudflared tunnel --url http://127.0.0.1:5174` exposes the *whole* locally-running app (frontend + backend, via Vite's existing `/api` proxy) through one free, temporary public URL — no CORS changes, no production build needed, because the browser only ever talks to the local Vite dev server; Vite does the proxying to the backend server-side.
- **`frontend/vite.config.js`**: added `server.allowedHosts: true` — Vite's dev server otherwise rejects requests with an unrecognized Host header (DNS-rebinding protection), which blocks the tunnel's hostname by default.
- **`html/final_deck.html`**: the iframe (`id="app-frame"`) now reads an optional `?app=<url>` query param to override its `src`, falling back to `127.0.0.1:5174` when absent. A small `<a>` link in the slide header ("Open Live App ↗") points at whatever tunnel URL is currently live, opening in a new tab.
- **Recorded-demo fallback**: `archive/diagrams/live_demo_fallback.gif` — a real ~7s captured walkthrough (idle → prompt → GENERATE → loading animation → real result). A **"Show Recorded Demo"** button next to the live link instantly swaps the *same frame* between the live iframe and this GIF. Manual, not automatic — there's no reliable cross-browser way to detect a silently-failed iframe load (e.g. a firewall blocking the tunnel domain outright), so this is presenter-operated: if the live app doesn't show up in a couple seconds, click the button.
- **`PRESENTATION_LIVE_DEMO.md`**: the full runbook for doing this again — start the app, start the tunnel, put the URL in the deck link, known caveats (GENERATE takes 14-34s, backend is single-worker so don't let two people click GENERATE at once, no auth on the tunnel URL).

### The recurring gotcha this surfaced: Vite rebinds to `::1` after a branch switch

`vite.config.js` has `host: '127.0.0.1'` (this machine's `localhost` DNS resolution is broken, per its own comment). Every time git switches branches in a way that touches `vite.config.js` on disk (even a transient flicker), Vite's own file-watcher restart doesn't reliably reapply that binding — it falls back to Vite's default (`localhost`, which resolves to `::1` here), and the app becomes unreachable at `127.0.0.1:5174` even though a process is still running and "ready." **Fix is always the same:** kill the node/vite process, `npm run dev` fresh. Happened twice this session before the pattern was recognized.

**This is exactly why the git worktree exists** (see below) — it's the permanent fix, not just a recognized symptom.

### Git worktree for main-branch/Pages pushes

`html/final_deck.html` on **`main`** is what GitHub Pages actually serves (`https://jcnorthrup9.github.io/MemoryMachine/html/final_deck.html`) — a much older, structurally different snapshot of this repo (no `frontend/` directory at all, a totally different/simpler `app.py`). Cherry-picking deck-only changes from `feature/blender-mcp-pipeline` onto `main` is the right move (confirmed: `main`'s copy of `final_deck.html` already matched what Pages was serving byte-for-byte), but doing it by `git checkout main` in the main working directory is what caused the Vite-rebind bug above, plus once triggered a ChromaDB file-lock error (`ChromaDB` files held open by the running backend, `git checkout` couldn't swap them — had to stop the backend first).

**Fix:** a dedicated worktree at **`.claude/worktrees/main-pages-deploy`**, checked out to `main`. Any future deck-on-Pages update should go: commit on `feature/blender-mcp-pipeline` as normal → `cd .claude/worktrees/main-pages-deploy && git cherry-pick <hash> && git push origin main` → back on the main working directory, nothing was touched, no restart needed. Used successfully for the second and third link updates with zero side effects.

## Current live state (verified at time of writing)

- Tunnel URL **`https://roof-allan-smooth-detective.trycloudflare.com/`** — still alive right now (this machine hasn't restarted since the presentation), but this is exactly the kind of thing that goes stale unpredictably. **Don't assume it still works** — check first (`curl -o /dev/null -w '%{http_code}' <url>`), and if dead, restart per `PRESENTATION_LIVE_DEMO.md` and push a new link via the worktree.
- `html/final_deck.html` on GitHub Pages currently has both the live link and the "Show Recorded Demo" fallback wired in and confirmed working.
- `origin/main` has moved forward substantially since this thread's work, from unrelated concurrent activity on the deck (page-01 case cards, page-04 precedent grid/current-conditions slides — none of that touched slide 05 or anything in this handoff). If picking this back up, expect `git log origin/main` to look different from what's described here — check it fresh rather than assuming.

## Known non-issues (already tried, correctly rejected)

- **Full public cloud deployment** of the backend — rejected, see Milestone 2's "why not" above. Still valid reasoning if this comes up again.
- **Excluding SVG `::hatch` groups from area rasterization** — wrong, reverted, see Milestone 1.

## Not yet done / open threads

- The Windows ProactorEventLoop backend zombie-listener bug (port stays open, process stays alive, nothing gets served) is still unfixed at the root — worked around all session via process restarts, never patched (`uvicorn.run()` forcing `WindowsSelectorEventLoopPolicy` was identified as the standard fix in an earlier session, never implemented).
- `gif_creator`'s browser-extension GIF export got stuck mid-download twice in a row this session (not a fluke) — worked around by capturing frames via `computer` tool screenshots with `save_to_disk: true` (bypasses Chrome's download manager entirely) and stitching with Pillow instead. Worth knowing if a future recording is needed — try the direct-screenshot approach first rather than re-fighting `gif_creator`'s download path.
