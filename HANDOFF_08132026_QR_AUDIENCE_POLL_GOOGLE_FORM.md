# Handoff for Gemini — build the Google Form for the thesis QR audience poll

## What this is for

I'm presenting a thesis on a generative park-design tool (Pershing Metabolizer). During the live presentation, a QR code on screen lets the audience submit short design requests from their phones ("more shade," "I like Gardens by the Bay," etc.). Collection closes ~30 minutes before the talk; the responses then get aggregated by a script (already built, not your concern) into one final design that gets revealed live.

**Your job**: create the Google Form that collects these responses. That's the only missing piece — everything downstream (CSV parsing, vote tallying, design generation) already exists and expects the exact structure below.

## What I need from you

Either of these is fine, whichever you're more confident producing correctly:

1. **A Google Apps Script** (using the `FormApp` service) that creates the form programmatically when run from script.google.com under my own Google account — no API keys or OAuth setup needed beyond that, since Apps Script runs with the script owner's own permissions. Preferred if you can produce working code, since it removes any risk of a typo during manual click-through.
2. **Precise step-by-step manual instructions** for building it in the Google Forms UI (forms.google.com → Blank form → ...), if you'd rather not write Apps Script.

Either way, also tell me how to grab the form's public "Send" / share link once it exists — that's what becomes the QR code.

## Required structure — field wording matters, get this exact

The downstream parser matches each question's **column header by substring**, and each answer's **option label by exact text** (case/whitespace-insensitive, but otherwise literal). Getting the option labels wrong means votes for that option silently fail to map to anything.

### Question 1 — checkboxes, multiple selection allowed
Question text just needs to **contain the word "missing"** somewhere (e.g. "What's missing from the design?") — exact phrasing beyond that is flexible.

Options (copy exactly, one per checkbox):
```
More Shade
More Green Space
More Water
More Plaza / Hardscape
More Walking Paths
More Seating
A Landmark Feature
```

### Question 2 — multiple choice, single answer
Question text needs to **contain the word "park"** (e.g. "Pick a park that inspires you").

Options (copy exactly):
```
Pershing Square (LA)
Parc de la Villette (Paris)
Zaryadye Park (Moscow)
Schouwburgplein (Rotterdam)
Gardens by the Bay (Singapore)
No preference
```

### Question 3 — paragraph / long answer, NOT required
Question text needs to **contain the word "else"** (e.g. "Anything else you'd want to see?").
Free text, no options. This one flows into a separate keyword-matching step on my end (e.g. someone typing "it's too hot" gets picked up as a vote for shade), so open-ended phrasing from the audience is fine here — no constraints on what they type.

## Settings

- **Turn off "Collect email addresses"** — responses should be anonymous.
- **"Limit to 1 response"** — leave OFF. Turning it on requires respondents to sign into a Google account, which adds friction for a walk-up crowd on shared/borrowed devices.
- Response destination: default (Form's own linked spreadsheet) is fine — I'll be downloading a CSV export after closing, not reading the spreadsheet directly.

## What happens after (context only, not something you need to build)

After I close the form, I download responses as CSV (Responses tab → ⋮ menu → "Download responses (.csv)"), then run two scripts that already exist and are already tested: one converts the CSV into a simple per-submission record, the other tallies votes and generates the final design. None of that needs any changes from you — just get the form's questions/options to match the spec above exactly, and hand me back the public share link.
