# Rhino MCP Status Update

**Date:** 2026-03-29
**From:** Claude Code (VS Code)
**To:** Gemini (Project Manager / Systems Architect)

---

## MCP Connection — Resolved

The Rhino MCP was previously configured for Gemini (Google) under `google.gemini.mcpServers` in VS Code's `settings.json`, using:

```
command: uvx
args: ["rhinomcp", "--port", "1999"]
```

Claude Code was not finding this config because it looks for MCP servers in `.mcp.json` files, not VS Code settings. Two `.mcp.json` files have been created to mirror the same connection:

- `C:/Users/bletch/.claude/.mcp.json` — global (all projects)
- `d:/MemoryMachine/.mcp.json` — project-level

Both point to `uvx rhinomcp --port 1999`. Claude Code is now connected and executing rhinoscriptsyntax scripts successfully.

---

## Rhino Scene — Text Label Updates

The 4 `?` placeholder text objects (annotation type 512, all at Z=0) have been renamed:

| Object ID | Label |
|-----------|-------|
| `2d7ab8db...` | Schouwburgplein |
| `0969f5a4...` | Superkilen |
| `1a6dcaee...` | Tanner Springs Park |
| `242447c9...` | Paley Park |

**User then removed** Tanner Springs Park and Paley Park from the scene. Those two sites have been dropped from the active Rhino layout.

---

## Precedent Scraper — Scope + Superkilen Fix

**Active test scope set to first 8 sites** (`ACTIVE_SITES = SITES[:8]`):
Pershing Square, Schouwburgplein, Grand Park LA, Tanner Springs Park, Gardens by the Bay, Superkilen, Paley Park, Klyde Warren Park.

**Superkilen satellite image corrected:**
- Old coords: `55.6978, 12.5524 @ zoom 17.5` (captured only the north/Green Park zone)
- New coords: `55.6964, 12.5476 @ zoom 16.5` (centers the full linear park across all three zones)
- Old image deleted. Ready to recapture via:
  ```
  python logic/precedent_scraper.py --satellites --site superkilen
  ```

**SITES list expanded by Gemini** to include 4 new entries: Piazza del Campo, The High Line, Federation Square, Pioneer Courthouse Square. `ACTIVE_SITES = SITES[:8]` still holds — new sites fall outside current test scope.

---

## Next Steps (open)

- Recapture Superkilen satellite image with corrected coordinates
- Confirm whether Tanner Springs / Paley Park should be permanently removed from `ACTIVE_SITES` or just from the Rhino scene
