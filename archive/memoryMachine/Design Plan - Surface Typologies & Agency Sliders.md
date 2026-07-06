**Tags:** #design-agency #sketch-ingestion #blender #standing-plan

Captures the design-agency control system discussed 2026-07-04, before building any of it — the user asked to "solidify the logic, save a note of it, and then see what works from there." Supplements `TODO_ThesisFinal_Pipeline_Blueprint.md` and `HANDOFF_07032026_PIPELINE_STATUS.md`.

---

## 1. Surface Typologies (user's taxonomy, verbatim intent)

- **Green Space**
- **Amenities**
  - Necessities (restrooms, drinking water, shade)
- **Hardscape**
  - Flexible Space (modular structures, moveable seating, performance space, food vending)
  - Circulation (walking paths, running/cycling paths)
- **Water Features**
- **Main Attractor**
  - The Canyon (the excavation itself)
  - The Lightwell (references/preserves the memory of the existing Pershing Square fountain — an explicit "memory" gesture, not just a functional water feature)

All of these are meant to read as a coherent, connected system — circulation and adjacency between typologies matters, and so does connection to the surrounding urban fabric (Olive/Hill/5th/6th frontages). This is a design goal for how the sketch itself should be drawn, not a technical rule to encode separately.

## 2. Sketch-marking convention — staged, not all at once

7-8 distinct typologies is too many to reliably distinguish by color alone (hard to tell apart by eye, harder for simple RGB thresholding on a photographed sketch). Proposed approach: **color = broad category, written text label = sub-type** — this already matches the user's own habit (the real test sketch had "HILL"/"OLIVE"/"5th"/"6th" handwritten directly on it).

Staged rollout (don't build all categories at once):
- **Stage 1 (built):** black = canyon/main attractor intent (line-following weight, additive to the data-driven excavation).
- **Stage 2 (next):** add blue = hardscape/protect (an area intent — suppresses excavation, needs flood-fill-the-interior logic, not just line-distance falloff, since it's a *region* claim not a *path* claim).
- **Stage 3+ (later):** green = green space, further sub-typing (amenities, water, flexible space, circulation) via written labels or additional colors, added incrementally once each stage is verified — not attempted all at once.
- Red stays reserved for annotation/boundary-tracing (already excluded from the design-intent signal).

## 3. Authority hierarchy (locked principle)

1. **Real site geometry is ground truth.** `structural_grid_analyzer.py`'s SVG-derived grid/boundary (the real Rhino "due-diligence" data: actual dimensions, real column positions, actual site boundary) is authoritative. Never distorted to fit the sketch.
2. **The sketch is fit *within* that real frame**, not the other way around — sketch pixel-space maps proportionally onto the site's real width/length, always constrained to the true boundary.
3. **Within that frame, the sketch is the primary design author.** `sketch_alpha` stays high (0.75+ per the user's earlier choice) — the data-driven signals (transit proximity, etc.) modulate, they don't override.

## 4. What sliders should control (scope, discussed 2026-07-04)

- **`sketch_alpha`** (already a real parameter) — the literal "agency dial": 0 = pure data-driven, 1 = pure sketch-driven. Doubles as a genuine thesis-argument moment for a jury demo (see Section 6).
- **Position offset (x, y, z)** — translate sketch-derived elements/weight field spatially. Should be low-effort given the existing grid-indexed architecture (voxel grid + plan/section views already built).
- **Canyon "width"** — maps to `sketch_weight_mapper.py`'s `falloff_scale_ft` (how far influence spreads from a drawn line).
- **Canyon depth scale** — currently capped by the `entrance_base_depth_ft`/`transit_influence` formula; needs an explicit multiplier/override slider added.
- **Canyon location** — covered by the position-offset control above.
- **Canyon shape** — explicitly NOT slider-controlled for now. Per the user directly: "for now, the shape of the canyon is dependent upon the sketch and the site boundary [SVG] data." Shape stays fully sketch+boundary-derived.

## 5. Pipeline architecture: Blender as the live "cockpit"

**Decision (2026-07-04): build live Blender sliders/controls before any new app or Three.js modification.** The user wants to try this specific path first.

- Blender's bundled Python already has (or can trivially get) the same libraries the core pipeline depends on — numpy, trimesh, ezdxf, svgpathtools, PIL, opencv. Confirmed already: `smolagents` was pip-installed directly into Blender's own Python (`.../Blender 5.0/5.0/python/bin/python.exe`) earlier this session for an unrelated addon fix, proving this works.
- **Architecture:** Blender directly imports `terracing_engine.py`, `sketch_weight_mapper.py`, `vector_export.py`, `structural_grid_analyzer.py` as plain Python modules — no duplicated logic, no separate server/API. A custom Blender panel exposes the sliders above as real Blender properties; moving a slider (or pressing a "recompute" button, since full HLR/DXF export isn't instant) re-invokes the same engine code and rebuilds the terrace geometry live in the viewport.
- **The existing Three.js "Metabolizer" browser app stays exactly as-is** — untouched, still the fast quick-iteration diagramming tool. It is NOT the control surface for this system.
- **Final exports (DXF/SVG/PNG, high-fidelity renders) can be triggered directly from within Blender**, calling the same `vector_export.py` functions, once the designer is happy with slider positions. So: yes, Blender can be "kept open as part of the presentation" — it isn't strictly upstream of a separate export app, it can *be* the export step too, on demand, from the same live session.

## 6. Why this matters for the thesis argument, not just the tooling

The user explicitly framed sliders as something that "would also help argue for my own agency in this project." `sketch_alpha` in particular is worth treating as a deliberate presentation moment, not just a technical parameter — turning it from 0 to 1 live in front of a jury visibly shows the design shifting from "the algorithm decided this" to "I decided this." Worth distinguishing, as more parameters get added, which are *technical* tuning knobs (nobody but the user needs to see them) versus *thematic* ones worth exposing live (agency, designer-vs-data tension).

## 7. Deferred: digital sketch-markup tool

Idea raised: build a small tool letting the user circle/outline/paint colored regions digitally (instead of hand-drawing on paper, photographing, cropping). Good idea, explicitly **not prioritized right now** — the user wants to try the Blender slider experiment first, before building any new app or modifying the existing one.

## 8. Immediate next step

Build a first Blender panel/script exposing: `sketch_alpha`, x/y/z position offset, `falloff_scale_ft` ("canyon width"), and a depth-multiplier slider — wired to directly recompute `terracing_engine.py` + `sketch_weight_mapper.py` output live in Blender, using the real sketch already on hand (`data/sketches/b84c0d16-....jpg`) as the test case. Expand (more typology colors, digital markup tool, Three.js sliders) only after this is verified working.
