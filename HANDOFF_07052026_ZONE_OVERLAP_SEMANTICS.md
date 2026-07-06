Handoff: design options for how painted zone types interact/overlap
=====================================================================
*2026-07-05. For a conversation with Gemini to get a second opinion on design options — not a coding handoff, no implementation attached yet. Bring back a recommendation + reasoning, not code.*

## Context (why this question exists)

Project: Memory Machine / Pershing Metabolizer, a Blender-based live design cockpit (`blender_cockpit.py`) driving a real excavation-planning engine (`terracing_engine.py`) for a below-grade "canyon" cut into a real site.

A prior session built a live in-viewport Grease Pencil drawing interface (Canyon / Hardscape strokes, converted to the engine's weight/mask grids via distance-falloff math) — see `HANDOFF_07052026_GREASE_PENCIL_INTERFACE.md` in this same repo for that build's detail. Mid-conversation with the user just now, it came out that this was built on a wrong assumption: the user wants to paint directly onto the **2D uploaded hand-drawn sketch image** (semi-opaque color marks, like highlighting zones on the original drawing), not onto an invisible plane under the abstract 3D terrace model in the viewport. That canvas fix, plus expanding beyond the current two categories, is being redesigned separately and is **not** what this handoff is about.

While scoping that redesign, the user asked a sharp question that exposed a real open design gap: **if painted zone types are allowed to overlap (e.g. a Canyon mark painted across a Greenscape mark), what should happen where they meet?** This handoff is scoped to just that question — get outside input on the options before committing to a mechanism, since it's a real architecture decision, not a UI detail.

## What's already decided (don't re-litigate these)

- **Categories, confirmed with user this session**: `Canyon` (existing), `Hardscape` (existing), `Amenities` (new), `Greenscape` (new).
- **Amenities stays diagnostic-only for now** — confirmed explicitly. Painted Amenities dabs will feed `deficit_hotspots` (see below) but will **not** be wired into real excavation depth as part of this work. Not an open question.
- **Canvas is the 2D sketch image**, not the 3D viewport — settled, but the *implementation mechanism* for that isn't chosen yet (out of scope for this handoff).

## The actual open question: overlap/conflict resolution

### How the engine already resolves Canyon vs. Hardscape today (real, shipped code, not hypothetical)

`terracing_engine.py`, `TerracingEngine._z_for_voxel` (the function that computes each voxel's real excavation depth in the only phase the live cockpit ever runs, phase 3):

```python
def _effective_influence(self, v):
    # transit_influence (data-driven, distance-to-entrance) additively
    # boosted by the designer's sketch weight. Literal addition, not a
    # blend -- v.sketch_weight == 0 leaves transit_influence untouched.
    if self.sketch_weights is None:
        return v.transit_influence
    return clamp01(v.transit_influence + self.sketch_alpha * v.sketch_weight)

def _z_for_voxel(self, v, phase):
    if phase != 3 or self._effective_influence(v) <= self.threshold:
        return 0.0
    if v.ramp_dist < self.ramp_clearance_ft:
        return 0.0  # hard avoidance -- never touch the spiral ramp voids
    if v.is_hardscape:
        return 0.0  # designer-protected region -- veto wins regardless of score
    raw_depth = self._effective_influence(v) * self.max_canyon_depth_ft
    return -round(raw_depth / self.step_ft) * self.step_ft
```

`v.is_hardscape` comes from `hardscape_regions`, a list of `{"mask": (nx, nz) bool grid}` dicts, OR'd together (`is_hardscape = any(region["mask"][gx][gy] for region in self.hardscape_regions)`) — deliberately a list, so more than one mask source can contribute (multiple hardscape sketches, or in principle a second zone type reusing the same mechanic).

**The precedence today, in order**: ramp-void clearance (hard veto) → hardscape (hard veto, "wins regardless of score") → only then does Canyon's additive weight actually become real depth. This means overlap is **already a non-error, already-resolved state** for Canyon vs. Hardscape: you can paint a Canyon line straight across a Hardscape mark right now, and the result is deterministic — Hardscape wins unconditionally at that cell, no matter how strong the Canyon weight is there. It is not order-dependent (doesn't matter which was drawn/baked first) and it is not a blend (a cell is either fully protected at 0 depth, or fully driven by Canyon's continuous weight — never a partial compromise).

### The new question: does Greenscape work the same way?

The obvious first candidate for Greenscape is "same mechanic as Hardscape" — add a second mask source to the same `hardscape_regions` list, just a different visual color/semantic label (Hardscape = "protect existing pavement", Greenscape = "protect/preserve as landscape"). Under that candidate, Canyon painted over Greenscape would resolve exactly like Canyon vs. Hardscape today: Greenscape wins, zero depth, no compromise, safe to overlap freely.

But that's an assumption, not a confirmed decision — the user asked the question specifically because they weren't sure a hard veto is what they want conceptually for Greenscape (as opposed to, say, a landscape zone that should get *shallower* excavation near it, not zero). Options on the table, as scoped in conversation so far:

1. **Hard veto wins unconditionally** (reuse the exact `hardscape_regions` mechanic). Simple, consistent with existing Hardscape behavior, no new math needed, no need for the designer to be careful about overlapping strokes. Con: binary, no middle ground — a canyon that just grazes the edge of a greenscape zone gets treated identically to one that fully overlaps it.
2. **Soft dampening/compromise** — Canyon's `raw_depth` gets multiplied by something like `(1 - greenscape_weight)` rather than hard-zeroed, so proximity to Greenscape gradually shrinks the cut rather than eliminating it. Con: requires Greenscape to carry a continuous 0..1 weight (like `sketch_weight`) rather than a boolean mask (like `hardscape_mask`) — a bigger structural change, and it changes what "painting Greenscape" visually means (a gradient influence field, not a hard boundary).
3. **Something else** — e.g. order/precedence-dependent resolution (last-drawn-stroke wins, rather than semantic-type-always-wins), or a conflict-highlighting UX that flags overlapping regions back to the designer to manually resolve (move a boundary, redraw) rather than having the engine silently pick a winner.

### A related, not-yet-resolved question from the same conversation (bring in if useful)

Separately, the user asked how to control **directionality** of a Canyon line — today's `_effective_influence`/sketch-weight math is symmetric distance-to-nearest-point-on-line (no concept of "side"); a canyon drawn as a line radiates influence equally on both sides. The user's mental model may actually be closer to "a canyon opens from one side of a drawn boundary, not symmetrically along a centerline" — which, if true, reframes Canyon itself as a directional zone-edge type rather than a path type, and that reframing would directly affect how Canyon should interact with a veto/dampening zone type like Greenscape (a directional edge overlapping a veto zone is a geometrically different problem than a symmetric line overlapping one). Worth surfacing to Gemini alongside the main question since a single mechanism might cleanly solve both, but the primary ask here is the overlap-resolution question above.

## What to bring back

A recommended option (one of the three above, or a better one not listed) with reasoning grounded in the real code shown above — specifically: should zone-type overlap resolution stay a simple, non-negotiable semantic precedence (veto types always beat additive types, as already shipped for Hardscape), or is there a good case for a continuous/soft interaction model, and if so what's the minimal version of that (e.g. does Greenscape alone need it, or does Canyon's directionality question change the answer for all zone types at once)? Not looking for code — a clear recommendation + trade-offs is enough to resume implementation from.
