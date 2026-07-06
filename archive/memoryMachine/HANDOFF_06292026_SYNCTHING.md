# Memory Machine — Claude Handoff (Syncthing Setup, School PC)
**Date:** 2026-06-29
**Status:** Syncthing installed and confirmed running on home PC. Needs verification/setup on this (school) PC.

---

## Context

User wants to sync the `D:\MemoryMachine\archive\memoryMachine` notes folder (the canonical MemoryMachine project notes repo — see [[memorymachine_notes_location]]) between their home PC and this school PC using Syncthing.

Concern raised: the school network may block Syncthing's sync traffic. This is a separate issue from whether the Syncthing GUI/app runs locally — local GUI working does NOT mean cross-device sync works if the network filters the relevant ports/protocols.

## What Was Verified on the Home PC

- `winget install Syncthing.Syncthing` completed successfully.
- Two `syncthing` processes were running.
- Port 8384 (web GUI) was confirmed LISTENING via `Get-NetTCPConnection`, plus an ESTABLISHED loopback connection — GUI is reachable at `http://localhost:8384` once given a moment to start after install (an initial "connection refused" was just a timing issue right after install, not a real block).
- Home PC has NOT yet been paired with the school PC (no remote device added yet, no shared folder configured yet).

## What This Session Should Check/Do

1. **Confirm Syncthing is installed and running here.**
   ```powershell
   Get-Process syncthing -ErrorAction SilentlyContinue
   Get-NetTCPConnection -LocalPort 8384 -ErrorAction SilentlyContinue
   ```
   If not installed: `winget install Syncthing.Syncthing`. Give it 10-20 seconds after install before hitting the GUI.

2. **Open the GUI** at `http://localhost:8384` and get this PC's Device ID (Actions → Show ID). Report it back to the user so they can add it as a remote device on the home PC (and vice versa — get the home PC's Device ID from the user to add here).

3. **Test connectivity to the home PC.** After both sides add each other as remote devices, check device status in the GUI:
   - `Connected (Direct)` — direct LAN/WAN connection works, school network is not blocking it.
   - `Connected (Relay)` — direct connection blocked, but public relay traffic (looks like HTTPS, usually gets through firewalls) is working. This is fine for syncing, just slower.
   - `Disconnected` indefinitely — likely blocked. School firewalls commonly block Syncthing's direct sync port (22000 TCP/UDP) and sometimes also block/throttle relay traffic via deep packet inspection.

4. **If stuck on `Disconnected`:**
   - Check Actions → Settings → Connections: confirm "Enable Relaying" and global discovery are ON (default).
   - Try toggling NAT traversal / check if outbound 443 is allowed generally on this network (most campus networks allow it for normal HTTPS browsing, which is what Syncthing relay traffic resembles).
   - If relays are also blocked, the fallback plan discussed with the user is to tunnel via **Tailscale** (its own protocol often gets through when raw Syncthing doesn't) and point Syncthing's sync at the Tailscale IP instead of relying on public discovery/relay.

5. **Once connected:** share the `memoryMachine` notes folder (or the whole `D:\MemoryMachine` tree, user's call) from one side and accept on the other. Set sync direction (two-way is fine unless one side should be read-only).

## Report Back

After running through the above, summarize for the user: was this PC able to install/run Syncthing, what's the connection status with home (Direct/Relay/Disconnected), and whether the school network appears to be blocking sync traffic specifically (vs. just GUI timing issues like the first home-PC attempt).
