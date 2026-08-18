# Handoff — 2026-08-05: Cordyceps/Rhino bridge went unresponsive mid-task — check Rhino before anything else

## 1. Read this first — what's actually blocking

Mid-session, while trying to switch the live Rhino document over to the real
site model, the Cordyceps MCP bridge stopped responding. **Nothing has been
confirmed lost**, but nothing past this point has been verified either. Do
not assume any of the in-flight save/open actions below actually completed.

**First action on resume**: try `gh_inspect(action='status')`. Three
possible outcomes:
- **Works, returns the 11-component list from §4** → bridge recovered, GH
  document state intact, probably just needed Rhino restarted or a dialog
  dismissed. Proceed to §6.
- **Times out** → Rhino is still alive but its UI thread is blocked,
  almost certainly on a dialog. Look at the actual Rhino window, dismiss/
  answer whatever's on screen, try again.
- **"Unable to connect" / connection refused** → the Cordyceps plugin's
  local server isn't running. Rhino likely crashed or was closed. Relaunch
  Rhino, confirm the Cordyceps plugin loads, reopen
  `FidelityGrid2.gh`, then try `gh_inspect(status)` again.

## 2. Exactly what happened, in order

1. User asked me to explain how `PM_PedestalUndercroft` (the live GH
   pedestal-generation script) works — done, no issue, see §5 of this doc
   for the summary if you need it again without re-reading the source.
2. User asked to **connect to the real "Pershing intervention grid" Rhino
   file and run the script** — i.e. stop testing against the small
   placeholder massing and point the pipeline at the actual site model.
3. I searched and found several candidates in
   `C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\`:
   - `PershingInterventionGRID.3dm`
   - `PershingInterventionGRID_08032026.3dm` (dated backup)
   - `PershingInterventionGRID_pedestal_2x2.3dm`
4. Checked current state first (`gh_document(info)` + `rhino_scene(layers)`)
   and found something worth flagging on its own: **the actual live
   Grasshopper document is `FidelityGrid2.gh`**, not `FidelityGrid1.gh` as
   every earlier handoff/summary in this repo has been calling it. Full
   path: `C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\
   grasshopper\FidelityGrid2.gh`. It was showing `isModified: true`
   ("FidelityGrid2*"). The currently-open `.3dm` also had substantial
   unsaved baked geometry (729 objects on a `Scaffold` layer, 55 `Seeds`,
   51 `WarpedGrid` curves, etc. — see §4's layer dump).
5. Asked the user two questions via `AskUserQuestion`, both answered:
   - **Which file**: `PershingInterventionGRID_pedestal_2x2.3dm` (chosen
     over the base file and the dated backup).
   - **How to handle unsaved work first**: "Save both first, then open the
     new file" (chosen over discarding).
6. Ran, in parallel: `rhino_scene(action='script', cmd='-_Save')` and
   `gh_document(action='save', path='...FidelityGrid2.gh')`.
7. **Both timed out.** Most likely explanation: `-_Save` popped a modal
   dialog (a "Save As" file browser if the `.3dm` was never actually named/
   saved before, or a mesh/version-compatibility warning) that blocked
   Rhino's UI thread — and since Grasshopper runs inside Rhino's process,
   the GH save call blocked too, waiting on the same stuck thread.
8. Tried `gh_inspect(status)` alone as a lighter probe — **also timed out**.
9. Tried again — this time `gh_inspect(status)` and `gh_document(info)`
   both returned **"Unable to connect. Is the computer able to access the
   url?"** — a connection refusal, not a timeout. That's a different
   failure mode: either Rhino crashed, or the Cordyceps plugin's local
   listener died (possibly the modal dialog escalated into an actual
   crash), or it's blocked severely enough that the listener itself
   stopped accepting connections.
10. Told the user I have no way to see or interact with a native Windows
    dialog from here, and asked them to check the Rhino window directly.
    User's response was to write this handoff instead of continuing to
    poke at it live — restarting and will check again later.

**Net effect**: the actual file-switch (`-_Open` on the target `.3dm`) was
**never attempted** — only the pre-switch save calls ran, and their
success/failure is unconfirmed. So there should be no risk of a botched
file-open having orphaned any GH references. The open question is purely
whether the `-_Save` completed, whether `FidelityGrid2.gh` got saved, and
what state Rhino is actually in right now.

## 3. What to check / do on resume

1. `gh_inspect(action='status')` — see §1 for what each outcome means.
2. If reachable: `gh_document(action='info')` — confirm it still reports
   `FidelityGrid2.gh`, and check `isModified`. If `isModified: false`, the
   save from step 6 above actually went through before the hang.
3. Check whether the `.3dm` itself saved — there's no direct "did the last
   save succeed" query; the practical check is whether Rhino is showing an
   asterisk/modified indicator, or just ask the user to look.
4. **Before retrying `-_Save` or any raw `rhino_scene(script, cmd=...)`
   command that can pop a dialog**: consider whether the document already
   has a real file path (it should, if this is a long-running session) —
   if so, a scripted `-_Save` normally shouldn't prompt at all. The likely
   dialog trigger was something else (version/mesh warning is the more
   probable culprit than "untitled document" given how long this session
   has been running). Worth asking the user if they saw a specific dialog
   when they check.
5. Once confirmed alive and stable, resume at §6 (the actual file-connect
   task) — don't re-ask the two `AskUserQuestion` decisions, they're
   already answered (see §2 step 5).

## 4. Live Grasshopper state as of just before the hang

`FidelityGrid2.gh`, 11 components, all `OK` per the last successful
`gh_inspect(status)`:

| Component | GUID | Role |
|---|---|---|
| `PM_FacadePanelizer` (FG1) | `21a3ec2f-1d8f-4012-8ca6-489e1cd1432f` | Real seeds/grid, corrected site constants |
| `PM_FacadeScreen` | `7dd97c84-8689-43f2-b239-c19175c1411f` | Earlier-session, untouched |
| `PM_GrowthScaffold` | `24f4b53c-578d-4ef5-9fde-20b1f9a61f02` | Earlier-session, untouched |
| `PM_ScaffoldFrame` | `335d5dd5-7c0a-41d9-a4e2-ce783ff1ea8b` | Earlier-session, constants corrected |
| `PM_HeightField` | `64e0abe1-42af-4c9c-a5b4-89f1d7d93db9` | Real height falloff — **orphaned**: output only feeds a Log panel, nothing downstream consumes it (the real math is duplicated inline inside `PM_MassingFrame_Lsystem` instead) |
| `PM_MassingFrame_Lsystem` | `2ea6b758-9af8-45a5-9853-8673ba78d81b` | Orthogonal L-system massing frame — twice rejected direction, frozen, not being extended |
| `PM_PedestalUndercroft` | `7228f312-43f8-479d-b6b6-6959a8429016` | Digital pedestal, hull forced-touch + distance-float. `.Seeds` rewired this session to real `FG1.SeedPts` |
| `PM_ElasticGrid` | `c8da1ebb-e3c9-4857-aafb-91582463e3c5` | Warped-DTLA-line distortion, calibrated `MaxRadiusFt=35, MaxForceFt=5` → `maxDisplacementFt=8.26` (target ~7-9ft) |
| `PM_CellOccupancy` | `aaff826d-35b1-4dcf-b728-5a4962650fc0` | Voxel-cell placement guide, `candidateCells=81 occupiedCells=62` |
| `SeedsMerge` | `2626ca39-57cd-4917-8a7f-8b281701ae18` | Merge (native) — FG1.SeedPts + PM_CellOccupancy.OccupiedCells |
| `FlattenSeeds` | `3a796d5d-3a65-4248-b1a7-6605373f394d` | Flatten Tree (native) — feeds `PM_MassingFrame_Lsystem.Seeds` |

Shared `Massing` Brep param GUID: `8bcec7ae-344f-4fe5-a300-993fd079e688` —
**currently references the small placeholder test massing**, not real
site geometry. This is exactly what the file-connect task (§6) needs to
fix.

**Deleted this session** (21 components — the entire "Attempt 1"
cohesion/gravity growth-agent direction, explicitly rejected by the user
two sessions ago, left dead on the canvas until now): `PM_GrowthColumns`,
`PM_GrowthAgents_Major`, `PM_GrowthAgents_Mullion`, `WorldXY`, `Module`,
`StampMove`, `StampVec`, `OriginPt`, `MajorModule`, `MajorStampVec`,
`MajorStampMove`, plus 7 sliders/toggles and 3 Log panels feeding them.
Document went from 22 components to 11. **If the save from step 6 in §2
didn't actually complete, this deletion work may not be persisted** —
check whether `PM_GrowthColumns` etc. are back when you reconnect; if so,
the deletion needs to be redone (the full ID list is in this repo's git
history / prior conversation, not repeated here since it's a mechanical
`gh_canvas(action='delete', ids=[...])` call).

Layers on the currently-open `.3dm` (from `rhino_scene(layers)`, taken
right before the hang — useful for confirming whether the doc reverted or
is intact once reconnected):
`Detailed_Facades::_Parti::ColumnGrid` (36), `DtlaGrid` (3), `Seeds` (55),
`MarkedCells` (50), `Detailed_Screen::_Parti::WarpedGrid` (51),
`Detailed_PinGrid::Footprint0::Scaffold` (729),
`Detailed_GrowthColumns::Footprint0::MullionPoints` (72), `MajorPoints`
(9).

## 5. `PM_PedestalUndercroft` — quick recap (already explained to user)

Real GH script, not the Processing/three.js one (see §7 for that — the
user's "how does this script work" question turned out to mean this one,
not `mainTk4`, after an initial mix-up).

1. Filter candidate `Seeds` to those whose XY falls inside `Massing`'s
   footprint.
2. `hull_2d()` — 2D convex hull of survivors.
3. Hull-perimeter points forced to touch `FloorZ` exactly. A volume-
   weighted center of mass is guaranteed to lie inside the convex hull of
   the points it's averaged from, so this guarantees physical stability by
   construction, independent of how dramatic the interior float is (the
   source script's own key insight, reused verbatim).
4. Interior (non-hull) points float: `bottom_z = FloorZ + MaxFloatFt * t`,
   `t` = normalized distance from the real site datum `ORIGIN`.
5. Each leg = a vertical `LegWidthFt`-square box from its `bottom_z` up to
   the massing's underside (currently a flat bbox `Min.Z` approximation —
   known simplification, would need a real ray-cast for a non-flat
   underside).

On the small placeholder massing: `candidateLegs=1` (only 1 of 55 real
seeds falls under that tiny footprint) — sparse but correct, and exactly
the kind of degenerate result that switching to the real site file (§6)
should fix.

## 6. The actual task in progress — resume here once the bridge is back

Goal: point the live pipeline (`Massing` param `8bcec7ae-...` at minimum,
possibly other Rhino-doc-tied references) at real geometry from
**`C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Rhino\
PershingInterventionGRID_pedestal_2x2.3dm`**, then re-run
`PM_PedestalUndercroft` (and worth re-checking `PM_MassingFrame_Lsystem`/
`PM_ElasticGrid`/`PM_CellOccupancy` too, since they all key off the same
`Massing` param or off seed positions gated by it) against real data
instead of the small test massing.

Steps not yet done:
1. Confirm bridge is alive (§1).
2. Confirm whether `-_Save` / `gh_document(save)` from before the hang
   actually completed (§3).
3. Open `PershingInterventionGRID_pedestal_2x2.3dm` in Rhino (the
   `-_Open` command itself was never attempted — this is the actual next
   new action, not a retry).
4. Once open, inspect its layers to find the real site massing geometry
   (object name/layer unknown yet — never got there before the hang).
5. Re-point the `Massing` Brep param (and confirm no other params were
   silently relying on the old document's specific object GUIDs) to the
   real massing.
6. Re-run and verify `PM_PedestalUndercroft`'s `Log` — expect
   `candidateLegs` to jump well above 1 now that real building footprints
   are involved instead of one small placeholder box.
7. Consider whether `PM_MassingFrame_Lsystem`, `PM_ElasticGrid`,
   `PM_CellOccupancy` should also be re-verified against the real massing
   at the same time, since they're all downstream of the same `Massing`
   param or of seed positions that depend on it.

## 7. Still-open, unrelated to the above: `mainTk4` attractor-seeding question

Separate open thread, doesn't block §6. Covered in
`HANDOFF_08012026_PROCESSING_GROWTH_ALGO_FOR_MASSING.md` §1, and this
session actually **read the real source** (`agent.pde`, `app_tk4.js` in
`C:\Users\jcnor\OneDrive - SCI-Arc\2026_Summer\Thesis\Processing\mainTk4\`)
to confirm that handoff's description was accurate — it was. Quick
recap of how it works: agents seeded at ground level walk in orthogonal,
collision-avoiding jogs (`forceOrtho()` + `occupiedVoxels` voxel-grid
collision chain: straight → horizontal dodge → vertical escape →
terminate) toward the nearest attractor point, stopping when within one
step-length of it. Originally, both agent seeds and attractor points came
from scanning a color-coded image mask (`isTargetColor`/`edgeCheck`);
attractors specifically came from **edge-detected pixels** of that mask,
suspended at one fixed flat height.

Two swaps are already decided (per the 08-01 handoff): mask → point-in-
polygon against real footprints, texture-driven thickness → constant real
lumber-stock thickness.

**Not decided**: with no image edge-detection left, how should attractor
points be generated from a real footprint polygon? Three options were
posed to the user this session via `AskUserQuestion` but the question was
rejected/redirected — turned out the user's preceding "how does this
script work" question meant the *Grasshopper* `PM_PedestalUndercroft`
script, not `mainTk4`, so the conversation pivoted to §6's file-connect
task before this ever got re-asked. Still fully open:
1. Points resampled along the footprint's boundary curve (closest analog
   to the original edge-tracing behavior).
2. Just the footprint's corners (sparser, more faceted).
3. An interior grid across the footprint (denser, reaches the whole
   footprint area not just its edges).

Also worth raising when this comes back up (not yet discussed with the
user at all): the original's attractors sit at one **flat** ceiling
height, but real buildings on this site have varying heights (already
modeled via `PM_HeightField`'s falloff) — whether attractor height should
vary per building rather than use a single constant is an open adaptation
question, not just the seeding-strategy one above.

## 8. Files touched this session (all already saved to the repo, unrelated
to the Rhino/GH hang above)

- `PershingMetabolizer_Prototype/MASSING_FRAME.md` — extended with a new
  §8 covering `PM_ElasticGrid`/`PM_CellOccupancy`, calibration numbers,
  before/after root-density table, updated component graph and caveats.
- `rhino/gh_elastic_grid_component.py` — fixed a real bug
  (`NurbsCurve.CreateInterpolatedPoints` doesn't exist in RhinoCommon;
  corrected to `Curve.CreateInterpolatedCurve`), updated default
  `MaxRadiusFt`/`MaxForceFt` to the calibrated values (35.0 / 5.0).
- `rhino/gh_cell_occupancy_component.py` — no changes this session beyond
  what was already written; pushed live successfully.

These are normal git-tracked file edits, independent of the live Rhino/GH
document state — not affected by the bridge going down.
