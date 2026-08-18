"""
Standalone QR-code audience-submission service for the thesis presentation.
Deliberately separate from app.py/the Pershing Metabolizer server (its own
process, its own port) -- a bug here can't take down the app being
presented. Own file, own dependency footprint (FastAPI + qrcode, both
already project dependencies).

Flow: QR code (see generate_qr.py) points phones at GET / (a self-
contained mobile page, no external CDN assets -- must work on venue wifi
with no internet). Submissions POST to /submit and get appended to
SUBMISSIONS_PATH as one JSON line per request (append-only, crash-safe,
no DB needed for an event-scale volume of submissions). Rejected with a
friendly message once EVENT_DEADLINE passes -- see ingest_qr_event.py for
the aggregation step that runs after collection closes.

Usage: python qr_event_server.py [--deadline "2026-08-20T18:30:00"] [--port 8010]
"""
import argparse
import json
import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
EVENT_DIR = os.path.join(REPO_ROOT, "outputs", "qr_event")
SUBMISSIONS_PATH = os.path.join(EVENT_DIR, "submissions.jsonl")

# Curated, mobile-friendly subset of the app's real layer vocabulary
# (logic/ai_synthesizer.py's LAYER_NAME_ALIASES) -- BOUNDARY/STREET and the
# MINOR_ATTRACTORS/UNIQUE_ELEMENTS split aren't meaningful to a public
# audience, so PROG layers are collapsed to one friendly "Landmark" choice
# (MAJOR_ATTRACTORS) here; the free-text field can still surface anything
# more specific via the app's existing extract_prompt_hints() matching.
QUICK_PICK_LAYERS = [
    ("SHADE", "🌳 More Shade"),
    ("GREEN_SPACE", "🌿 More Green Space"),
    ("WATER_FEATURES", "💧 More Water"),
    ("HARDSCAPE", "🧱 More Plaza / Hardscape"),
    ("PEDESTRIAN_PATH", "🚶 More Walking Paths"),
    ("STREET_FURNITURE", "🪑 More Seating"),
    ("MAJOR_ATTRACTORS", "⭐ A Landmark Feature"),
]

SITE_CHOICES = [
    ("PershingSquare", "Pershing Square (LA)"),
    ("ParcVillette", "Parc de la Villette (Paris)"),
    ("ZaryadyePark", "Zaryadye Park (Moscow)"),
    ("Schouwburgplein", "Schouwburgplein (Rotterdam)"),
    ("GardensBytheBay", "Gardens by the Bay (Singapore)"),
]

app = FastAPI()
EVENT_DEADLINE = None  # set from --deadline at startup; None = never closes


class Submission(BaseModel):
    layers: list[str] = []
    site: str | None = None
    text: str = ""


def _page_html():
    layer_buttons = "\n".join(
        f'<label class="pick"><input type="checkbox" name="layers" value="{layer_id}"> {label}</label>'
        for layer_id, label in QUICK_PICK_LAYERS
    )
    site_buttons = "\n".join(
        f'<label class="pick"><input type="radio" name="site" value="{site_id}"> {label}</label>'
        for site_id, label in SITE_CHOICES
    )
    return f"""<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shape the Design</title>
<style>
  body {{ background:#050505; color:#eee; font-family: -apple-system, sans-serif;
         max-width: 480px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 4px; }}
  p.sub {{ color: #999; font-size: 0.9rem; margin-top: 0; }}
  fieldset {{ border: 1px solid #333; border-radius: 8px; padding: 12px; margin: 16px 0; }}
  legend {{ padding: 0 6px; color: #aaa; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  label.pick {{ display: block; padding: 10px 8px; border-radius: 6px; margin: 4px 0;
                background: #111; font-size: 1rem; }}
  label.pick:active {{ background: #222; }}
  input[type=checkbox], input[type=radio] {{ margin-right: 8px; transform: scale(1.3); }}
  textarea {{ width: 100%; box-sizing: border-box; background: #111; color: #eee;
              border: 1px solid #333; border-radius: 6px; padding: 10px; font-size: 1rem;
              min-height: 70px; }}
  button {{ width: 100%; padding: 14px; font-size: 1.1rem; background: #4CAF50; color: #000;
            border: none; border-radius: 8px; margin-top: 16px; font-weight: bold; }}
  button:disabled {{ background: #333; color: #777; }}
  #msg {{ text-align: center; margin-top: 16px; font-size: 1rem; min-height: 1.2em; }}
</style>
</head>
<body>
  <h1>Shape the Design</h1>
  <p class="sub">Pick what you'd want to see more of -- your input gets folded into the final design shown at the presentation.</p>
  <form id="f">
    <fieldset>
      <legend>What's missing?</legend>
      {layer_buttons}
    </fieldset>
    <fieldset>
      <legend>Pick a park that inspires you (optional)</legend>
      {site_buttons}
    </fieldset>
    <fieldset>
      <legend>Anything else? (optional)</legend>
      <textarea name="text" placeholder="e.g. it should feel cooler, more like a plaza..."></textarea>
    </fieldset>
    <button type="submit" id="btn">Submit</button>
  </form>
  <div id="msg"></div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const btn = document.getElementById('btn');
  const msg = document.getElementById('msg');
  btn.disabled = true;
  const form = new FormData(e.target);
  const layers = form.getAll('layers');
  const site = form.get('site') || null;
  const text = form.get('text') || '';
  try {{
    const res = await fetch('/submit', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{layers, site, text}})
    }});
    const data = await res.json();
    if (res.ok) {{
      msg.textContent = "Thanks! Your input is in.";
      e.target.style.display = 'none';
    }} else {{
      msg.textContent = data.detail || "Submissions are closed.";
      btn.disabled = false;
    }}
  }} catch (err) {{
    msg.textContent = "Couldn't reach the server -- try again.";
    btn.disabled = false;
  }}
}});
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return _page_html()


@app.post("/submit")
async def submit(payload: Submission):
    if EVENT_DEADLINE and datetime.now() >= EVENT_DEADLINE:
        return JSONResponse(status_code=403, content={"detail": "Submissions are closed -- thanks for participating!"})

    os.makedirs(EVENT_DIR, exist_ok=True)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "layers": payload.layers,
        "site": payload.site,
        "text": payload.text.strip()[:500],  # cap free text -- public form, keep it bounded
    }
    with open(SUBMISSIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {"status": "ok"}


@app.get("/status")
async def status():
    count = 0
    if os.path.exists(SUBMISSIONS_PATH):
        with open(SUBMISSIONS_PATH, encoding="utf-8") as f:
            count = sum(1 for _ in f)
    closed = bool(EVENT_DEADLINE and datetime.now() >= EVENT_DEADLINE)
    return {"submissions": count, "closed": closed,
            "deadline": EVENT_DEADLINE.isoformat() if EVENT_DEADLINE else None}


def main():
    global EVENT_DEADLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline", help='ISO datetime, e.g. "2026-08-20T18:30:00" -- submissions rejected after this')
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    if args.deadline:
        EVENT_DEADLINE = datetime.fromisoformat(args.deadline)
        print(f"Submissions close at {EVENT_DEADLINE.isoformat()}")
    else:
        print("No --deadline set -- submissions stay open until this process is stopped.")

    os.makedirs(EVENT_DIR, exist_ok=True)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
