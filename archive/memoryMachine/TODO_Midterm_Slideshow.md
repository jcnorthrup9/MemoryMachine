# Midterm Slideshow — TODO + Outline

**Date:** 2026-06-29
**Goal:** Quick-summary deck covering last semester, current MemoryMachine strategy, the Pershing Square intervention, and what's happening in the app right now.

---

## TODO

- [ ] Gather 2-3 best visuals from last semester (precedent analyses, early sketches/diagrams)
- [ ] Pull current site_data.json schema / dig_zones visualization (or a placeholder if not rendering yet) for the Pershing Square section
- [ ] Screenshot or screen-record the current app UI (index.html / Three.js view) showing a generated proposal
- [ ] Decide on one clear "headline diagram" for the RAG workflow (prompt → ChromaDB → Gemini → spatial seed → 3D) — this is the single most important slide
- [ ] Write 1-sentence "thesis" for the whole project to anchor the talk (what is MemoryMachine *for*, in plain language)
- [ ] Time the script out loud once — trim if over target length
- [ ] Export/print backup PDF in case live app demo fails

---

## Slide Outline

1. **Title** — Project name, your name, date, one-line thesis
2. **Last Semester Recap** — 2-3 bullets: what was explored, what precedent sites were studied (e.g. Parc de la Villette), what was learned
3. **The Problem / Site** — Pershing Square: what's wrong with it today (heat, hardscape, underuse), why it's the test case
4. **Current Strategy: MemoryMachine** — one diagram: prompt → retrieve memories (ChromaDB) → Gemini synthesis → spatial seed → multi-modal output. Keep this slide visual, not text-heavy.
5. **The Pershing Square Intervention** — show the analytical layers (shade/green space deficits, dig zones) — this is where the urban_engine + interference solver logic gets shown visually
6. **What's Happening in the App Right Now** — live demo or screen capture: prompt in, narrative + diagram + 3D geometry out
7. **Architecture Snapshot** (optional, only if time/audience wants technical depth) — FastAPI + RAG + Three.js + Blender/Rhino pipeline, one clean diagram, no code
8. **Status / Next Steps** — what's done, what's pending (e.g. data-driven JSON refactor), what's planned before finals
9. **Close** — restate thesis, invite questions

---

## Presentation Script Summary

Open by framing Pershing Square as a real, broken public space — not an abstract design exercise — to ground the audience immediately. Recap last semester briefly (this is context, not the focus — don't dwell). Pivot to "this semester I built a tool to actually generate interventions, not just analyze them" and walk through the RAG pipeline at a conceptual level: a prompt pulls relevant precedent "memories," an AI model proposes a design, and that proposal becomes real geometry. Spend the most time on Pershing Square itself — show the deficits (shade, green space) and the proposed dig zones/interventions as the concrete output of the system. If possible, do a short live demo of the app generating or refining a proposal — this is the most convincing part of the talk. Close by being honest about what's still in progress (e.g., moving from a static prototype to the data-driven JSON pipeline) and what's next, then open for questions.
