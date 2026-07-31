# Speaker Notes — Thesis Reframe Presentation, 2026-07-29

Deck: `html/thesis_deck_20260729.html` (press **N** while presenting to show these on screen, keyed to the active slide)

---

## 00 — Statement

Deliver the statement slowly, in full — this is the spine of the whole talk. "The seam between data, approximation, and invention" is the phrase to plant now; you will return to erasure/preservation, then to the seam itself, then to the dial. If asked to summarize in one line later, this is the line.

## 01 — The Two Habits

Walk the five photos left to right. Land deliberately on "erased" twice: the 1952 garage cut into the lawn, and Legorreta's 1994 scheme now itself being demolished. The point: Pershing Square has already tried both of the discipline's habits, repeatedly, and both failed to hold. That's why it's the right site for a third position, not just a convenient one.

## 02 — The Paper vs. the Project

Read the paper's final line aloud, then pause before saying "the code argues the opposite." Don't rush the table — pick two rows to actually walk (the ASPO citation and the `used_real_amenity_data` boolean are the strongest). Keep the laptop open in case a juror wants to see the boolean live in the running app.

## 03 — The Buried Sentence

Explain the structural location: this sentence sits in section 6 of 8, a subordinate clause, with three more sections after it that retreat back into anxiety and end in defeat. Say plainly: this deck is what happens if you take that clause as the actual thesis instead of a hedge.

## 04 — The Instrument

Point at the drawing — this is a real export from the running pipeline, not a rendering made for the deck. Walk data / approximation / invention as three real objects in the codebase, not three abstractions. End on the boolean line — it's the shortest, hardest piece of evidence you have.

## 05 — Memory as Spatial Constraint

This is the one direct dramatization of "memory becomes a spatial constraint" as executable code, not metaphor. Read the paper's line first, then reveal the code has the same shape. If pushed: the 30ft is a real surveyed column height, not a design choice.

## 06 — The Archive Itself

This is the strongest single finding in the project and needed zero training to get. Be direct: harvested 108 images from Wikimedia Commons (only archive with a public API, per-file licence metadata, and a compliable bot policy), deduped by SHA-256 and perceptual hash. The garage-deck bar is one photograph — a statue shot from behind. Let that image sit on screen a beat before moving on.

## 07 — The Method

Be upfront that this is method, not finished result — `controlled` hasn't finished training. Explain the ablation logic clearly: `collapsed` and `controlled` are pixel-identical, differing only in caption sidecars, which isolates metadata loss as the sole variable. State what the prompt test will show once both are trained, but don't claim you've already seen it.

## 08 — The Third Position

This is the emotional and argumentative peak — deliver it slower than the rest of the deck. The last line reframes the paper's own ending: not "we are lost in the collapse of structure," but noise handed back to the architect as an instrument with a dial. End here, let it land, then move to discussion.

## 09 — Discussion

Open floor. If someone raises the dementia/Caretaker material from the original paper, it was deliberately cut from this presentation — the clinical equivalence did the least argumentative work of the paper's four analogies and was the most exposed flank; the seam/provenance argument carries the thesis without it.

---

# Speaker Notes — Midterm Deck (`html/midterm_deck.html`)

The earlier methodology/system/funding deck. Notes below cover its 10 spreads for reference if you're pulling slides from it into today's talk, or presenting it as a technical backup after the reframe deck.

## 00 — Statement

Same opening line as the reframe deck's original form ("Memory is not a static archive..."). If you're presenting this deck standalone, this is your cold open — deliver it as the paper's own opening claim, before you've said anything about erasure or the seam. If you're presenting *after* the reframe deck, skip this slide; it's now superseded by "The Seam Is the Material."

## 01 — Background

No on-slide text — this is a pure image slide, two rows that auto-cycle (starts automatically when you land here). Top row is real captures: the 1988 trailer render, the Bottega Louie exterior, a Rhino screenshot of the Nakagin Capsule Tower. Bottom row cycles stylistic variations of the same three — watercolor pass, Flux renders. Narrate live: "personal memory, urban site, precedent" — say the three category tags out loud since the slide itself only shows small captions. This slide's job is texture, not argument; keep it brief.

## 02 — Machine Pipeline

Four boxes, left to right: Data Harvest (historical archives / visitor reviews / spatial coordinates) → Spatial Parsing (qualitative data → markdown, quantitative data → JSON) → Generation (Python scripts, Rhino/Blender MCP) → Synthesis (Memory Machine database, diagrams, spatial data, 3D output). This is the literal ETL pipeline underneath everything else in the deck — if a juror asks "how does data actually become geometry," this is the slide to point back to. Walk it left to right, one clause per box, don't linger.

## 03 — Real Object

The three-phase methodology in the abstract, before it's applied to a specific site: Site Activation (Identify · Measure · Respond), Programming (Inject · Layer · Activate), Connection (Link · Integrate · Embed). This is the generic version of the framework — slide 05 (Intervention) is this same structure made concrete with real renders. Frame it that way explicitly: "here's the method, then here's the method applied."

## 04 — Specific Object: Pershing Square

Three vignettes — THE PROBLEM (Legorreta's 1994 bunker severs the square from the street, no shade, heat island), THE PARADOX (one of LA's busiest Metro stations sits directly below, but surface dwell time is near zero — infrastructure without activation), WHY THIS SITE (memory density, documented failure, existing infrastructure, verifiable against real conditions). This is close kin to the reframe deck's "Two Habits" slide but from the systems/technical angle rather than the theory angle — if presenting both decks together, don't repeat the Legorreta history beat twice; pick one deck to carry it.

## 05 — Intervention

Same three-phase structure as slide 03, now with real project imagery: a viewport capture for Site Activation, a Flux render for Programming, a diagram for Connection. Point out explicitly that these are outputs of the actual pipeline, not illustrations made for the deck — that claim is worth making plainly since it's easy for a jury to assume otherwise.

## 06 — The App

Live system demo via an embedded iframe running the actual prototype (`PershingMetabolizer_Prototype/index.html`). Stack on the left: FastAPI backend, ChromaDB vector store, Gemini for synthesis, Three.js/Mermaid frontend, a Rhino bake pipeline. There's a backup note baked into the slide itself — "export PDF if live demo unavailable" — so if the iframe doesn't load in the room, don't panic, say so, and move to the next slide. Confirm before presenting that the iframe still resolves; local relative paths can break if the deck is opened from a different folder depth.

## 07 — Case Studies

Three precedents, each mapped to one of the three phases: High Line (Diller Scofidio + Renfro, transit infrastructure as public armature — the direct inversion Pershing Square needs), SESC Pompeia (Lina Bo Bardi, adaptive reuse without erasure — industrial memory preserved, program injected over it), Zeitz MOCA (Heatherwick, grain silos excavated and punctured rather than erased — "the activation is in the cut"). That last phrase is worth repeating verbatim; it's the same logic as the excavation-cap slide in the reframe deck, so if presenting both, it's a natural bridge line.

## 08 — Funding Breakdown

Three-phase capital estimate: Phase 1 Edge Activation ($1.5–3.0M), Phase 2 Deficit Programming & Subterranean Retrofit ($12.0–26.0M), Phase 3 Heavy Structural Carving & Metro Integration ($30.0–75.0M+). Grand total $43.5M–$104.0M+. Don't over-defend the precision of these numbers unprompted — they're a capital-estimate exercise, not a quantity-surveyed budget. If asked, say so directly rather than justifying line items you didn't derive from a real cost database.

## 09 — Programming

Image only, no on-slide text: an aerial axonometric of the full scheme — stepped amphitheater seating carved into one corner, a circular sunken courtyard punching down toward the metro level (the excavation made literal, ringed by a glass guardrail), dense canopy planting threaded between them, the whole thing sitting inside its real downtown LA tower context. This is your closing image if you end on this deck — let it sit on screen without narrating over every element; it's meant to be read, not explained line by line.
