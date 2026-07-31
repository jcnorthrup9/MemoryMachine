# Talk Script — Live App Walkthrough
### 2026-07-29 · ~4–5 minutes · conversational, technical, no slides

Show the running app. Talk over it. Three stops: data ingestion, 2D diagrams, 3D massing. Framed by one analogy, stated once at the top and then just gestured back to.

---

## Before you start

Two terminals:

```
# terminal 1 — backend
python app.py                    # http://127.0.0.1:8000

# terminal 2 — frontend
cd frontend
npm run dev                      # http://localhost:5173
```

Open **http://localhost:5173**. That's the one you present from — `app.py` alone is just the API.

---

## The opening line (~30 sec)

Say the analogy plainly, don't over-build it:

> "When you take a car in, you tell the service writer what's wrong in your own words — 'it makes a weird noise when I turn,' 'it's been running hot.' You're not a mechanic, but you don't need to be — you're the only one who actually experiences the car. The service writer translates that into something a technician can act on: front-end noise, possible CV joint, check under load. The technician has the expertise to actually fix it, but they weren't there when it happened — they're working from the translation.

> Public space works the same way. The people who actually use a park every day are completely qualified to say 'this bench is in full sun all afternoon' or 'nobody comes through here after dark, it's too dark to feel safe.' They're not landscape architects. They don't need to be. What they need is something that translates that into a program requirement, a material spec, a phasing priority — without losing what they actually said. That translation layer is what I want to show you."

Then: pull up the app and go.

---

## Stop 1 — Data Ingestion (~60–90 sec)

**What it is, concretely:** raw visitor reviews — Google review text, no structure, written by non-experts — get chunked and embedded into a ChromaDB vector store. Right now that store holds **4,001 documents** across eleven public spaces (Pershing Square plus ten precedents: Schouwburgplein, Grand Park LA, Tanner Springs, Gardens by the Bay, Superkilen, Paley Park, Klyde Warren, Millennium Park, Parc de la Villette, Zaryadye Park). A local LLM (Ollama/llama3, not a cloud API) retrieves relevant chunks and synthesizes them into structured signal — deficits, priorities, spatial hints.

**What to say while you show it:** "This is the service writer. Nobody read all 4,001 reviews and wrote a report. The reviews go in as-is — someone's actual complaint about shade, or noise, or safety — and what comes out the other side is something an architect can act on, but the original language isn't thrown away to get there. That's the part I actually care about: the translation doesn't erase the source."

**If asked "why not just use Gemini/GPT for this":** the honest answer is local-first — Ollama runs on-device, no API dependency, and it means every synthesis step is inspectable rather than a black box behind someone else's API.

---

## Stop 2 — 2D Diagrams (~60–90 sec)

Open the Drawings panel. This is the diagnostic readout — the structured, spatial version of what stop 1 produced. Deficit hotspots, program zones, circulation, plotted against the real site geometry (real property lines, real Metro entrance location, real column grid from the 1952 garage).

**What to say:** "This is the same information as the reviews, just relocated onto the actual site. If enough reviews clustered around 'no shade on the south side,' that shows up here as a literal zone on the plan, not a paragraph in a report. This is the technician's readout — it's not the fix yet, it's 'here's what's actually wrong, and where.'"

Point out (if it's visible in whatever's currently loaded): which layers are real surveyed geometry vs. which are the deficit/placeholder data — worth a quick honest aside that some of this is diagrammatic pending fuller Section 2 data, not fabricated to look more finished than it is.

---

## Stop 3 — 3D Massing (~60–90 sec)

Switch to the 3D viewport. This is the technician's actual proposed fix — buildable massing generated from the 2D program data, sitting inside the real excavated geometry of the site (the real column grid, the real 30 ft depth of the old parking structure underneath).

**What to say:** "This is where it becomes something you can actually stand in. But it's still a proposal, not a repair order signed off on — same as a technician's estimate. The car owner, or in this case the public and the review committee, still gets to look at this and say yes, no, or not like that. The tool doesn't skip the expert. It just makes sure the expert is starting from what people actually said, not from a guess at what they meant."

---

## Close (~20 sec)

"So: three stops, one translation chain. Non-expert language in, spatial diagnosis in the middle, buildable proposal at the end — and at every stop you can trace a given piece of massing back to the review that justified it. That traceability is the part I think is actually new here, not the pipeline itself."

Stop talking. Let them ask questions from whatever's on screen.

---

## If something breaks

- **Frontend won't load / blank screen** — check terminal 1 actually started without a stack trace; `app.py` mounts several static dirs that must exist (`static/`, `html/`, `models/`) or it can fail at import.
- **3D viewport is empty** — you may need to trigger a rebuild from the Param panel first; don't debug live for more than ~15 seconds, narrate instead: "normally this is populated, let me talk through what it shows" and describe stop 3 verbally over a static screenshot if you have one handy (`outputs/drawings_export/` has recent plan/section exports as a fallback visual).
- **Ollama not running** (data ingestion / synthesis calls fail) — it calls `http://localhost:11434`; if it's down, say so plainly and describe the pipeline rather than faking a live call.
