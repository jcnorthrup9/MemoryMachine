---
# Design tokens -- machine-readable source of truth for styling.
# Extracted from Google Stitch mockup exports (2026-07-06) and reconciled
# where the four generated screens disagreed with each other or with the
# brief (see "Resolved inconsistencies" below). This is the ONLY place
# tokens should be edited; tailwind.config.js/theme CSS should read from
# here, not the other way around.
colors:
  background: "#0A0A0A"
  surface: "#171717"
  surface-dim: "#141313"
  surface-bright: "#3a3939"
  surface-container-lowest: "#0e0e0e"
  surface-container-low: "#1c1b1b"
  surface-container: "#201f1f"
  surface-container-high: "#2a2a2a"
  surface-container-highest: "#353434"
  surface-variant: "#353434"
  on-surface: "#e5e2e1"
  on-surface-variant: "#c4c7c8"
  on-background: "#e5e2e1"
  primary: "#ffffff"
  on-primary: "#2f3131"
  primary-container: "#e2e2e2"
  on-primary-container: "#636565"
  secondary: "#c7c6c6"
  on-secondary: "#2f3131"
  secondary-container: "#484949"
  on-secondary-container: "#b8b8b8"
  border: "#262626"
  outline: "#8e9192"
  outline-variant: "#444748"
  accent: "#00FF66"          # active-state / terminal-variable color, use sparingly
  success: "#00FF66"
  warning: "#FACC15"
  error: "#EF4444"
  on-error: "#690005"
  error-container: "#93000a"
  on-error-container: "#ffdad6"
  inverse-surface: "#e5e2e1"
  inverse-on-surface: "#313030"

borderRadius:
  DEFAULT: "0px"
  lg: "0px"
  xl: "0px"
  full: "9999px"    # circular elements only (avatars, status dots) -- never cards/panels

spacing:
  edge: "1px"
  container: "24px"
  gap: "16px"
  base: "8px"
  card_gap: "16px"

fontFamily:
  mono-label: ["JetBrains Mono"]
  mono-sm: ["JetBrains Mono"]
  headline-md: ["Inter"]
  headline-lg: ["Inter"]
  body-md: ["Inter"]

fontSize:
  mono-label: ["10px", { lineHeight: "12px", letterSpacing: "0.05em", fontWeight: "500" }]
  mono-sm: ["12px", { lineHeight: "16px", letterSpacing: "0.02em", fontWeight: "400" }]
  headline-md: ["18px", { lineHeight: "24px", fontWeight: "600" }]
  headline-lg: ["24px", { lineHeight: "32px", letterSpacing: "-0.02em", fontWeight: "600" }]
  body-md: ["14px", { lineHeight: "20px", fontWeight: "400" }]
---

# Memory Machine -- Design System

Architectural, high-contrast, brutalist token system. Dark-only. Monospaced
data, sharp geometry, flat panels bound by 1px lines instead of shadows or
rounded cards.

## Source and resolved inconsistencies

Extracted from 4 Google Stitch HTML exports (Parameters & Configuration,
System Diagnostics, Archive Index, Reconstruction Workspace), all sharing
the same color/font/spacing tokens -- but their `borderRadius` values
actually disagreed with each other: "Parameters" used `0px` (matching the
brief's explicit "sharp 2px border radii" -- close enough to flat), while
"Archive Index" and "Reconstruction Workspace" had accidentally-generated
rounded values (`0.25rem`/`0.5rem`/`0.75rem`). **Resolved to `0px`
everywhere** as the canonical value, per the brief's stated intent, not
picked arbitrarily -- every panel/card/button in the real app should read
as a flat, bordered block, never a rounded one.

## Component patterns

These aren't raw tokens but recurring structural patterns worth keeping
consistent across the app -- read this before inventing a new variant.

- **Panel**: `bg-surface border border-border p-6`, no shadow, no radius.
- **Stat tile**: uppercase `mono-label` caption (on-surface-variant) + large
  value in `mono-label`/`mono-sm` (accent or primary) + a 1px-tall progress
  bar (`bg-border` track, `bg-accent` fill).
- **Toggle**: NOT a pill switch -- a small bordered box (`border-accent
  bg-accent` when on, small inner square offset to match state; `border-
  border` transparent when off).
- **Sidebar nav item**: 2px left border in accent + `bg-surface-container-
  high` when active; transparent border + `on-surface-variant` when
  inactive. Icon + uppercase `mono-sm` label, never both icon-only.
- **Primary button**: solid `bg-accent`, `text-background`, bold uppercase
  `mono-sm`, wide tracking.
- **Secondary/outline button**: `border-accent text-accent`, transparent
  background.
- **Select/input**: `bg-background border border-border`, `focus:border-
  accent`, never a focus ring/shadow.
- **Log/terminal panel**: near-black background (`#050505` or
  `surface-container-lowest`), `mono-sm` text, dimmed timestamp prefix +
  full-opacity status text, `success`/`warning`/`error` colors for status
  words only, never whole lines.

## Accent usage rule

`accent` (#00FF66) is reserved for **active-state and live-data signaling**
only -- the current nav item, an enabled toggle, a live/streaming indicator,
a value currently changing. It is not a general highlight color; overusing
it flattens its meaning.
