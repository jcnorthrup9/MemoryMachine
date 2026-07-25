# Handoff — 2026-07-24: canopy panel grid rotation, cross-machine sync diagnosis, high-fidelity assets (not started)

No blocking issues from today's own work. One item below is a live, unresolved bug report from the
user that needs their follow-up, not code I can fix from here.

## 1. Canopy panel faceting now follows a rotatable grid (DONE, verified live)

Traced a user reference to "the grid logic ... from a processing script ... applied to the site in
2D" to `logic/site_grid.py`'s `build_site_grid()` (added 2026-07-22, a rotatable `cell_size_ft`/
`rotation_deg` overlay for the root `app.py`'s 2D Digital Palimpsest canvas via `GET /api/site-grid`,
rendered in `static/js/engine2D.js`) -- **not** `frontend/src/siteZones.js`'s unrelated 9-zone
export/clip grid, an earlier wrong guess this session that got corrected mid-turn.

Per the user's choice (asked via AskUserQuestion), that grid logic now drives **canopy panel
faceting** specifically:
- `logic/canopy_engine.py`: `CanopyEngine` gained `panel_grid_rotation_deg`; `_panel_specs()` now
  builds panels from `build_site_grid(site_width_ft, site_length_ft, panel_pitch_ft,
  panel_grid_rotation_deg)["cells"]` instead of a fixed axis-aligned loop, and each `canopy_panel`
  `StructuralElement` now carries `rotation_deg` (the dataclass field already existed,
  `terracing_engine.py:733`, previously unused by panel-shape kinds).
- `logic/pershing_api.py`: `CanopyParams` gained `panel_grid_rotation_deg: float = 0.0`.
- `frontend/src/components/Viewport.jsx`: `CanopyPanelInstances` now spins `u`/`v` around the panel
  normal by `s.rotation_deg` (`u.applyAxisAngle(normal, theta)`) before building the render basis --
  previously `rotation_deg` was read by no panel-rendering code at all.
- `blender_cockpit.py` and `blender/pershing_headless_build.py`: both `_add_panel()` (documented as
  straight ports of each other -- keep them in lockstep if touched again) gained the matching
  `rotation_deg` spin via `mathutils.Matrix.Rotation(...) @ u`.
- `frontend/src/App.jsx` / `ParamPanel.jsx`: new "Panel Grid Rotation (deg)" slider (0-90) next to
  Panel Pitch.

**Verified live**: `generate_canopy()` called in-process at `panel_grid_rotation_deg=0` vs `30` --
panel count stable (1624 vs 1626), `rotation_deg` threads through to every serialized panel spec,
`vite build` compiles clean.

**Known caveat, not a bug, worth knowing**: at `rotation_deg=0` panel centers are **not** bit-for-bit
identical to the old axis-aligned grid -- `build_site_grid()` anchors cells around the site's center
(`width_ft/2`), the old loop anchored at `x=0`. Same pitch/coverage, different phase. Cosmetic only,
but if anyone ever diffs canopy output before/after this change expecting exact equality at rotation
0, that's why it won't match.

**Not yet done**: an actual live-browser visual check (rotate the slider, confirm panel seams visibly
rotate, not just tilt) and a real headless-Blender export at nonzero rotation -- both were left as
manual follow-ups, not automated in this session.

## 2. "Extrude as Boxes" now defaults on (DONE)

`frontend/src/App.jsx`'s `visibleLayers` initial state: `programBoxes` flipped from `false` to `true`.
Trivial, `vite build` verified clean.

## 3. Cross-machine sync bug report -- UNRESOLVED, needs the user's follow-up

User reported on a second machine (Syncthing-synced copy of this repo): Drawings tab 404s, SPATIALIZE
shows the wrong saved build "iteration", and diagrams render an old patterned hatch fill instead of
the current solid fill.

Investigated from this machine (the only one directly reachable) and found **no code defect**:
`POST /api/pershing/generate-drawings` and `GET/POST/DELETE /api/pershing/archive[/...]` both exist
and are correctly registered in `app.py`; `frontend/vite.config.js`'s `API_PROXY` covers `/api` as a
catch-all so neither route is a proxy-config gap; `.stignore` excludes `.git`/`node_modules`/`dist`/
`venv`/`__pycache__` but NOT `outputs/`/`db/`/`cache/`, so archive/iteration data should sync fine.
User confirmed via the Syncthing GUI that the folder shows "Up to Date" on the other machine, which
rules out a sync gap specifically.

Leading theory (unconfirmed, needs the user to check on that machine): a **stale running process** --
Syncthing updates files on disk but doesn't restart whatever `python app.py`/`npm run dev` process is
already running there, so a newly-added backend route or changed SVG-fill logic wouldn't take effect
without a manual restart. This project has a documented history of exactly this class of bug (see
`frontend/vite.config.js`'s own comment about stale/ghost `uvicorn --reload` processes on Windows, and
`HANDOFF_07132026_CANOPY_PROGRAM_LAYERS.md`'s "READ THIS FIRST" section: "Python doesn't hot-reload;
the process serving `/api/pershing/*` has to be killed and restarted for any `logic/*.py` change to
take effect"). Secondary, less likely theory: something on that machine is pointed at the wrong
folder -- there's a vestigial, completely unwired `npm create vite` scaffold sitting at the repo root
(`index.html`/`src/`/`vite.config.js`, package name "temp-app", one-off commit `0ed31a5`) and the
explicitly-superseded `PershingMetabolizer_Prototype/` (see `start.bat`'s own 2026-07-17 comment) --
neither should be what's running, but worth ruling out.

**Next step**: user was about to try a full process restart (backend `app.py` then `npm run dev` in
`frontend/`, then hard-refresh the browser) on the other machine. Status of that test is unknown as of
this handoff -- ask the user directly rather than assuming it's resolved.

## 4. High-fidelity assets folder -- NOT STARTED, user's own plan, just scoped today

User wants to swap the 3D app's current procedural box/cylinder/hex primitives (per-kind in
`frontend/src/kindRegistry.json`) for real detailed meshes, with a toggle to turn "high fidelity"
assets on/off in the 3D tab. Confirmed **nothing like this currently exists**:
- `models/` (served `/models`) -- static real-site-context OBJ/STL, not a per-kind asset library.
- `outputs/vector_export_test/site_named.obj` (served `/pershing-context`) -- the one fixed OBJ
  `StaticContext.jsx` loads, not swappable.
- `outputs/blender_headless/` (served `/blender-headless-output`) -- "Build in Blender" output, not
  per-kind assets.
- `assets/park_generated_assets/` -- 31 raw `meshsave_XXXXX_.obj` files sitting on disk, completely
  unreferenced by any app code; the only thing that touches asset files at all is
  `harvest/import_assets.py`, a standalone Rhino-side script unrelated to the FastAPI/React pipeline.

User's own plan (stated, not yet executed): create a new folder, then come back and have the app
point to it, plus a toggle. When that happens, the natural integration point is a new static mount in
`app.py` (same pattern as `/models`/`/pershing-context`) plus a toggle in `Viewport.jsx`/
`ParamPanel.jsx` alongside `visibleLayers`, keyed by `kind` to match `kindRegistry.json`. Nothing
implemented yet -- purely a landscape survey so far.

## 5. Commit made this session

`eaddcc5` on `feature/blender-mcp-pipeline` -- **312 files, +44258/-673**. Per explicit user
confirmation this bundled the ENTIRE working tree, not just today's changes -- the branch had been
accumulating uncommitted work across many prior sessions (see the other `HANDOFF_*`/`MILESTONE_*.md`
docs at repo root and in `archive/memoryMachine/` for what else is in there: Drawings tab,
diagram_tool AI Remix, SPATIALIZE<->2D bridge, 9-zone export grid, real-export accuracy fixes, Zonal
Constraints HUD fix, etc.). Not pushed to origin -- only committed locally.

**Gitignore hygiene fix included in the same commit**: `outputs/blender_headless/` (1.2GB+ of
regenerated Blender-build test fixtures), loose `outputs/*.png|mtl|csv` debug captures,
`outputs/cockpit/*.bak`, and `archive/workflowScreenshots/` (57MB of manual-QA screenshots) are now
gitignored -- none of it is source, all of it was about to get permanently baked into git history via
a blanket `git add -A`. `outputs/pershing_archive/` (real saved-build "iteration" records,
ArchivePanel.jsx) and `outputs/rhino/` were deliberately left alone and DID get committed -- they're
real app state, not disposable test output.

## Verification checklist for whoever picks this up next

- Canopy panel rotation: open RECONSTRUCT, generate canopy, move the Panel Grid Rotation slider,
  confirm panel seams visibly rotate in the live viewport (not just tilt). Try a headless Blender
  build at a nonzero rotation and confirm the exported panels match the viewport angle.
- Cross-machine bug: ask the user whether the other machine's restart resolved Drawings 404 / wrong
  SPATIALIZE iteration / hatch pattern. If it didn't, get the exact failing request/URL from that
  machine's browser Network tab -- that would demote this from "staleness" to a real bug worth
  investigating in code.
- High-fidelity assets: wait for the user to create their folder and ask for the wiring -- don't
  start building a toggle/mount speculatively.
