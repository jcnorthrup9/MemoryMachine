# GrowthColumns — tying the image-sampler growth script to the real column grid (`PM_GrowthColumns`)

## 1. Purpose

A separate, pre-existing Grasshopper document (`ImageSamplerToColumns.gh`,
from an earlier SCI-Arc studio, not part of this repo) samples a
black-and-white plan image and, via an agent-based growth algorithm, grows
orthogonal stick structures upward from the sample points that pass a
brightness threshold. The user wanted to tie that pipeline to the
Pershing site's real column module: *"if each grid intersection is 27
feet, that counts as a major column, within that major column can be
several other column types, let's call them mullions and have them exist
every 9 feet. but the entire site program doesn't need to be enclosed."*
Their own diagnosis of the blocker: *"i think our biggest issue here is
scale."*

## 2. What was actually wrong (found by inspecting the live document)

The existing pipeline's front end (`Curve` → `Bounding Box` → `Box Corners`
→ `Rectangular Grid`) generated sample points at a spacing set by a single
generic slider, anchored to the footprint curve's own bounding box corner
— no relationship to the real Pershing 27ft/9ft grid or its real origin.

Worse, the image-sampling UV was computed by subtracting each sample
point from the **module brep's own bounding-box corner**, then dividing by
the **module's own dimensions** — i.e. the image was being sampled through
a window sized to whatever the tiny 1x1ft voxel module happened to be, not
the site. That is the literal "scale" bug.

Downstream of that: `Split ARGB` → `Smaller Than` (Red channel vs. a
threshold slider) → `Dispatch` — a working binary presence gate — feeding
a Python 3 "Py3" agent-growth script (per-agent cohesion + decaying upward
gravity + `forceOrtho` axis-snapping, matching this project's established
orthogonal-only requirement). Its `outPts` output was wired to nothing;
a `Center Box`/`Move` stub clearly meant to place a module-brep copy at
each grown point existed but was never connected.

## 3. What `PM_GrowthColumns` does

New Python 3 Script component (`rhino/gh_growth_columns_component.py`),
reusing PM_PinGrid's proven helpers (site-data loading, `point_in_curve`,
the FEET-based grid convention) rather than inventing new grid math:

- **Major grid, 27ft** — literal scaffolding positions, matching the
  site's real column pitch (`real_slabs_columns.json` confirms actual
  surveyed columns sit on a true 27ft pitch). Idealized uniform grid for
  this prototype (per the user: *"for the test it is just a 27x27 foot
  grid"*), sourced through one function (`major_column_points`) so
  swapping to real `COLUMN_POSITIONS` later is a one-function change.
- **Mullion grid, 9ft (tunable via `MullionSpacingFt`)** — nested inside
  the major bays, deduped against the major grid by local-coordinate
  coincidence (both grids share origin/angle, so no O(n·m) distance scan
  is needed).
- **`MullionUV`** — the actual scale fix: each mullion point's position
  normalized 0–1 against the **footprint's own bounding box**, replacing
  the old module-bbox-relative computation.
- Does **not** reimplement image sampling or growth — outputs
  `MajorPosts`, `MullionPoints`, `MullionUV`, `Log` for the existing
  pipeline to consume.

`Crv` is an optional input: if wired (this document's own convention — a
single `Curve` param drives the whole pipeline), that curve is sampled
directly; if left unwired, the component falls back to PM_PinGrid's
`FOOTPRINT_LAYER` layer-scan convention, for the eventual FidelityGrid1
port.

## 4. Live rewiring (in `ImageSamplerToColumns.gh`, not FidelityGrid1 yet)

Cordyceps was connected directly to this document (not FidelityGrid1.gh),
and it already had a live test curve and module brep referenced — so the
tie-in was prototyped and verified here first, matching how every other
`PM_*` component in this project was developed (test in isolation, then
port). Porting the validated combo into `FidelityGrid1.gh` is the next
step, not yet done.

Changes made to the live document:
- Added `PM_GrowthColumns` (guid `59c934d4-cf0c-4ced-804a-2fc2c5702d90`),
  wired from the existing `Crv` param and the existing `9.0`-valued
  "grid pitch" slider (repurposed directly as `MullionSpacingFt` — it was
  already set to 9.0).
- Disconnected the old `Rectangular Grid` output from `Dispatch`'s `List`
  input; reconnected to `PM_GrowthColumns.MullionPoints`.
- Disconnected the old `Vector XYZ` output from `Image Sampler`'s input;
  reconnected to `PM_GrowthColumns.MullionUV`.
- Left the old grid-generation and UV-normalization chain (13 components)
  in place but preview-disabled — nothing deleted, fully reversible.
- Connected the previously-dead `Py3.outPts` output into the unfinished
  `Point` → `Move`/`Center Box` stub, completing the visualization path
  that was already scaffolded but never wired.
- Added a `Log` panel.

## 5. A second, independent bug found: stale slider values

Once wired, the result rendered as one solid red monolith. Root cause,
unrelated to the scale fix above: `speed` (agent step size) was `58`,
`maxGens` was `36`, and the box-size divisor was `2` — meaning every
"voxel" module was actually a **29ft cube**, and agents could travel
thousands of feet through cohesion before stopping. Real column height on
this site is 30ft total. These were leftover values from a differently
scaled test, not something the scale fix could address on its own.

Adjusted to `speed=2.5`, `maxGens=12`, box-divisor `1.5` (→ ~1.7ft
modules) — proportioned to the real 30ft column height. Result: a
legible field of short vertical growth columns with occasional orthogonal
lateral branches (arches/bridges from the `forceOrtho` axis-snapping),
closely matching the "bands of parallel sticks of varying height" and
"interlocking orthogonal bar lattice" reference images cited earlier in
this project. These slider values are a starting point, not a final
tuning — left as live sliders for the user to adjust.

## 6. Verification record

```
site_data_source=...\real_geometry.json
ORIGIN=(337.028,570.210)  column_height_ft=30.0
footprints=1
majorHeight=30.0 majorStick=1.2 mullionSpacing=9.0
majorPoints=144
mullionCandidates=1152
```

Downstream (after rewiring): `Smaller Than` presence gate passed 159 of
1152 mullion candidates (~14%) — real, visible open voids elsewhere,
matching "the entire site program doesn't need to be enclosed." The
growth script expanded those 159 seeds to 5883 total trail points across
12 generations; `Move` placed 5883 module-box copies, confirmed via
`gh_inspect(action='status')` — 25/25 components OK, no errors.

Viewport capture (Rendered display mode) confirmed visually: sparse,
independent vertical growth columns of varying height, some branching
into orthogonal horizontal runs, sitting on the correctly-scaled 9ft
mullion/27ft major grid — not the tiny broken-UV result nor the
oversized 29ft-cube monolith from before the slider fix.

## 7. Known caveats / open items (as of section 6, `ImageSamplerToColumns.gh`)

- **"Height" is not yet driven by the sampled brightness value itself** —
  only presence is (the binary threshold gate). The user's answer asked
  for *both* presence and height to be image-driven; the existing growth
  script's `maxGens`/`speed` are global sliders shared by every agent, so
  height variation currently comes from the agent cohesion/growth
  dynamics, not per-point brightness. Making height also value-driven
  would need a further edit to the Python growth script (per-point
  `maxGens`/`speed` scaled by each point's own sampled value) — a
  reasonable follow-up, not done here since it changes the existing
  script's own logic rather than just its input scale.
- **Document is unsaved.** All changes above are live in the open GH
  document but not written to disk — confirm before saving, since this is
  the user's own pre-existing file, not a repo artifact.
- **Major grid is still the idealized test grid**, not real
  `COLUMN_POSITIONS` — swap point per the user's own answer, deferred
  until the real site model is the target.
- Old pre-fix components (grid generation + broken UV normalization) were
  preview-disabled, not deleted, in case any of it is still wanted.
- Per user direction, this file was frozen after section 6 — no further
  edits were made to `ImageSamplerToColumns.gh`. All subsequent work
  (sections 8+) moved to a clean, repo-tracked pipeline in
  `FidelityGrid1.gh` instead.

## 8. Massing containment + the new `FidelityGrid1.gh` pipeline

The user asked, given a selected closed polysurface as the building
massing: *"how would the sampler logic be applied to this... the intention
is to test this out here with a simple shape, then go into the actual site
to test it out there with the actual massings."* They also flagged that
the image currently wired into `ImageSamplerToColumns.gh` is a random
placeholder, not the real plan drawing (white background, black wall
poche) the original script was built around — and, separately, asked for
a **new** Grasshopper pipeline rather than further edits to that file.

Three decisions, via `AskUserQuestion`:
1. Growth should be contained within the massing's **actual 3D volume**
   (not a flat height cap), so it correctly handles setbacks/terracing on
   real massings later.
2. The footprint should come from a **general-purpose horizontal
   section-cut** through the massing solid (`Intersection.BrepPlane`, at
   `bbox.Min.Z + 0.05`) rather than assuming one flat bottom face — costs
   ~15 extra lines over naive bottom-face extraction, but never needs
   revisiting for a real massing with a non-planar or multi-volume base.
3. The image-sampling presence/height gate is **bypassed for now** — every
   `MullionPoints` candidate grows unconditionally — so the massing-
   containment logic can be verified in isolation first. `MullionUV` is
   still output, correctly scaled, ready for an Image Sampler once a real
   plan drawing exists; no other change needed when that happens.

### New components (both also updated in the repo copies referenced above)

- **`PM_GrowthColumns`** — extended with an optional `Massing` (Brep)
  input, prioritized over `Crv` via `footprint_from_massing()`
  (section-cut, see above). Unchanged otherwise.
- **`PM_GrowthAgents`** (new file, `rhino/gh_growth_agents_component.py`)
  — a clean, repo-tracked port of `ImageSamplerToColumns.gh`'s verified
  agent-growth algorithm (unchanged: cohesion + decaying gravity +
  `force_ortho`), plus the new containment logic:
  - `prepare_massing()`: `Brep.IsPointInside()` is only reliable on a
    **closed, manifold solid**. This checks `IsSolid`/`IsValid` first
    and, if the wired Brep isn't already closed, attempts
    `Brep.CapPlanarHoles()` before use — reported in the `Log` either
    way. If it still can't be closed, containment falls back to a flat
    Z-height cap at the massing's own bounding-box top, rather than
    silently skipping containment.
  - An agent whose next step would land outside the (now-verified-closed)
    massing solid freezes permanently instead of moving.

### New pipeline graph, in `FidelityGrid1.gh`

```
Massing (Brep param, referenced via GH's "Set one Brep" onto the
         selected polysurface -- Cordyceps cannot set live geometry
         references on a param; this one step needs the user's own
         right-click action in the GH UI)
  |
  +--> PM_GrowthColumns (MullionSpacingFt, MajorHeightFt, MajorStickFt, Bake5)
  |       |
  |       +--> MullionPoints --> PM_GrowthAgents.Points
  |
  +--> PM_GrowthAgents (MaxGens, GrowthSpeedFt)
          |
          +--> GrowthPts --(Vector2Pt from world origin)--> StampMove.Motion
                                                                    |
                              WorldXY --> Center Box (ModuleSizeFt) -+--> StampMove.Geometry
```

Log panels wired for both `PM_GrowthColumns` and `PM_GrowthAgents`.

### Verification record

Test massing: an L/T-shaped closed polysurface (not a simple box — a more
useful test than originally assumed), bbox `(0,189,0.05)`–`(108,324,10.05)`,
already a valid closed solid (`IsSolid=True`, no capping needed).

```
PM_GrowthColumns: footprints=1  majorPoints=9  mullionCandidates=72
PM_GrowthAgents:  seeds=72  maxGens=10  speed=2.5
                  massing=wired, closed solid (containment active)
                  frozenByContainment=5/72
                  growthPts=781
```

Direct diagnostic (`IsPointInside` tested at the massing's own bbox
center, and at points 10ft above/below its bbox) confirmed the
containment call itself behaves correctly (`True` at center, `False`
above and below). A second diagnostic on the real growth run confirmed
`zMin=0.00  zMax=7.50` against `massingZTop=10.05` — every grown point
stayed inside the massing's real height, with margin.

**A note on a false alarm during verification**: an early perspective
viewport capture appeared to show growth towers rising well above the
massing's top face, which looked like a containment failure. Direct
numeric inspection of the output (not eyeballing a foreshortened oblique
screenshot) showed this was a misreading of perspective distortion, not
a real bug — `zMax=7.50` was correct and safely under the `10.05`
massing top the whole time. Recorded here as a reminder to verify
spatial claims numerically, not just visually, when a capture's camera
angle isn't a controlled orthographic view.

### Caveats

- **`Massing` still needs one manual step per new test object.**
  Cordyceps can drive sliders/toggles/panels but not GH's live
  geometry-reference picker — referencing a new massing requires the
  user to right-click the `Massing` param and "Set one Brep" in the GH
  UI. Not automatable from here; documented so it isn't mistaken for an
  oversight later.
- **Image-sampling gate still bypassed** (see decision 3 above) — next
  step once a real plan drawing is available: insert a native Image
  Sampler + threshold + Dispatch between `PM_GrowthColumns.MullionPoints`/
  `MullionUV` and `PM_GrowthAgents.Points`, exactly as decision 3
  anticipated.
- **Major grid is still the idealized test grid**, not real
  `COLUMN_POSITIONS` — same open item as section 7, now inherited by the
  new pipeline too.
- Document (`FidelityGrid1.gh`) is modified but unsaved as of this
  writing.

## 9. Realistic thicknesses + main columns falling off at the massing top

Two follow-up requests. First, thickness: the user's real digital site
model uses 0.75ft columns, and asked for a value close to that which is
also a clean division of 27, 9, or 3 (the site's own grid moduli) — with
mullions even more slender than the main columns.

`0.75 = 3÷4` is an **exact** match, not just close (3ft being `27÷9` or
`9÷3`). Set `MajorStickFt = 0.75`. For mullions, `0.375 = 3÷8` (half the
column thickness) was chosen over `0.25 = 3÷12` (a third) as the more
legible default at model scale; `ModuleSizeFt`'s slider floor was widened
from 0.5 to 0.125 to allow it.

Second: *"make both the main columns and the mullions fall off at the top
surface of the building massing."* Clarified via `AskUserQuestion`:
"falloff" meant a **hard clip** exactly at the top surface, not a
tapering cross-section.

Investigating turned up an asymmetry: **mullions already structurally
cannot exceed the massing's volume** — `PM_GrowthAgents`' containment
check tests each agent's *next* position before ever committing it, so a
frozen agent's final position is guaranteed to have passed
`IsPointInside`. This holds regardless of `Speed`/`MaxGens`, not just for
the specific values tested in §8. **Main columns had no such relationship
to the massing at all** — `PM_GrowthColumns` built every post at a flat
`MajorHeightFt` (30ft default), completely ignoring the massing's real
height, which is exactly why they were rendering 3x taller than the 10ft
test box in earlier captures.

Fix, in `PM_GrowthColumns.run()`: when `Massing` is wired, its own
bounding-box top Z becomes the column height, overriding `MajorHeightFt`
entirely (which now only applies as a fallback when no massing is
wired) — a flat cap, consistent with the "don't overcomplicate it, they
are just columns at 27x27 feet" guidance rather than per-column
terrain-following raycasting for a stepped/terraced top. `Log` now
reports which source was used (`massing top Z` vs `MajorHeightFt
fallback`) so this is never silently ambiguous.

Verified: `Log` reported `majorHeight=10.05 (source=massing top Z)`
against the test massing's real `10.05ft` top — an exact match, not an
approximation. Viewport capture (massing preview disabled to see clearly)
confirmed the main-column posts now terminate flush with the top surface
at every location, including the L-shaped massing's internal corner and
side walls, with no overshoot anywhere.

**Note: §9's flat-height-cap fix was superseded almost immediately by
§10 below** — the user asked why columns didn't use the same growth
algorithm as mullions, and the answer led to giving major columns their
own `PM_GrowthAgents` pass too, which handles massing-top falloff via
containment (the same mechanism mullions already used), making the
special-cased flat cap from this section unnecessary. Left recorded here
as an accurate account of what was tried and why, not corrected after
the fact.

## 10. Unifying columns and mullions under the same growth algorithm

The user asked directly: *"the mullions have the growth algorithm, but
the columns do not? they both should have this logic."* Accurate — the
original design (§3) deliberately gave major-grid points literal, fixed
geometry (`make_pin()`, straight boxes) while only mullion points ran
through `PM_GrowthAgents`, following the session's earliest framing of
columns as "real/literal structure" vs. mullions as "what the algorithm
determines." The user overturned that split: both grids should grow.

Clarified via `AskUserQuestion`:
1. Columns should stay visually distinct (thicker modules) from mullions,
   not unify into one module size — two grids, two thicknesses, both
   grown.
2. Column growth should be **more rigid** than mullion growth — stay
   close to vertical/on-grid rather than branching laterally — not use
   identical parameters.

### Design

- **`PM_GrowthColumns` became a pure point generator for both grids.**
  All Brep-building (`make_pin`), `MajorHeightFt`, `MajorStickFt`, and the
  massing-top-Z height-cap logic from §9 were removed. It now outputs
  `MajorPoints` (raw, unbuilt — the same treatment `MullionPoints` always
  had) alongside the existing `MullionPoints`/`MullionUV`. This also
  simplified its own logic — no more massing-top bookkeeping, since that
  concern moved entirely to the growth stage.
- **`PM_GrowthAgents` gained a `RigidityBias` (0.0–1.0) parameter.**
  Before axis-snapping (`force_ortho`), the combined gravity+cohesion
  vector is blended toward pure "up" by `rigidity`: `acc = acc * (1 -
  rigidity) + UP_VEC * rigidity`, then re-unitized. At `0.0` this is a
  no-op (original mullion behavior, unchanged). Closer to `1.0`, the
  vector going into axis-snapping is dominated by vertical, so the agent
  overwhelmingly picks the Z axis each step instead of wandering toward
  whatever the cohesion pull suggests — reads as structural rather than
  organic, without a separate code path or growth model.
- **Two live component instances, not one script handling both.**
  `PM_GrowthAgents_Major` (new) and `PM_GrowthAgents_Mullion` (renamed
  from the original `PM_GrowthAgents`) run the identical script with
  different inputs: major gets `RigidityBias=0.9`, `MaxGens=6` (columns
  shouldn't wander far from their 27ft grid line); mullion keeps its
  original `RigidityBias=0.0` (unwired, defaults to 0), `MaxGens=10`.
  Each cohesion calculation only considers agents within its own instance
  — major and mullion agents don't pull on each other, keeping the two
  systems visually and behaviorally independent.
- **Two separate module-stamping chains.** A new `MajorModule` (Center
  Box, sized by the repurposed `MajorModuleSizeFt` slider, 0.75ft) +
  `MajorStampVec` + `MajorStampMove` chain parallels the existing mullion
  one (renamed `MullionModuleSizeFt`, 0.375ft) — same `WorldXY`/`OriginPt`
  reused by both via `Vector2Pt`-from-origin, matching the existing
  pattern rather than inventing a new stamping idiom.
- **A side benefit, not a separate fix**: major-column massing-top
  falloff is now handled by the same volumetric containment mechanism
  mullions already used (an agent freezes the moment its next step would
  exit the massing), rather than the flat bounding-box-top special case
  added in §9. One mechanism, both grids, less code.

### Verification

```
PM_GrowthAgents_Major:   seeds=14  maxGens=6  speed=2.5  rigidityBias=0.9
                         massing=wired, closed solid (containment active)
                         frozenByContainment=14/14
                         growthPts=70

PM_GrowthAgents_Mullion: seeds=82  maxGens=10  speed=2.5  rigidityBias=0.0
                         massing=wired, closed solid (containment active)
                         frozenByContainment=16/82
                         growthPts=871
```

All 14 major-grid agents froze via containment (expected: at rigidity
0.9 they travel almost straight up, reaching the massing's 10ft-ish top
well within 6 generations at 2.5ft/step). Only 16 of 82 mullion agents
froze in the same run — consistent with free-branching agents wandering
laterally as often as vertically, not reliably reaching the top within
10 generations. `gh_inspect(action='status')` showed 15/15 components
OK, no errors, after the full rewire.

Viewport capture (both massing preview and `PM_GrowthColumns`' own raw-
point preview disabled, close-up) confirmed visually: larger 0.75ft
modules stacking vertically near each major grid corner, clustered
toward the massing's top surface; smaller 0.375ft modules scattered more
broadly and irregularly across the wall face — the intended visual and
behavioral hierarchy between "structural" and "infill" achieved through
one shared algorithm with different tuning, not two different systems.

### Caveats

- `RigidityMajor`/`MaxGensMajor`/`SpeedMajor` (0.9/6/2.5) are starting
  values, not tuned finals — left as live sliders.
- Same open items as §8 still apply: `Massing` needs the manual "Set one
  Brep" step per new test object; the image-sampling gate is still
  bypassed; the major grid is still idealized, not real
  `COLUMN_POSITIONS`; the document is unsaved.
