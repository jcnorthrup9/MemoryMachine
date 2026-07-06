# UI/UX Improvement Proposal: Boxy Player Interface v1.0 (Audit Findings)

**Date Generated:** 2026-06-04
**Source Audit Run Context:** System Directive Execution simulation run on D:\\boxy_player\\obsidian\\boxy_player\
**Goal:** To stabilize UI rendering, improve responsiveness under failure conditions (no MPD connection), and propose a robust structure for development.

## 🔴 I. Audit Findings & Bottlenecks Identified

The primary instability source across both TUI and GUI paradigms is the **tight coupling between the UI Rendering Cycle and the Live Streaming Connection Status.** When the stream momentarily stalls or disconnects, components often attempt to render based on stale data (e.g., displaying an incorrect "current time" or assuming a track has successfully loaded metadata), leading to layout instability and unhandled exceptions.

1.  **State Synchronization Lag:** The critical bottleneck is synchronization during connection transitions. A simple 'is connected' boolean check is insufficient.
2.  **Event Hook Instability:** Primary control buttons (Play, Pause, Skip) must not execute any visible change logic if the underlying *capability* to perform the action is absent or pending verification.
3.  **Layout Reflow Errors:** Observed when a component fails silently while trying to calculate layout geometry based on expected media metadata that hasn't arrived yet.

## 🟢 II. Optimization Proposals (Implementation Roadmap)

### A. Architectural Fixes: The State Buffer Pattern (HIGH PRIORITY)
This is the most crucial structural change, applicable to both TUI and GUI layers.

*   **Proposal:** Introduce a mandatory **`PlaybackStateBuffer`** singleton object managed by the core logic layer.
*   **Functionality:** This buffer caches all critical data points (`current_track_metadata`, `playback_progress_seconds`, `connection_status: {active, degraded, offline}`) on every successful state update from the backend API.
*   **UI Consumption Rule:** All UI elements (TUI Widgets/GUI Components) must **read their display values exclusively from this buffer**, not directly from transient function calls.

### B. Component-Level Fixes & Stability Hooks
These proposals address specific failure points:

1.  **Asynchronous Connection Trapping:** Wrap all control hook emitters (`on_play()`, `on_skip_next()`) with a preliminary check: `if state_buffer.is_connection_valid(): emit_event(action)` $\rightarrow$ This prevents the UI from calling action handlers when nothing is playing/connected.
2.  **Time Playhead Control:** The visual progress bar must never calculate *elapsed time* if the `ConnectionStatus` is 'degraded' or 'offline'. Instead, it should fall back to a gracefully animated placeholder that communicates latency visually (e.g., a pulsing indicator).

### C. UI/UX Enhancements
These improve polish and usability for sharing:

1.  **Default Mode Aesthetic:** For shared demos, enforce a high-contrast, *Dark Mode* theme by default. This feels professional, reduces eye strain, and makes artwork pop, fulfilling the 'professional look' requirement.
2.  **Action Clarity:** When an action fails (e.g., "Cannot skip track: No playlist loaded"), display this message **non-intrusively** in a dedicated status line that fades out after 4 seconds, rather than relying on hard error popups that interrupt flow.

---
*End of Report.*