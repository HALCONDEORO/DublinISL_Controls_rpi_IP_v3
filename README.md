# DublinISL Controls — PTZ Camera Control System

> Version 3.0 — Tested on Raspberry Pi OS

Control system for two IP PTZ cameras in the **Kingdom Hall of Jehovah's Witnesses for the deaf in Dublin** (Dublin ISL congregation — Irish Sign Language).

Because the congregation is deaf, **audio and microphones play no role whatsoever.** Everything that matters is what the cameras show. The system is built around giving the operator precise, fast visual control: clicking a seat instantly moves the camera to the preset for that speaker, and the ATEM switcher cuts to the correct camera automatically.

The application runs on a Raspberry Pi 4. It controls two PTZ cameras via VISCA over TCP/IP and integrates with a BlackMagic ATEM video switcher for automated camera switching during live sessions.

---

## Table of Contents

1. [Features](#features)
2. [Hardware Requirements](#hardware-requirements)
3. [Software Requirements](#software-requirements)
4. [Installation](#installation)
5. [Usage Guide](#usage-guide)
6. [Backup](#backup)
7. [Updating](#updating)
8. [Network Architecture](#network-architecture)
9. [File Reference](#file-reference)
10. [Security](#security)
11. [Troubleshooting](#troubleshooting)
12. [Architecture](#architecture)
13. [License](#license)
14. [Contact](#contact)

---

## Features

- **Dual PTZ camera control** — Pan, tilt, zoom, focus, and exposure via VISCA over TCP/IP (port 5678)
- **131-seat auditorium layout** — Visual seat grid with a per-seat saved camera preset
- **Speaker management** — Drag-and-drop name assignment to seats; chairman gets individual saved positions per speaker
- **ATEM switcher integration** — Monitors program output and auto-switches between camera inputs
- **Session management** — Coordinated camera power-on/off with motor initialisation sequence
- **Async event bus** — Thread-safe `AsyncEventBus`; events are queued and dispatched without blocking the UI
- **Worker supervisor** — Background watchdog checks camera and ATEM threads every 10 s and restarts them automatically if they fail
- **Simulation mode** — Virtual VISCA servers and ATEM for development without hardware
- **Network discovery** — TCP/ARP scan to auto-detect camera IPs on the LAN
- **Operating schedule** — Per-weekday enable/disable with configurable start and end times
- **Touchscreen interface** — Optimised for 1920×1080 with virtual keyboard support
- **Machine-locked login** — PBKDF2-HMAC-SHA256 password; progressive lockout after failed attempts; audit log
- **Persistent data** — JSON files stored in `~/.config/dublinisl/`; survive reinstalls and `git pull`
- **Atomic JSON writes** — Temp-file + rename prevents corruption on power loss; automatic `.bak` copy on every save
- **ZIP export / import** — One-click full backup and restore (data + config files) via Settings

> Screenshots of the interface will be added in a future release.

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| **Computer** | Raspberry Pi 4 (4 GB RAM recommended) |
| **PTZ Cameras** | 2 × VISCA-over-IP cameras, TCP port **5678** |
| **Video Switcher** | BlackMagic ATEM (optional), TCP port **9910** |
| **Display** | 1920×1080 touchscreen (recommended); mouse + keyboard also supported |
| **Network** | All devices on the same LAN; static IPs strongly recommended |

> Developed and tested on **Raspberry Pi OS**. It may work on other Linux distributions or Windows, but these are not officially supported.

---

## Software Requirements

| Software | Version | Notes |
|----------|---------|-------|
| Python | 3.8 or newer | Pre-installed on Raspberry Pi OS |
| PyQt5 | Latest | GUI framework |
| PyATEMMax | Latest | Optional — only needed for ATEM integration |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/halcondeoro/dublinisl_controls_rpi_ip_v3.git
cd dublinisl_controls_rpi_ip_v3
```

> If git is not installed: `sudo apt-get install git`

### 2. Install Python dependencies

```bash
pip3 install PyQt5
```

If you are using a BlackMagic ATEM switcher, also install:

```bash
pip3 install PyATEMMax
```

### 3. Create configuration files

Create the following plain-text files in the project folder with your actual network values:

| File | Contents | Example |
|------|----------|---------|
| `PTZ1IP.txt` | IP address of the Platform camera | `172.16.1.11` |
| `PTZ2IP.txt` | IP address of the Audience camera | `172.16.1.12` |
| `Cam1ID.txt` | VISCA device ID for Camera 1 (hex) | `81` |
| `Cam2ID.txt` | VISCA device ID for Camera 2 (hex) | `82` |
| `ATEMIP.txt` | IP address of the BlackMagic ATEM | `192.168.1.240` |
| `Contact.txt` | Support contact shown on the Help screen | `IT Support: ext. 123` |

Quick creation:

```bash
echo "172.16.1.11"   > PTZ1IP.txt
echo "172.16.1.12"   > PTZ2IP.txt
echo "81"            > Cam1ID.txt
echo "82"            > Cam2ID.txt
echo "192.168.1.240" > ATEMIP.txt
echo "IT Support"    > Contact.txt
```

> All values can also be edited from inside the app via **Settings → Camera Configuration**.

### 4. Set the login password

```bash
python3 setup_password.py
```

Enter and confirm your new password. The file `password.enc` is written and locked to this machine.

> **Default password (first run):** `dublin2024` — change it immediately.

### 5. Run the application

```bash
python3 main.py
```

**Auto-start on boot (Raspberry Pi):**

Add to `/etc/rc.local` before `exit 0`:

```bash
su pi -c "cd /home/pi/dublinisl_controls_rpi_ip_v3 && python3 main.py &"
```

---

## Usage Guide

### Login Screen

| Element | Description |
|---------|-------------|
| **Password field** | Type the login password (input is hidden) |
| **ACCESS** | Submit — or press **Enter** |
| **? Help** | Displays the support contact from `Contact.txt` |
| **Status message** | Green on success; amber/red on failure |

Failed login lockout:

| Attempt | Lockout |
|---------|---------|
| 1st | No lockout |
| 2nd | 10 seconds |
| 3rd | 30 seconds |
| 4th | 60 seconds |
| 5th+ | 1 hour |

All attempts are recorded in `audit_log.json` with timestamps.

---

### Splash Screen — System Check

After login, 12 automated checks run before the main window opens. Each component shows **OK** if reachable or **--** if unavailable (the app continues regardless). Press **Ctrl+D** for diagnostic detail.

---

### Main Window Overview

The window has two areas:

| Area | Description |
|------|-------------|
| **Seat grid (left)** | One button per seat (1–131); click to recall that seat's camera preset |
| **Right panel** | Camera controls: mode toggle, camera select, joystick, zoom, focus, exposure |

Platform buttons at the top of the grid:

| Button | Preset |
|--------|--------|
| **Left** | Left side of the stage |
| **Chairman** | Chairman desk — per-speaker personal presets |
| **Right** | Right side |

---

### CALL Mode vs SET Mode

| Mode | Purpose |
|------|---------|
| **CALL** (red) | Live operation — click a seat to recall its preset and switch the ATEM input |
| **SET** (green) | Setup — drag speaker names to seats, save chairman positions |

Use **SET mode** before the meeting to assign attendees. Switch to **CALL mode** when the meeting starts.

---

### Controlling a Camera

**Select camera:** Use the Platform / Audience toggle buttons. A green LED means reachable; red means offline.

**Joystick — pan and tilt:** Click and drag toward any of 8 directions. Camera moves while the knob is held; release to stop.

**Zoom:** Vertical slider to the right of the joystick. Drag up to zoom in, down to zoom out.

**Focus:**

| Button | Action |
|--------|--------|
| Auto Focus | Continuous auto-focus (default) |
| One Push AF | Single trigger, then holds |
| Manual Focus | Disables auto-focus |

**Exposure:**

| Button | Action |
|--------|--------|
| Darker | Decreases exposure |
| Backlight | Toggles backlight compensation (glows orange when ON) |
| Brighter | Increases exposure |

---

### Assigning Speakers to Seats

Done in **SET mode** before the meeting.

1. Click the **Attendees** button (person icon)
2. In the floating panel, click and hold a name
3. Drag it onto the desired seat button
4. The button updates to show the speaker's first name

**Remove an assignment:** Drag the seat back to the Attendees panel, or double-tap the seat and confirm.

**Attendees panel buttons:**

| Button | Action |
|--------|--------|
| Pencil | Rename the speaker |
| Bin | Delete the speaker permanently |
| + Add | Add a new speaker |
| Bring All Back | Clear all seat assignments at once |

---

### Chairman Presets

Saves a personalised camera position per speaker for the chairman seat.

1. Drag a speaker's name onto the Chairman button
2. Position the camera with the joystick and zoom
3. Click **Save position**

In CALL mode, clicking Chairman recalls that speaker's saved position automatically. Click **Edit** to re-position and save again.

---

### Configuration Dialog

Open via **Settings** at the bottom of the right panel.

| Section | Description |
|---------|-------------|
| **Session** | Start or end the camera session (powers cameras on/off) |
| **Camera** | Edit IP / VISCA ID; green = reachable, red = offline |
| **Camera Discovery** | LAN scan — assign found IPs directly |
| **Access** | Change the login password |
| **Schedule** | Open the weekly schedule editor |
| **Simulation Mode** | Toggle real hardware vs virtual cameras |
| **Close Program** | Shut down the application |

---

### Weekly Schedule

Open via **Settings → Weekly Schedule**.

- Check a day to enable it; set start and end times
- During scheduled hours the login screen requires no password
- Saved to `schedule.json`

---

### Simulation Mode

Runs the full application without physical hardware.

```bash
python3 sim_mode.py on
python3 main.py
```

Or from inside the app: **Settings → Enable Simulation Mode**.

To restore real hardware:

```bash
python3 sim_mode.py off
```

---

## Backup

### Data files (stored in `~/.config/dublinisl/` — survive reinstalls)

| File | Contents |
|------|----------|
| `seat_names.json` | Speaker names and seat assignments |
| `chairman_presets.json` | Per-speaker camera presets |
| `schedule.json` | Weekly operating schedule |

Each JSON file has an automatic `.bak` sibling. If a file becomes corrupt, rename the `.bak` to restore the previous save.

> The data directory can be overridden with `DUBLINISL_DATA_DIR`, e.g. `DUBLINISL_DATA_DIR=/mnt/usb python3 main.py`.

### Configuration files (in the app directory)

| File | Contents |
|------|----------|
| `PTZ1IP.txt`, `PTZ2IP.txt` | Camera IP addresses |
| `Cam1ID.txt`, `Cam2ID.txt` | VISCA device IDs |
| `ATEMIP.txt` | ATEM IP address |
| `Contact.txt` | Support contact |

> `password.enc` is machine-locked — it cannot be used on a different machine and does not need to be backed up.

### ZIP export / import (built-in)

- **Export Backup** — creates a `.zip` with all JSON data files and all `.txt` config files
- **Import Backup** — restores both groups from a previously exported `.zip`

This is the recommended way to migrate to a new Raspberry Pi.

### Recommended: automatic daily backup to USB drive

```bash
#!/bin/bash
# /home/pi/backup_dublinisl.sh
DEST="/media/pi/BACKUP/dublinisl_$(date +%Y%m%d)"
mkdir -p "$DEST"
cp "$HOME/.config/dublinisl"/*.json "$DEST"/
cp /home/pi/dublinisl_controls_rpi_ip_v3/*.txt "$DEST"/
echo "Backup completed: $DEST"
```

Schedule daily at 02:00:

```bash
chmod +x /home/pi/backup_dublinisl.sh
crontab -e
# Add:
0 2 * * * /home/pi/backup_dublinisl.sh
```

---

## Updating

Data files and `.txt` config files are never touched by git. Pull the latest code and restart:

```bash
cd /home/pi/dublinisl_controls_rpi_ip_v3
git pull origin main
python3 main.py
```

If new Python dependencies were added:

```bash
pip3 install PyQt5
pip3 install PyATEMMax   # only if using ATEM
```

> Always check the release notes before updating on a production system.

---

## Network Architecture

```
                    LAN
+---------------+  TCP:5678  +----------+
| Raspberry Pi  | ---------> | PTZ Cam1 |
| (this app)    | ---------> | PTZ Cam2 |
|               |  TCP:9910  +----------+
|               | ---------> |   ATEM   |
+---------------+            +----------+
```

- All connections are **outbound TCP** from the Raspberry Pi
- No incoming connections required — no firewall rules needed
- Static IPs are strongly recommended for all devices

---

## File Reference

### Configuration files (plain text, created manually)

| File | Description |
|------|-------------|
| `PTZ1IP.txt` | Platform camera IP address |
| `PTZ2IP.txt` | Audience camera IP address |
| `Cam1ID.txt` | Camera 1 VISCA device ID (hex) |
| `Cam2ID.txt` | Camera 2 VISCA device ID (hex) |
| `ATEMIP.txt` | BlackMagic ATEM IP address |
| `Contact.txt` | Support contact shown in Help |

### Data files (auto-managed, stored in `~/.config/dublinisl/`)

| File | Description |
|------|-------------|
| `seat_names.json` | Speaker names and seat assignments |
| `chairman_presets.json` | Per-speaker camera presets for the chairman seat |
| `schedule.json` | Weekly operating schedule |

### Runtime files (in the app directory)

| File | Description |
|------|-------------|
| `password.enc` | Machine-locked encrypted login password |
| `audit_log.json` | Timestamped log of all login attempts |
| `sim_ip_backup.json` | Backup of real IPs while simulation mode is active |

---

## Security

- **Machine-locked encryption:** `password.enc` is encrypted with a key derived from the machine's hardware identifier — unusable on any other machine.
- **PBKDF2-HMAC-SHA256:** 200,000 iterations with a 16-byte random salt.
- **Progressive lockout:** 10 s, 30 s, 60 s, and 1 hour after repeated failed logins.
- **Audit logging:** Every login attempt recorded in `audit_log.json`.
- **No network listener:** Only outbound TCP connections — no open ports.

---

## Troubleshooting

| Symptom | Likely cause | Solution |
|---------|-------------|----------|
| Camera LED shows red | Camera unreachable | Check IP in `PTZ1IP.txt` / `PTZ2IP.txt`; verify camera is on and on the LAN |
| Wrong password on first run | Default not yet set | Run `python3 setup_password.py` |
| `password.enc` rejected after moving to new Pi | Machine-lock mismatch | Run `python3 setup_password.py` on the new machine |
| ATEM shows "--" in splash | ATEM offline or wrong IP | Check `ATEMIP.txt`; the app works without ATEM |
| Joystick has no effect | Session not started | Settings → **Start Session** |
| App crashes at startup | PyQt5 not installed | Run `pip3 install PyQt5` |
| Seat assignments lost after reboot | `seat_names.json` missing | Check `~/.config/dublinisl/`; rename `.bak` to `.json` or restore from ZIP |
| Chairman preset slot collision warning | Two speakers share a slot | Click OK to reassign automatically, or clear the old entry first in SET mode |
| JSON file corrupt after power cut | Incomplete write | Rename `<file>.json.bak` → `<file>.json` in `~/.config/dublinisl/` |

---

## Architecture

The codebase is split into five layers. Each layer only imports from layers below it — no circular dependencies.

```
┌──────────────────────────────────────┐
│  UI Layer (Qt)                       │
│  main_window, right_panel,           │
│  login_screen, splash_screen, …      │
├──────────────────────────────────────┤
│  Adapters  (adapters/input/)         │
│  joystick_adapter, seat_adapter      │
├──────────────────────────────────────┤
│  Application  (application/)         │
│  CameraService, PresetService,       │
│  SessionService                      │
├──────────────────────────────────────┤
│  Core  (core/)                       │
│  AsyncEventBus, SystemState,         │
│  Controller, Supervisor              │
├──────────────────────────────────────┤
│  Domain  (domain/)                   │
│  Camera, Preset, Seat  (data only)   │
└──────────────────────────────────────┘
```

| Layer | Qt? | I/O? | Responsibility |
|-------|-----|------|----------------|
| **Domain** | No | No | Data shapes and constants |
| **Core** | No | No | State, events, orchestration, thread supervision |
| **Application** | No | JSON / TCP | Business logic services |
| **Adapters** | Yes | No | Bridge Qt signals → AsyncEventBus |
| **UI** | Yes | No | Render state, capture user input |

Key modules:

| Module | Description |
|--------|-------------|
| `core/events.py` | `AsyncEventBus` — thread-safe queue; dispatches events without blocking the UI |
| `core/supervisor.py` | `Supervisor` — polls registered workers every 10 s; restarts any that have died |
| `core/state.py` | `SystemState` — single source of truth for runtime state |
| `core/controller.py` | Central coordinator wiring all services together |
| `visca_protocol.py` | Pure VISCA command encoding (no Qt dependency) |
| `camera_worker.py` | Daemon thread per camera; persistent TCP socket |
| `atem_monitor.py` | Background thread monitoring ATEM program output |
| `data_paths.py` | Persistent data directory path + ZIP export/import |
| `json_io.py` | Atomic JSON read/write with `.bak` copies |
| `secret_manager.py` | PBKDF2 + machine-locked password encryption |
| `hardware_simulator.py` | Virtual VISCA servers + ATEM for simulation mode |

---

## License

Copyright (c) 2026 Marco Antonio Tevar Asensio. Todos los derechos reservados.

Este software es propietario y de uso privado exclusivo. Queda prohibida su copia, distribución, modificación o uso sin autorización expresa y por escrito del autor. Consulta el fichero [LICENSE](LICENSE) para el texto completo.

---

## Contact

For technical support or installation assistance:

**Marco Tevar** — +353 085 236 8581
**Carol Torres** — +353 89 975 2890
