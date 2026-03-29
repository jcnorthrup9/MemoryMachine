"""
scrapbook_compiler.py
---------------------
Generates html/precedent_scrapbook.html — an 'Archival Dossier' style
HTML document cataloguing the 10 Memory Machine precedent outdoor spaces.

Run:
    .venv/Scripts/python.exe logic/scrapbook_compiler.py
"""

import os, sys, re, textwrap, webbrowser

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")
IMG_DIR   = os.path.join(BASE_DIR, "assets", "precedents")
HTML_DIR  = os.path.join(BASE_DIR, "html")
OUT_FILE  = os.path.join(HTML_DIR, "precedent_scrapbook.html")

os.makedirs(HTML_DIR, exist_ok=True)

# Pull SITES list from batch_scraper without running its main()
sys.path.insert(0, os.path.join(BASE_DIR, "logic"))
from batch_scraper import SITES

# Exclude Pershing Square from the precedent scrapbook (it's the target site)
PRECEDENT_SITES = [s for s in SITES if s["id"] != "pershing_square"]

# ── text extraction helpers ───────────────────────────────────────────────────
def extract_wikipedia_blurb(text, chars=380):
    """Return the first ~380 chars after the [WIKIPEDIA] marker."""
    m = re.search(r'\[WIKIPEDIA\]\s*\n+(.*)', text, re.DOTALL)
    if not m:
        return None
    blurb = m.group(1).strip()
    # Stop at any section marker
    blurb = re.split(r'\n\[', blurb)[0].strip()
    if len(blurb) > chars:
        blurb = blurb[:chars].rsplit(' ', 1)[0] + '…'
    return blurb


def extract_ddg_sentences(text, n=5):
    """Pull n short, distinct review sentences from the DDG section."""
    m = re.search(r'\[DUCKDUCKGO SEARCH RESULTS\](.*)', text, re.DOTALL)
    if not m:
        return []

    raw = m.group(1)
    # Drop source lines and query headers
    raw = re.sub(r'^\s*Source:.*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^\s*Search:.*$', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'^\s*\[.*?\]\s*$', '', raw, flags=re.MULTILINE)

    # Split into candidate sentences
    candidates = []
    for line in raw.splitlines():
        line = line.strip()
        if len(line) < 30 or len(line) > 220:
            continue
        # Split on '.', '!', '?' but keep the punctuation
        for sent in re.split(r'(?<=[.!?])\s+', line):
            sent = sent.strip()
            if 25 < len(sent) < 200:
                candidates.append(sent)

    # Deduplicate and prefer shorter, more distinct sentences
    seen_starts = set()
    chosen = []
    for s in candidates:
        key = s[:40].lower()
        if key not in seen_starts:
            seen_starts.add(key)
            chosen.append(s)
        if len(chosen) >= n:
            break
    return chosen


def load_site_text(reviews_file):
    path = os.path.join(DATA_DIR, reviews_file)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def find_image(site_id):
    """
    Return a relative path (from html/) to the satellite image, or None.
    Checks both {id}_satellite.jpg and common variant names.
    """
    candidates = [
        f"{site_id}_satellite.jpg",
        # klyde_warren_park -> klyde_warren_satellite.jpg
        f"{site_id.replace('_park', '')}_satellite.jpg",
    ]
    for name in candidates:
        full = os.path.join(IMG_DIR, name)
        if os.path.exists(full):
            # relative path from html/ to assets/precedents/
            return f"../assets/precedents/{name}"
    return None


# ── polaroid rotations (cycles through a fixed set for visual rhythm) ─────────
ROTATIONS = [-2.1, 1.4, -0.8, 2.3, -1.6, 0.9, -2.5, 1.1, -1.3, 2.0]

# ── HTML template ─────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Special+Elite&family=Courier+Prime:ital,wght@0,400;0,700;1,400&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --paper:   #f4f0e6;
  --paper2:  #ede8d8;
  --ink:     #2a2318;
  --ink2:    #4a3f30;
  --faint:   #9a8f80;
  --red:     #8b1a1a;
  --stamp:   rgba(139,26,26,0.18);
  --rule:    rgba(42,35,24,0.12);
}

html { scroll-behavior: smooth; }

body {
  background: #cbc4b4 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='4' height='4'%3E%3Crect width='4' height='4' fill='%23bbb5a4'/%3E%3Ccircle cx='1' cy='1' r='0.7' fill='%23c4bdb0' opacity='0.5'/%3E%3C/svg%3E");
  font-family: 'Courier Prime', 'Courier New', monospace;
  color: var(--ink);
  padding: 2rem 1rem 4rem;
}

/* ── Cover header ── */
.cover {
  max-width: 900px;
  margin: 0 auto 3rem;
  background: var(--paper);
  border: 2px solid var(--ink);
  padding: 2.5rem 3rem;
  position: relative;
  box-shadow: 4px 4px 0 rgba(0,0,0,0.25);
}
.cover::before {
  content: '';
  position: absolute; inset: 6px;
  border: 1px dashed var(--faint);
  pointer-events: none;
}
.cover-label {
  font-size: 0.65rem; letter-spacing: 0.35em; text-transform: uppercase;
  color: var(--faint); margin-bottom: 0.4rem;
}
.cover-title {
  font-family: 'Special Elite', cursive;
  font-size: 2.4rem; line-height: 1.1;
  letter-spacing: 0.04em; color: var(--ink);
}
.cover-subtitle {
  margin-top: 0.6rem; font-size: 0.85rem; color: var(--ink2);
  border-top: 1px solid var(--rule); padding-top: 0.5rem; margin-top: 0.8rem;
}
.cover-meta {
  display: flex; gap: 2rem; flex-wrap: wrap;
  margin-top: 1rem; font-size: 0.72rem; color: var(--faint);
  letter-spacing: 0.1em;
}
.stamp-classified {
  position: absolute; top: 1.8rem; right: 2rem;
  font-family: 'Special Elite', cursive;
  font-size: 1.1rem; color: var(--red);
  border: 2px solid var(--red); padding: 0.2rem 0.6rem;
  transform: rotate(-4deg); opacity: 0.6;
  letter-spacing: 0.12em;
}

/* ── Dossier card ── */
.dossier-grid {
  max-width: 900px; margin: 0 auto;
  display: grid; grid-template-columns: 1fr; gap: 3rem;
}

.card {
  background: var(--paper);
  border: 1.5px solid var(--ink2);
  padding: 0;
  box-shadow: 3px 5px 0 rgba(0,0,0,0.20);
  position: relative;
  page-break-inside: avoid;
}
.card::after {
  content: '';
  position: absolute; inset: 5px;
  border: 1px dotted var(--rule);
  pointer-events: none;
}

.card-header {
  background: var(--paper2);
  border-bottom: 1.5px solid var(--ink2);
  padding: 1rem 1.4rem 0.8rem;
  display: flex; align-items: baseline; gap: 1rem;
}
.card-number {
  font-size: 0.65rem; color: var(--faint);
  letter-spacing: 0.25em; white-space: nowrap;
}
.card-name {
  font-family: 'Special Elite', cursive;
  font-size: 1.45rem; color: var(--ink);
  line-height: 1.1;
}
.card-location {
  font-size: 0.72rem; color: var(--faint);
  letter-spacing: 0.08em; margin-left: auto; white-space: nowrap;
}

.card-body {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 0;
}

/* ── Polaroid image ── */
.polaroid-wrap {
  padding: 1.2rem 0.8rem 0.8rem 1.2rem;
  display: flex; flex-direction: column; align-items: center;
  gap: 0.5rem;
}
.polaroid {
  background: #fff;
  padding: 6px 6px 28px;
  box-shadow: 2px 3px 8px rgba(0,0,0,0.28);
  width: 160px;
}
.polaroid img {
  display: block; width: 148px; height: 110px;
  object-fit: cover; filter: sepia(0.18) contrast(1.05);
}
.polaroid-missing {
  width: 148px; height: 110px;
  background: #ccc8bc;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.6rem; color: #888; text-align: center;
  letter-spacing: 0.06em; line-height: 1.4;
}
.polaroid-caption {
  font-size: 0.6rem; color: var(--faint); text-align: center;
  letter-spacing: 0.05em; margin-top: 2px;
  font-style: italic;
}

.card-tag {
  display: inline-block;
  font-size: 0.6rem; letter-spacing: 0.15em; text-transform: uppercase;
  background: var(--ink); color: var(--paper);
  padding: 0.15rem 0.45rem; margin-top: 0.4rem;
}

/* ── Text columns ── */
.card-text {
  padding: 1.2rem 1.4rem 1.2rem 0.8rem;
  border-left: 1.5px solid var(--rule);
}

.section-label {
  font-size: 0.6rem; letter-spacing: 0.3em; text-transform: uppercase;
  color: var(--faint); border-bottom: 1px solid var(--rule);
  padding-bottom: 0.2rem; margin-bottom: 0.5rem;
}

.wiki-blurb {
  font-size: 0.8rem; line-height: 1.65;
  color: var(--ink2); margin-bottom: 1.1rem;
}
.wiki-blurb em { font-style: italic; }

.reviews-list {
  list-style: none; padding: 0;
}
.reviews-list li {
  font-size: 0.76rem; line-height: 1.55;
  color: var(--ink); padding: 0.3rem 0 0.3rem 1.1rem;
  border-bottom: 1px dotted var(--rule);
  position: relative;
}
.reviews-list li::before {
  content: '›'; position: absolute; left: 0;
  color: var(--faint);
}
.reviews-list li:last-child { border-bottom: none; }

/* ── No-data fallback ── */
.no-data {
  font-size: 0.75rem; color: var(--faint); font-style: italic;
  padding: 0.5rem 0;
}

/* ── Footer ── */
.footer {
  max-width: 900px; margin: 3rem auto 0;
  text-align: center; font-size: 0.65rem;
  color: var(--faint); letter-spacing: 0.1em;
  border-top: 1px solid var(--rule); padding-top: 1rem;
}
"""

def card_html(site, index):
    txt       = load_site_text(site["reviews_file"])
    wiki      = extract_wikipedia_blurb(txt) or "<em>No archival record found.</em>"
    sentences = extract_ddg_sentences(txt)
    img_path  = find_image(site["id"])
    rot       = ROTATIONS[index % len(ROTATIONS)]
    num       = f"CASE-{index+1:02d} / REF-{site['id'].upper()[:12]}"

    if img_path:
        img_tag = f'<img src="{img_path}" alt="Satellite view of {site["name"]}" loading="lazy">'
    else:
        img_tag = '<div class="polaroid-missing">[ VISUAL DATA<br>MISSING ]</div>'

    sentences_html = ""
    if sentences:
        items = "".join(f"<li>{s}</li>" for s in sentences)
        sentences_html = f"""
        <div class="section-label">Field Observations / Key Reviews</div>
        <ul class="reviews-list">{items}</ul>"""
    else:
        sentences_html = '<p class="no-data">— field observations not on record —</p>'

    return f"""
  <article class="card" id="{site['id']}">
    <div class="card-header">
      <span class="card-number">{num}</span>
      <span class="card-name">{site['name']}</span>
      <span class="card-location">{site.get('search_alias','').split(' ')[-1]}</span>
    </div>
    <div class="card-body">
      <div class="polaroid-wrap">
        <div class="polaroid" style="transform: rotate({rot}deg)">
          {img_tag}
        </div>
        <div class="polaroid-caption">aerial / satellite view</div>
        <span class="card-tag">{site['id'].replace('_',' ')}</span>
      </div>
      <div class="card-text">
        <div class="section-label">Historical Description</div>
        <p class="wiki-blurb">{wiki}</p>
        {sentences_html}
      </div>
    </div>
  </article>"""


def build_toc():
    items = []
    for i, s in enumerate(PRECEDENT_SITES):
        num = f"{i+1:02d}"
        items.append(
            f'<li><a href="#{s["id"]}">'
            f'<span class="toc-num">{num}.</span> {s["name"]}</a></li>'
        )
    return "<ul class='toc-list'>" + "".join(items) + "</ul>"


def build_html():
    pass  # datetime imported inline below
    import datetime as _dt
    date_str = _dt.datetime.now(_dt.timezone.utc).strftime("%d %b %Y")
    cards    = "\n".join(card_html(s, i) for i, s in enumerate(PRECEDENT_SITES))

    toc_css = """
.toc { margin-top: 1rem; }
.toc-list { list-style: none; display: flex; flex-wrap: wrap; gap: 0.3rem 1.5rem; padding: 0; }
.toc-list li a {
  font-size: 0.72rem; color: var(--ink2); text-decoration: none;
  letter-spacing: 0.04em;
}
.toc-list li a:hover { text-decoration: underline; color: var(--red); }
.toc-num { color: var(--faint); margin-right: 0.2rem; }
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Memory Machine — Precedent Scrapbook</title>
  <style>{CSS}{toc_css}</style>
</head>
<body>

  <div class="cover">
    <div class="stamp-classified">DOSSIER</div>
    <div class="cover-label">Memory Machine · Pershing Square DTLA · Precedent Research</div>
    <div class="cover-title">Outdoor Public Space<br>Precedent Scrapbook</div>
    <div class="cover-subtitle">
      Ten curated case studies selected for spatial, material, acoustic, and programmatic
      relevance to the redesign of Pershing Square, Downtown Los Angeles.
    </div>
    <div class="cover-meta">
      <span>COMPILED: {date_str}</span>
      <span>CORPUS: 10 SITES</span>
      <span>SOURCE: Wikipedia · DuckDuckGo · Gemini Synthesis</span>
      <span>PROJECT: MEMORY MACHINE v2</span>
    </div>
    <div class="toc">{build_toc()}</div>
  </div>

  <div class="dossier-grid">
    {cards}
  </div>

  <div class="footer">
    MEMORY MACHINE — AUTOMATED PRECEDENT DOSSIER — {date_str} — FOR DESIGN RESEARCH PURPOSES ONLY
  </div>

</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[SCRAPBOOK] Building precedent dossier...")
    html = build_html()
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(OUT_FILE) // 1024
    print(f"[OK] Written {size_kb} KB to {OUT_FILE}")
    print("[OK] Opening in browser...")
    webbrowser.open(f"file:///{OUT_FILE.replace(os.sep, '/')}")
    print("[DONE] Scrapbook complete.")
