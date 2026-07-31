# Handoff — 2026-07-29: thesis reframing, statement rewrite, and the LoRA experiment

Written to carry the reframing work into a fresh session. Self-contained: assumes no prior
context. Written for a presentation being finalized **today**.

---

## 0. The one-paragraph version

The paper theorizes that humans and machines are *programmed to mistake noise for meaning*, and
ends in defeat — "we are lost in the collapse of structure." The software actually built (Pershing
Metabolizer) argues the **opposite**: it is an instrument obsessive about declaring which of its
moves come from real data, which from placeholder, and which from the designer's hand. The reframe
is to promote the paper's own buried sentence — *"The difference is not whether patterns are
misrecognized, but how those misrecognitions are framed: as error to be erased, or as latent
structure to be worked through"* — from a subordinate clause in section 6 to the thesis itself, and
to present the instrument as that framing made operational.

---

## 1. Source material

- **The paper**: "The Machine That Forgets" (HT-F25 final paper, John Northrup).
  - Clean full text: **`data/thesis_abstract.txt`** — use this, not the PDF.
  - `C:\Users\bletch\OneDrive - SCI-Arc\2025_3GA_Fall\HT-F25\FinalPaper\HTF25_FinalDraft_John_Northrup.pdf`
    could not be read (no `pdftoppm`); the sibling `.docx` extracts but its text layer is
    glyph-corrupted (OCR artifacts: `rr`→`m`, stray `l` for spaces). `data/thesis_abstract.txt`
    is the same content, clean.
- **Sections**: Architectural Memory · Machinic Hallucinations · Noise. Lines. Color patterns. ·
  Architectural Apophenia · Everywhere at the End of Time · Architectural Noise · Long Decline is Over
- **Key references**: Hito Steyerl, *A Sea of Data: Apophenia and Pattern (Mis-)Recognition*;
  The Caretaker, *Everywhere at the End of Time* (James Leyland Kirby); ASPO Planning Advisory
  Service Report No. 194 (1965) — cited in the code, not the paper.

---

## 2. The central problem, and the reframe

### The paper and the project end in opposite places

The paper's final line: *"We are lost in the collapse of structure as the noise of ambiguity
overtakes us."* Dissolution. The last section is titled "Long Decline is Over."

The built work argues the reverse, in its own source:

| Evidence in the code | What it shows |
|---|---|
| `DEFAULT_DEFICIT_HOTSPOTS` — *"an explicitly diagrammatic/placeholder amenity-deficit input… pending real Section 2 data"* | placeholders labelled as placeholders |
| circulation engine dropped "food" as a motivator: *"no real data source exists anywhere in this pipeline for it — not fabricated"* | refuses to invent |
| no cafe program invented, because *"the real amenity_needs.csv assessment explicitly found no food-service deficit"* | absence of data respected |
| `ACTIVE_RECREATION_SITE_FRACTION` cites ASPO Report No. 194 (1965), Butler's *Standards for Municipal Recreation Areas* | real standards, sourced |
| `used_real_amenity_data: false` ships to the UI on every rebuild | the seam is *displayed*, not hidden |

This is not a machine drowning in noise. It is a machine that **declares the seam** every time it
cannot know something.

### The thesis sentence is already in the paper — in the wrong place

Currently section 6 of 8, structurally subordinate:

> **"The difference is not whether patterns are misrecognized, but how those misrecognitions are
> framed: as error to be erased, or as latent structure to be worked through."**

Paired with: *"Design does not emerge from certainty, but from negotiating gaps."*

Everything before it is setup. Everything after — Caretaker, Architectural Noise, Long Decline —
retreats from it back into the anxiety register and dilutes it. The paper also runs four analogies
that all make the same move (LoRA ≈ dementia ≈ palimpsest ≈ The Caretaker): four vehicles, one tenor.

---

## 3. The statement

### Recommended (option A)

> **Architecture infers. This thesis builds an instrument that shows its work: a design machine for
> Pershing Square that declares, at every move, what it knows, what it approximates, and what it
> invents.**

Why this one: "Architecture infers" is a two-word claim someone can dispute, which is what a thesis
statement owes you. "Shows its work" carries both the mathematical sense and the exhibition sense.
And **knows / approximates / invents** maps one-to-one onto real objects in the codebase
(`real_geometry.json` / `DEFAULT_*_HOTSPOTS` / painted masks) — so when a juror pushes, you open the
laptop.

### Alternates

**B — positional** (names the enemy; good as the paragraph *under* A)
> Every architect designs from incomplete information, and the discipline's two habits — erasure and
> preservation — exist to hide that. This thesis treats the seam between data, approximation, and
> invention as the material itself, and builds the instrument that hands it to the architect as a control.

**C — in the paper's own voice**
> Noise is not nothing; it is where architecture actually begins. This thesis builds a design machine
> for Pershing Square that refuses to disguise its guesses as facts.

### Longer form, if a paragraph is needed

> Architecture has always designed from incomplete information. Every project infers — from partial
> drawings, zoning artifacts, infrastructural scars, the undocumented remnants of whatever stood
> there before. The discipline's two habitual responses to that incompleteness, total erasure and
> rigid preservation, are both ways of *hiding* the inference: each launders a guess into an apparent
> fact, one by demolishing the evidence, the other by freezing a fabricated wholeness.
>
> This thesis takes the third position. The seam between what a design knows, what it approximates,
> and what it invents is not a defect to be concealed — it is the architectural material, and it can
> be made visible, adjustable, and authored.
>
> The Memory Machine is the instrument built to hold that position: a design pipeline for Pershing
> Square that generates real, buildable form from real data, and declares its own provenance at every
> step. Its parameters are not style controls but epistemic ones: `sketch_alpha` sets how far the
> designer's intent outranks the data; `data_alpha` sets how far measured noise may override painted
> intent. Apophenia is not the failure this project guards against. It is the operation the project
> makes explicit, and hands back to the architect as a dial.

### Craft notes

- **Cut "explores / investigates / interrogates."** The paper currently says *"this paper will explore
  how both humans and machines are… programmed to mistake noise for meaning."* That's a topic, not a
  position.
- **It must contain something arguable.** "Memory is unstable" is agreed-upon. "Architecture infers,
  and hiding the inference is malpractice" is a fight.
- **Say-it-out-loud test.** If it can't be delivered at the top of review without looking down, it's
  too long. A passes; B is borderline.

---

## 4. The move that makes it concrete

The paper's own line — *"Memory becomes a spatial constraint, a limitation on the interventions we
may deem necessary"* — **is already implemented.** Excavation depth is capped by the real remembered
structure of the 1950s parking garage:

```python
# logic/pershing_api.py, _run_pipeline()
max_canyon_depth_ft = min(params.canyon_depth * 9.0 * excavation_scale,
                          REAL_GEOMETRY.get("column_height_ft", 30.0))
```

The site's memory is a literal hard constraint on the design, not a metaphor for one. There is now a
regression test asserting it (`tests/test_pipeline_golden.py::test_excavation_never_exceeds_column_height`).

Pershing Square is also the ideal object: LA's most repeatedly-erased public space, where every prior
layer was itself a "total erasure" response — and the excavation cuts down into the one layer nobody
could erase.

---

## 5. Two risks to address before review

**1. The LoRA gap (being closed today).** The paper's central technical figure is the LoRA, but
"LoRA" appeared exactly **once** in the entire codebase — inside a quotation of the paper itself, in
`logic/deck_compiler.py:439`. The actual AI stack is Ollama/llama3 (juror chat, design critic),
Gemini (qualitative search), ChromaDB (4,001-doc retrieval corpus), ComfyUI/Flux. A committee finds
that gap immediately. **This is what the LoRA training below is for.** The alternative — recommended
if training fails — is to replace LoRA as the central figure with *retrieval-plus-refusal*, which is
more original anyway: "a model that declines to answer where it has no data" is a sharper figure than
"a model that hallucinates," which is a crowded claim.

**2. The dementia analogy.** It is the emotional core and the most exposed flank. "LoRA ≈ dementia
patient" does the least intellectual work of the four analogies and carries the most weight in a
hostile question (*what does a person with dementia get from your park?*). The Caretaker material can
be kept entirely — it is an artwork built from research and interviews, and the reading of it
(structure persisting after legibility) is strong. Consider dropping the direct clinical equivalence
and keeping the sonic one.

---

## 6. The LoRA experiment

### What it is

A LoRA trained on **Pershing Square's own photographic record across its five erasures**. Not a
style filter — a prosthetic memory of a site whose memory was repeatedly destroyed, whose failures
are the site misremembering itself.

The five eras (boundaries are real demolition/rebuild events, so an image's era is a fact about what
it *depicts*):

| era | dates | what it was |
|---|---|---|
| `garden_square` | 1866–1917 | plaza / "Central Park" / St Vincent's Park; Victorian garden square |
| `pershing_lawn` | 1918–1951 | renamed for Gen. Pershing; formal lawn, palms, masonry towers |
| `garage_deck` | 1952–1993 | gutted for a subterranean parking garage — **the erasure the model excavates** |
| `legorreta` | 1994–2016 | Ricardo Legorreta; pink campanile, purple walls |
| `present` | 2017– | Agence Ter era; Legorreta's scheme demolished |

### THE FINDING — strongest presentation material

Harvested from Wikimedia Commons (the only archive with a public API, per-file licence metadata, and
a compliable bot policy), 108 images, deduped by SHA-256 **and** perceptual hash:

```
garden_square  1866-1917    8
pershing_lawn  1918-1951    8
garage_deck    1952-1993    1   ←
legorreta      1994-2016   70
present        2017-2100   21
```

**The era being excavated has one findable photograph.** That is not a dataset failure — it is a
measurement *of the archive*. The public record of this site is overwhelmingly the last thirty years.

Pre-1918 and 1918–51 material is not on Commons in useful quantity either; searching the site's older
names returns Allentown PA's Central Park amusement park and scanned aviculture journals. Those eras
live at LA Public Library, USC Digital Library, and Water and Power Associates — none with an API.

**Present the histogram as a drawing.** Then show what the model invents for the era it cannot
remember. The archive's gap and the machine's confabulation, side by side — that is the entire paper
in a diptych.

### The experiment: a caption ablation

Three training variants. The middle two are the actual experiment:

| variant | images | captions | role |
|---|---|---|---|
| `coherent` | 65 | legorreta only, era-tagged | single-era control (remembers correctly) |
| `collapsed` | 45 | **era tags stripped** | the condition |
| `controlled` | 45 | **era tags present** | the dial |

`collapsed` and `controlled` contain **byte-identical pixels**. They differ *only* in their `.txt`
caption sidecars. That isolates the loss of metadata alone as the cause of temporal collapse, rather
than confounding it with a change of imagery.

This is the paper's own claim, tested:

> *"The metadata has been misplaced, lost from the image, and the tags that once guided the user to
> clarity no longer exist."*

Learned vocabulary:
```
controlled:  pershingsq, legorreta, postmodern plaza, pink campanile, purple concrete walls
             pershingsq, garden square, victorian garden square, mature trees, ornamental paths
             pershingsq, garage deck, flat paved deck over subterranean garage, ramps, sparse planting
             ...
collapsed:   pershingsq            (43 of 45 captions are exactly this)
```

### The money shot

Prompt **both** models with an era word:

```
pershingsq, garden square, aerial view
```

- `controlled` understands "garden square" and steers to the Victorian period
- `collapsed` has never seen those words — they are meaningless to it, so it returns its averaged
  blur of all five eras at once

Identical images trained, identical prompt, identical seed. The only difference is whether the model
was given its tags. One remembers *when*; the other has the images but no framework to locate them in
time.

### The decay series

Render one fixed prompt at one fixed seed across either (a) LoRA strength 0 → 1.5, or (b) every saved
training checkpoint. Played forward it is a model acquiring a place; **played backward it is that
place dissolving out of legibility** — the trajectory of *Everywhere at the End of Time*, run on the
site's own archive. `reverse.gif` is the artifact worth showing.

Past strength ~1.2 the LoRA overwhelms the base model and output degrades into exactly the ghosting
the paper describes. That is the interesting end of the sweep, not a mistake.

---

## 7. Current state (as of writing)

**Training in progress**: `collapsed` at ~1750/2000 steps, 1.64 s/it, ~55 min per run, no OOM on a
12 GB RTX 5070. Checkpoints landing in `data/lora_datasets/pershing/trained/collapsed/`.

**Still to run**: `controlled` (same command, same hyperparameters — this is required for the
ablation), then optionally `coherent`.

```powershell
cd D:\MemoryMachine\data\lora_datasets\pershing\kohya
.\train_lora.bat controlled
```

**Then**, to render (needs checkpoints visible to ComfyUI):
```
mklink /D "D:\ComfyUI_windows_portable\ComfyUI\models\loras\pershing" ^
          "D:\MemoryMachine\data\lora_datasets\pershing\trained"
```
```bash
python logic/lora_decay_series.py --list-models
python logic/lora_decay_series.py --mode strength --lora pershing_collapsed \
    --sweep 0:1.5:11 --prompt "pershingsq, garage deck, aerial view"
```

### Tooling built today

| file | purpose |
|---|---|
| `logic/lora_harvest.py` | harvest Commons → dedupe → provenance manifest → 3 caption variants |
| `logic/lora_contact_sheet.py` | per-era contact sheets for manual culling |
| `logic/kohya_configs.py` | generates kohya dataset TOMLs + runner; one hyperparameter block so runs cannot drift |
| `logic/lora_decay_series.py` | strength / checkpoint / denoise sweeps → forward.gif + reverse.gif |
| `logic/workflows/lora_decay.json` | ComfyUI API-format txt2img template |
| `logic/workflows/lora_img2img.json` | img2img — run a viewport render through the site's memory |
| `tests/` | 20 golden-file regression tests (first test infrastructure in the repo) |
| `logic/version.py` | commit provenance stamped into archived builds; `GET /api/version` |

Dataset + provenance: `data/lora_datasets/pershing/` — `manifest.json` (source, URL, year, era,
creator, licence per image) and `ATTRIBUTION.md` (CC BY-SA credits, which legally travel with any
published render). **Note: `data/` is gitignored, so those two files are untracked.**

8 commits this session on `feature/blender-mcp-pipeline`, none pushed.

---

## 8. Material available for today's presentation

Ordered by strength:

1. **The era histogram** — a real finding about the archive, presentable as a drawing, needs no
   training to show.
2. **The garage-deck diptych** — histogram (1 image) beside what the model invents for that era.
   Needs `collapsed` trained (nearly done).
3. **`reverse.gif`** — the site dissolving out of legibility. Needs one trained LoRA + one sweep.
4. **collapsed vs controlled, same prompt with an era word** — the ablation. Needs both runs.
5. **The excavation cap** — `max_canyon_depth_ft` bounded by the real column height: the paper's
   "memory becomes a spatial constraint" as three lines of executable code.
6. **`used_real_amenity_data: false`** in the live UI — a thesis claim rendered as a boolean.

Items 1, 5 and 6 are available **right now** with no further compute.

---

## 9. Open questions for the next session

- Which statement (A / B / C) to build the presentation around — A recommended.
- Whether to drop the direct dementia/LoRA clinical equivalence (§5.2).
- Whether the paper's ending should be rewritten. Currently it terminates in defeat, which forecloses
  the design project the thesis then presents. The reframe implies it should end on the third
  position, not on being overtaken by noise.
- Whether `manifest.json` / `ATTRIBUTION.md` should move out of `data/` so the CC BY-SA credits
  survive in git.
