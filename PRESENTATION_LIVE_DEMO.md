# Sharing a live-link demo of the app

The app runs locally day-to-day and the deck's "05 // THE APP" slide embeds it
via `http://127.0.0.1:5174/` — that only resolves on this machine. For a
presentation where you need to send a link and have the app actually work for
whoever opens it, use a temporary Cloudflare Tunnel. Nothing to configure each
time beyond the steps below; the deck reads the app's public URL from a query
parameter, so there's no file to edit and nothing to remember to revert.

## Steps

1. Start the app as normal: run `start_metabolizer.bat` (backend on :8000,
   frontend on :5174). Wait for both to come up.

2. Start the tunnel:
   ```
   cloudflared tunnel --url http://127.0.0.1:5174
   ```
   It prints a random public URL after a few seconds, e.g.:
   ```
   https://ireland-castle-recognized-herb.trycloudflare.com
   ```
   This is a free "quick tunnel" — no account or config needed. It forwards
   public HTTPS traffic to the local Vite dev server, which already proxies
   `/api` and everything else to the local backend (`frontend/vite.config.js`),
   so this one URL exposes the whole working app, not just static files.

3. Open (or share) the deck with that URL as the `app` query parameter:
   ```
   final_deck.html?app=https://ireland-castle-recognized-herb.trycloudflare.com/
   ```
   Slide "05 // THE APP" will load the live app through that URL instead of
   `127.0.0.1:5174`. Opening the deck without `?app=` still falls back to the
   normal local behavior, unchanged.

4. When you're done, close the `cloudflared` window/process. The tunnel dies
   immediately — nothing stays exposed afterward.

## Things to plan around during the live demo

These are real, observed behaviors of this app, not hypothetical:

- **GENERATE takes 14-34 seconds per click** (the first call after a backend
  restart can be slower). Set expectations before clicking it live.
- **The backend is single-worker and blocks on every route while one
  GENERATE call is in flight.** If two people have the link open at once and
  one clicks GENERATE, the other's page will hang too until it finishes.
  Don't share the link to a room and let multiple people click around
  simultaneously — drive it yourself.
- **The backend occasionally becomes unresponsive** (a known Windows-specific
  issue, not caused by the tunnel) — process stays alive, port stays open,
  but nothing gets served. If a request never returns, close and re-run
  `start_metabolizer.bat`, then restart the tunnel (it'll print a new URL —
  update the `?app=` link if you're mid-presentation).
- **There is no authentication on any route.** Only share the tunnel URL with
  your actual audience, and close the tunnel right after the presentation.
