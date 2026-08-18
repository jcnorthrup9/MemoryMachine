---
# Design tokens -- machine-readable source of truth for styling.
# Originally extracted from Google Stitch mockup exports (2026-07-06, dark
# brutalist brief). Re-extracted 2026-07-30 from two NEW Stitch exports
# ("Archive Index" / data-archive screen and "Reconstruction Workspace" /
# Blender-core screen) requesting a cleaner, white-background, less-cluttered
# look. This is the ONLY place tokens should be edited; tailwind.config.js/
# theme CSS should read from here, not the other way around.
colors:
  background: "#ffffff"
  surface: "#ffffff"
  surface-dim: "#f3f4f6"
  surface-bright: "#ffffff"
  surface-container-lowest: "#ffffff"
  surface-container-low: "#f9fafb"
  surface-container: "#f3f4f6"
  surface-container-high: "#f9fafb"
  surface-container-highest: "#e5e7eb"
  surface-variant: "#f3f4f6"
  on-surface: "#1a1c1c"
  on-surface-variant: "#71717a"
  on-background: "#1a1c1c"
  primary: "#1a1c1c"
  on-primary: "#ffffff"
  primary-container: "#f3f4f6"
  on-primary-container: "#1a1c1c"
  secondary: "#454747"
  on-secondary: "#ffffff"
  secondary-container: "#e2e2e2"
  on-secondary-container: "#454747"
  border: "#e5e7eb"
  outline: "#71717a"
  outline-variant: "#d1d5db"
  accent: "#3E6D8E"          # active-state / terminal-variable color, use sparingly -- deepened from the CIRCULATION pastel (#AFC6D9) in drawing_styles.py's diagram palette for cross-artifact consistency
  success: "#00CC52"
  warning: "#d97706"
  error: "#dc2626"
  on-error: "#ffffff"
  error-container: "#fee2e2"
  on-error-container: "#410002"
  inverse-surface: "#313030"
  inverse-on-surface: "#f3f4f6"

borderRadius:
  DEFAULT: "2px"
  lg: "4px"
  xl: "6px"
  full: "9999px"    # circular elements only (avatars, status dots) -- never cards/panels

spacing:
  edge: "1px"
  container: "32px"
  gap: "24px"
  base: "12px"
  card_gap: "24px"

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

Architectural, high-contrast, light-mode token system. Clean white
background, monospaced data, quiet 1px borders, small consistent corner
radii, and shadow used sparingly as an interaction cue (hover/elevation),
not decoration.

## Source and resolved inconsistencies

Originally extracted from 4 Google Stitch HTML exports (2026-07-06:
Parameters & Configuration, System Diagnostics, Archive Index,
Reconstruction Workspace) into a dark, zero-radius, brutalist system.

Re-extracted 2026-07-30 from 2 NEW Stitch exports of the same two screens
(Archive Index, Reconstruction Workspace) requesting a cleaner, white,
less-cluttered look. Only two of the original four screens were
regenerated -- Parameters & Configuration and System Diagnostics still use
tokens extrapolated from these two, not their own dedicated mockup.

The two new exports disagreed on two points: accent green (`#00CC52` in
Archive Index vs `#10b981` in Reconstruction Workspace) and border-radius
scale (`0.125/0.25/0.375rem` vs `4px/6px`). **Resolved by taking Archive
Index as the canonical source for the full palette** -- it defines every
token name this app's tailwind config already uses (a complete Material-
style set), while Reconstruction Workspace only exercises a subset and
otherwise agrees with it (same white background/surface, same
`#e5e7eb` border, same light gray `on-surface-variant` family, closely
overlapping radius scale). Not picked arbitrarily: mixing tokens from two
independently-generated exports risks incoherent contrast pairs, so one
file wins wholesale rather than cherry-picking per token.

## Component patterns

These aren't raw tokens but recurring structural patterns worth keeping
consistent across the app -- read this before inventing a new variant.

- **Panel**: `bg-surface border border-border rounded-lg p-6`, no shadow at
  rest; `hover:shadow-lg` only on interactive/clickable panels (e.g. archive
  cards), never on static layout chrome (sidebars, toolbars).
- **Stat tile**: uppercase `mono-label` caption (on-surface-variant) + large
  value in `mono-label`/`mono-sm` (accent or primary) + a 1px-tall progress
  bar (`bg-surface-container-highest` track, `bg-accent` fill, `rounded-
  full`).
- **Toggle**: NOT a pill switch -- a small bordered box (`border-accent
  bg-accent` when on, small inner square offset to match state; `border-
  border` transparent when off), `rounded` corners.
- **Sidebar nav item**: 4px left/right border in accent + `bg-surface-
  container-low` when active; transparent border + `on-surface-variant`
  when inactive. Icon + uppercase `mono-sm` label, never both icon-only.
- **Primary button**: solid `bg-accent`, `text-background` (or `bg-primary
  text-on-primary` for a neutral high-emphasis action), bold uppercase
  `mono-sm`, wide tracking, `rounded`.
- **Secondary/outline button**: `border-accent text-accent`, transparent
  background, `rounded`.
- **Select/input**: `bg-white border border-border rounded`, `focus:border-
  accent`, never a focus ring/shadow.
- **Log/terminal panel**: stays dark regardless of app theme
  (`surface-container-lowest`-equivalent near-black, e.g. `#141313`),
  `mono-sm` text, dimmed timestamp prefix + full-opacity status text,
  `success`/`warning`/`error` colors for status words only, never whole
  lines -- this is the one deliberate dark-on-light inversion, reading as a
  console/terminal embedded in the page.

## Accent usage rule

`accent` (#FF7F50) is reserved for **active-state and live-data signaling**
only -- the current nav item, an enabled toggle, a live/streaming indicator,
a value currently changing. It is not a general highlight color; overusing
it flattens its meaning.
