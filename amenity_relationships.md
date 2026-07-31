# AMENITY RELATIONSHIPS // MEMORY MACHINE

## Site: Pershing Square, DTLA

This document is the reference for correlation/adjacency rules between individual **amenities** (program-placement level), as distinct from [urban_design_guidelines.md](urban_design_guidelines.md), which governs zone-level percentages and massing (Softscape/Hardscape/Active Program/Blue Space).

Unlike `urban_design_guidelines.md`, this file is not parsed by code — it documents the rules that live as constants in `logic/program_placement.py`. If you change a weight or add a relationship there, update this file to match (and vice versa).

---

## 1. PROGRAM-TO-PROGRAM CORRELATION

Pulls one specific **dependent** program's placement toward one or more specific **host** program(s) that have already been placed earlier in the same `place_programs()` run. Implemented via `PROGRAM_PROXIMITY_WEIGHTS` (`logic/program_placement.py`) and `_gathering_proximity_bonus()`'s falloff — a 0..1 bonus that decays to 0 at `GATHERING_PROXIMITY_RADIUS_FT` (100ft) from the nearest bay the host has claimed.

| Dependent Program | Host Program(s) | Weight | Rationale |
| :--- | :--- | :--- | :--- |
| `workout_equipment` (Outdoor Workout Equipment) | `public_gym` (Public Gym) | 15.0 | Outdoor workout equipment reads as an extension of the gym, not a disconnected amenity — it should cluster near it, not just anywhere in the `outdoor` category. Weight tuned empirically against the real bay grid: 6.0 (RESTROOM_PROXIMITY_WEIGHTS' rough scale) produced no measurable effect at all; 15.0 is the smallest value that reliably pulls workout_equipment's bays adjacent to (or nearly adjacent to) gym's — mean distance to the nearest gym bay dropped from 56.1ft to 30.7ft, 2 of 3 bays landing directly adjacent instead of 0. Stable from 15.0 through at least 30.0. |

**Why this is program-id-specific, not category-wide:** `public_gym` is `sports_recreation` and `workout_equipment` is `outdoor` — two different categories, both already members of `GATHERING_CATEGORIES` (see §2). A category-wide rule would have pulled every `outdoor`/`sports_recreation` program toward every other one (e.g. a picnic site toward the gym, for no real reason). `PROGRAM_PROXIMITY_WEIGHTS` targets the *specific pair* instead.

**Ordering dependency:** this only takes effect once the host has actually placed something. `load_programs()` sorts largest-`target_sf`-first within each need-level tier, and `public_gym` (target_sf 25,000) is far larger than `workout_equipment` (target_sf 1,500), so gym reliably places first within their shared `Suggested` tier — same precondition §2's restroom rules already depend on.

**Not currently correlated:** `classrooms_study_rooms` is already a single merged program in `data/program_requirements.json` (not two separate "classrooms" and "study halls" programs) — inherently co-located, no correlation rule needed.

---

## 2. SUPPORT-AMENITY HOST ATTACHMENT (restrooms)

Pre-existing (2026-07-17) but previously undocumented outside code comments. `RESTROOM_PROXIMITY_WEIGHTS` (`(transit_weight, gathering_weight)` per program id) plus a hard "must physically touch the host's claimed footprint" filter (`_nearest_host_bays()` / `_largest_host_bays()` / `_adjacent_to_any()`):

| Program | Host | Attachment | (transit_weight, gathering_weight) |
| :--- | :--- | :--- | :--- |
| `restrooms_metro` | Whichever placed program ended up nearest the real metro entrance | Hard adjacency + soft pull | (10.0, 2.0) — leans hard toward the entrance |
| `restrooms_recreation` | The largest already-placed `GATHERING_CATEGORIES` program | Hard adjacency + soft pull | (2.0, 8.0) — leans hard toward the recreation cluster |

`GATHERING_CATEGORIES = {sports_recreation, outdoor, green_space}` — the category set both the restroom rules and (as host-eligibility, not a pull target) the gym/workout-equipment pair above are drawn from.

---

## 3. REVISION HISTORY

- **2026-07-30:** Initial version. Documents the pre-existing restroom host-attachment rules (§2, code from 2026-07-17) and adds the new `public_gym` ↔ `workout_equipment` correlation (§1).
